from random import Random
import re
from bson import ObjectId
import httpx
import requests
from datetime import datetime, timedelta, timezone
import os
import json
import asyncio
import threading
import time
from typing import Optional, Dict, Any, List
import logging
logger = logging.getLogger(__name__)

class MongoJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle MongoDB specific types."""
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        
        return super().default(obj)


class LlmAgent:
    """Base class for any agent that communicates with the LLM API."""
    def __init__(self, api_endpoint: str, model_name: str = 'carlos'):
        self.api_endpoint = api_endpoint
        self.model_name = model_name
        self.client = httpx.AsyncClient(timeout=60.0)

    async def _call_llm(self, messages: list, schema: Optional[dict] = None, temperature: float = 0.7, max_tokens: int = -1, stream: bool = False) -> dict:
        """Call the LLM API with given messages and return the response."""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        if schema:
            payload["response_format"] = schema
        headers = {
            "Content-Type": "application/json"
        }

        try:
            response = await self.client.post(f"{self.api_endpoint}/v1/chat/completions", headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            content_str = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            return json.loads(content_str) 
        except requests.RequestException as e:
            logger.error(f"LLM API request failed: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM response: {e}")
            logger.debug(f"Raw response content: {response.text}")
            return {}


class CuratorAgent(LlmAgent):
    """Agent responsible for curating and analyzing incoming messages."""
    def __init__(self, api_endpoint: str, system_prompt: str, schema: dict):
        super().__init__(api_endpoint)
        self.system_prompt = system_prompt
        self.schema = schema

    async def run(self, message: str, chunk: str=None) -> dict:
        """Curate the incoming message and return analysis."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": message}
        ]
        if chunk:
            messages.append({"role": "system", "content": f"Long input split into chunks. Directive: Store all information for later synthesis."})
            messages.append({"role": "system", "content": f"Chunk info: {chunk}"})
        response = await self._call_llm(messages, schema=self.schema, temperature=0, max_tokens=-1)
        return response.get("queries_to_execute", []), response.get("insights_to_store", [])
    

class ThinkerAgent(LlmAgent):
    """Agent responsible for thinking about curated data and formulating responses."""
    def __init__(self, api_endpoint: str, system_prompt: str, schema: dict):
        super().__init__(api_endpoint)
        self.system_prompt = system_prompt
        self.schema = schema

    async def run(self, message: str, curator_data: dict) -> dict:
        """Think about the curator provided data and return insights."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": "Curator data: " + json.dumps(curator_data, cls=MongoJSONEncoder)},
            {"role": "user", "content": f"Orginal user message: {message}"}
        ]
        return await self._call_llm(messages, schema=self.schema, temperature=0, max_tokens=-1)
    

class GeneratorAgent(LlmAgent):
    """Agent responsible for generating the final response based on thinker insights."""
    def __init__(self, api_endpoint: str, system_prompt: str, schema: dict):
        super().__init__(api_endpoint)
        self.system_prompt = system_prompt
        self.schema = schema

    async def run(self, message: str, think_data: dict, timestamp: str) -> str:
        """Generate a response based on thinker insights."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": "Thinker data: " + json.dumps(think_data, cls=MongoJSONEncoder)},
            {"role": "system", "content": f"Current time is {timestamp}"},
            {"role": "user", "content": f"Original user message: {message}"}
        ]
        response = await self._call_llm(messages, schema=self.schema, temperature=0.7)
        return response.get("response_text", "I'm not sure how to respond to that right now.")
    
    async def stream(self, message: str, think_data: dict, timestamp: str):
        """Stream a response based on thinker insights."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": "Thinker data: " + json.dumps(think_data, cls=MongoJSONEncoder)},
            {"role": "system", "content": f"Current time is {timestamp}"},
            {"role": "user", "content": f"Original user message: {message}"}
        ]
        async for chunk in self._call_llm(messages, schema=self.schema, temperature=0.7, stream=True):
            yield chunk
    

class SummarizerAgent(LlmAgent):
    """Agent responsible for summarizing long messages and generating tags for it."""
    def __init__(self, api_endpoint: str, system_prompt: str, schema: dict):
        super().__init__(api_endpoint)
        self.system_prompt = system_prompt
        self.schema = schema

    async def run(self, message: str) -> List[str]:
        """Summarize the message and generate tags."""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Message to summarize: {message}"}
        ]
        response = await self._call_llm(messages, schema=self.schema, temperature=0, max_tokens=-1)
        return response.get("summary", []), response.get("tags", [])


class CarlosDatabaseHandler:
    """Handles database interactions for storing and retrieving messages and analyses."""
    def __init__(self, db_uri: str, db_name: str):
        from pymongo import MongoClient
        self.client = MongoClient(db_uri)
        self.db = self.client[db_name]

        # Collections
        self.messages_col = self.db['messages'] # User messages
        self.responses_col = self.db['responses'] # Agent responses
        # Both messages and responses will have the following structure:
        # {'tags': ['tag1', 'tag2'],
        # 'embedding': [0.123, 0.456, ...],  # Vector embedding
        # 'summary': '',
        # 'message': ''}
        self.analyses_col = self.db['analyses'] # Thinker analyses
        self.insights_col = self.db['insights'] # Autom thoughts and insights
        self.interactions_col = self.db['interactions'] # Full interaction logs
        # interactions collection
        # {
        # "tags": ["tag1", "tag2"],
        # "embedding": [0.123, 0.456, ...],  # Vector embedding of the user message
        # "_id": "interaction_abc123",
        # "user_id": "your_user_name",
        # "timestamp": "2025-08-26T03:48:13.000Z",
        # "user_message_id": "msg_qwer456",  Link to messages collection
        # "agent_response_id": "res_asdf789",  Link to responses collection
        # "analysis_id": "ana_zxcv123"       Link to analyses collection
        # }
        self.cassandra_flags_col = self.db['cassandra_flags'] # Cassandra flags raised during thinking
        self.ensure_indexes()

    def ensure_indexes(self):
        """Ensure necessary indexes are created for efficient querying."""
        self.messages_col.create_index([("tags", 1)])
        self.responses_col.create_index([("tags", 1)])
        self.analyses_col.create_index([("tags", 1)])
        self.interactions_col.create_index([("tags", 1)])
        # self.interactions_col.create_index([("embedding", "vector")], name="search_context_vector_index", vector_params={"dimensions": 1536, "similarity": "cosine"})

    def store_user_message(self, message: str, summary: str, tags: list[str], embedding: list[float]) -> str:
        """Store a user message and return its ID."""
        doc = {
            "message": message,
            "summary": summary,
            "tags": tags,
            "embedding": embedding,
            "timestamp": datetime.now(timezone.utc)
        }
        result = self.messages_col.insert_one(doc)
        return str(result.inserted_id)
    
    def store_agent_response(self, message: str, summary: str, tags: list[str], embedding: list[float]) -> str:
        """Store an agent response and return its ID."""
        doc = {
            "message": message,
            "summary": summary,
            "tags": tags,
            "embedding": embedding,
            "timestamp": datetime.now(timezone.utc)
        }
        result = self.responses_col.insert_one(doc)
        return str(result.inserted_id)
    
    def store_analysis(self, analysis_data: dict) -> str:
        """Store thinker analysis data and return its ID."""
        # We dont yet know what to store here or how does analysis_data look like, we prolly have atleast tags
        doc = {
            "timestamp": datetime.now(timezone.utc)
        }
        result = self.analyses_col.insert_one(doc)
        return str(result.inserted_id)

    def store_interaction(self, interaction_data: dict) -> str:
        all_tags = interaction_data.get("user_tags", []) + interaction_data.get("response_tags", [])
        user_message_id = self.store_user_message(
            message=interaction_data.get("user_message", ""),
            summary=interaction_data.get("user_summary", ""),
            tags=interaction_data.get("user_tags", []),
            embedding=interaction_data.get("user_embedding", [])
        )

        agent_response_id = self.store_agent_response(
            message=interaction_data.get("agent_response", ""),
            summary=interaction_data.get("response_summary", ""),
            tags=interaction_data.get("response_tags", []),
            embedding=interaction_data.get("response_embedding", [])
        )

        analysis_id = self.store_analysis(
            analysis_data=interaction_data.get("analysis", {})
        )

        doc = {
            "user_id": interaction_data.get("user_id", "unknown_user"),
            "timestamp": datetime.now(timezone.utc),
            "tags": all_tags,
            "user_message_id": ObjectId(user_message_id),
            "agent_response_id": ObjectId(agent_response_id),
            "analysis_id": ObjectId(analysis_id),
            "embedding": interaction_data.get("user_embedding", [])
        }
        result = self.interactions_col.insert_one(doc)
        return str(result.inserted_id)

    def search(self, tags: list[str], query_vector: list[float], time_filter: str = '', top_k: int = 5) -> list[dict]:
        """
        Search for relevant past messages on a LOCAL MongoDB instance.
        This version manually calculates cosine similarity since $vectorSearch is not available.
        """
        pipeline = [
            # Stage 1: Fast initial filtering using the index on 'tags'.
            {
                '$match': {
                    'tags': {'$in': tags}
                }
            },
            
            # Stage 2: Manually calculate cosine similarity for the filtered documents.
            # This part is computationally intensive and does not use an index.
            {
                '$addFields': {
                    'similarity': {
                        '$let': {
                            'vars': {
                                'dotProduct': {
                                    '$reduce': {
                                        'input': {'$range': [0, {'$size': '$embedding'}]},
                                        'initialValue': 0,
                                        'in': {
                                            '$add': [
                                                '$$value',
                                                {
                                                    '$multiply': [
                                                        {'$arrayElemAt': ['$embedding', '$$this']},
                                                        {'$arrayElemAt': [query_vector, '$$this']}
                                                    ]
                                                }
                                            ]
                                        }
                                    }
                                },
                                'normA': {
                                    '$sqrt': {
                                        '$reduce': {
                                            'input': '$embedding',
                                            'initialValue': 0,
                                            'in': {'$add': ['$$value', {'$pow': ['$$this', 2]}]}
                                        }
                                    }
                                },
                                'normB': {
                                    '$sqrt': {
                                        '$reduce': {
                                            'input': query_vector,
                                            'initialValue': 0,
                                            'in': {'$add': ['$$value', {'$pow': ['$$this', 2]}]}
                                        }
                                    }
                                }
                            },
                            'in': {
                                '$cond': [
                                    {'$or': [{'$eq': ['$$normA', 0]}, {'$eq': ['$$normB', 0]}]},
                                    0,
                                    {'$divide': ['$$dotProduct', {'$multiply': ['$$normA', '$$normB']}]}
                                ]
                            }
                        }
                    }
                }
            },
            
            # Stage 3: Sort by the newly calculated similarity score.
            {
                '$sort': {'similarity': -1}
            },
            
            # Stage 4: Limit to the top results.
            {
                '$limit': top_k
            },
            
            # --- The rest of your pipeline remains the same ---
            # Stage 5: Join with other collections to get summaries and analyses.
            {
                '$lookup': {
                    'from': 'messages',
                    'let': { 'msg_id': '$user_message_id' },
                    'pipeline': [
                        { '$match': { '$expr': { '$eq': ['$_id', '$$msg_id'] } } },
                        { '$project': { '_id': 0, 'summary': 1 } }
                    ],
                    'as': 'user_message_data'
                }
            },
            # ... (add your other $lookup stages for responses and analyses here) ...
            {
                '$lookup': {
                    'from': 'responses',
                    'let': { 'res_id': '$agent_response_id' },
                    'pipeline': [
                        { '$match': { '$expr': { '$eq': ['$_id', '$$res_id'] } } },
                        { '$project': { '_id': 0, 'summary': 1 } }
                    ],
                    'as': 'agent_response_data'
                }
            },
            {
                '$lookup': {
                    'from': 'analyses',
                    'localField': 'analysis_id',
                    'foreignField': '_id',
                    'as': 'analysis_data'
                }
            },

            # Stage 6: Shape the final output document.
            {
                '$project': {
                    '_id': 0,
                    'interaction_id': '$_id',
                    'timestamp': 1,
                    'tags': 1,
                    'user_id': 1,
                    'similarity': 1, # Include the calculated similarity
                    'user_message_summary': {
                        '$arrayElemAt': ['$user_message_data.summary', 0]
                    },
                    'agent_response_summary': {
                        '$arrayElemAt': ['$agent_response_data.summary', 0]
                    },
                    'analysis': {
                        '$arrayElemAt': ['$analysis_data', 0]
                    }
                }
            }
        ]
        results = list(self.interactions_col.aggregate(pipeline))
        return results
    
    def search_by_tags(self, tags: list[str], time_filter:str='', top_k: int = 5) -> list[dict]:
        """Search for relevant past messages based on tags only."""
        query = {
            "tags": {"$in": tags}
        }
        results = list(self.interactions_col.find(query).sort("timestamp", -1).limit(top_k))
        return results
     

class Carlos:
    """Main class for handling user interactions and coordinating agents."""
    def __init__(self, api_endpoint: str, db_uri: str, user_name: str):
        self.api_endpoint = api_endpoint
        self.db_uri = db_uri
        self.user_name = user_name

        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.db_handler = CarlosDatabaseHandler(db_uri, user_name)
    
        # Load prompts and schemas
        prompts = self._load_prompts()
        self.curator_agent = CuratorAgent(api_endpoint, prompts["curator"]["prompt"], prompts["curator"]["schema"])
        self.thinker_agent = ThinkerAgent(api_endpoint, prompts["thinker"]["prompt"], prompts["thinker"]["schema"])
        self.generator_agent = GeneratorAgent(api_endpoint, prompts["generator"]["prompt"], prompts["generator"]["schema"])
        self.summarizer_agent = SummarizerAgent(api_endpoint, prompts["summarizer"]["prompt"], prompts["summarizer"]["schema"])

    async def _fetch_embeddings(self, text: str) -> List[float]:
        """Asynchronously fetch embeddings for the given text."""
        payload = { "model": "text-embedding-nomic-embed-text-v1.5", "input": text }
        headers = { "Content-Type": "application/json" }
        try:
            # Use the async client with 'await'
            response = await self.http_client.post(f"{self.api_endpoint}/v1/embeddings", headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("data", [{}])[0].get("embedding", [])
        except httpx.RequestError as e:
            logger.error(f"Embedding API request failed: {e}")
            return []
        

    def _load_prompts(self) -> Dict[str, Any]:
        """Load prompts and schemas from files."""
        base_path = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base_path, 'prompts', 'curator_system_prompt.txt'), 'r') as f:
            curator_prompt = f.read()
        with open(os.path.join(base_path, 'schemas', 'curator_schema.json'), 'r') as f:
            curator_schema = json.loads(f.read())
        with open(os.path.join(base_path, 'prompts', 'thinker_system_prompt.txt'), 'r') as f:
            thinker_prompt = f.read()
        with open(os.path.join(base_path, 'schemas', 'thinker_schema.json'), 'r') as f:
            thinker_schema = json.loads(f.read())
        with open(os.path.join(base_path, 'prompts', 'response_generator_system_prompt.txt'), 'r') as f:
            generator_prompt = f.read()
        with open(os.path.join(base_path, 'schemas', 'response_generator_schema.json'), 'r') as f:
            generator_schema = json.loads(f.read())
        with open(os.path.join(base_path, 'prompts', 'summarizer_system_prompt.txt'), 'r') as f:
            summarizer_prompt = f.read()
        with open(os.path.join(base_path, 'schemas', 'summarizer_schema.json'), 'r') as f:
            summarizer_schema = json.loads(f.read())

        return {
            "curator": {"prompt": curator_prompt, "schema": curator_schema},
            "thinker": {"prompt": thinker_prompt, "schema": thinker_schema},
            "generator": {"prompt": generator_prompt, "schema": generator_schema},
            "summarizer": {"prompt": summarizer_prompt, "schema": summarizer_schema}
        }
    
    async def close(self):
        """Close any open resources."""
        await self.http_client.aclose()
        await self.curator_agent.client.aclose()
        await self.thinker_agent.client.aclose()
        await self.generator_agent.client.aclose()
        await self.summarizer_agent.client.aclose()

    async def chunk_message(self, message: str, chunk_size: int = 2000) -> List[str]:
        """Chunk a long message into smaller parts."""
        words = message.split()
        chunks = []
        current_chunk = []

        for word in words:
            if len(' '.join(current_chunk + [word])) <= chunk_size:
                current_chunk.append(word)
            else:
                chunks.append(' '.join(current_chunk))
                current_chunk = [word]

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        summaries = []
        tags = set()
        for chunk in chunks:
            summary, chunk_tags = await self.summarizer_agent.run(chunk)
            summaries.append(summary)
            tags.update(chunk_tags)
            emedding = await self._fetch_embeddings(chunk)
            self.db_handler.store_user_message(chunk, summary, list(chunk_tags), emedding)
        return "".join(summaries), list(tags)


    async def _pipeline(self, message: str) -> str:
        """Process the message through the full pipeline and return the final response."""
        # User Input -> Initial Fetch:
        # The Summarizer generates tags and an embedding from the user's message.
        # The DatabaseHandler performs the initial hybrid search to get a baseline of relevant context.
        # Thinker (The Detective 🕵️):
        # The Thinker receives the user's query and the initial search results.
        # Its primary job is to analyze this context and identify knowledge gaps. It asks the high-level questions: "This is a good start, but to give a great answer, what else do I need to know? What's missing? What's contradictory?"
        # It then formulates an "information request" for the Curator.
        # Curator (The Librarian 📚):
        # The Curator receives the Thinker's specific information request.
        # Its job is purely tactical: translate the Thinker's request into concrete database queries and execute them. It's the expert at finding things in the database.
        # It can also store any intermediate insights the Thinker generates.
        # The Loop:
        # The Curator returns the new information to the Thinker.
        # The Thinker re-evaluates the now-richer context. If it's satisfied, it proceeds. If not, it can ask the Curator for even more information.
        # Response & Storage:
        # Once the Thinker has a complete picture, it passes its final, synthesized context to the Generator.
        # The Generator creates the final response.
        # The entire exchange is then stored in the database
        
        
        if len(message) > 4000:
            summary, tags = await self.chunk_message(message)
            logger.debug(f"Message was chunked. Summary: {summary}, Tags: {tags}")

        else:
            timestamp = datetime.now(timezone.utc).isoformat()
            
            summary, tags = await self.summarizer_agent.run(message)
            logger.debug(f"Summarizer output - Summary: {summary}, Tags: {tags}")
            # query_vector = await self._fetch_embeddings(message)

            # search_results = self.db_handler.search(tags, query_vector, top_k=5)
            # logger.debug(f"Search results: {search_results}")

        query_vector = await self._fetch_embeddings(summary)
        max_thinker_loops = 5
        thinker_loop = 0
        thinker_context = {
            "search_results": [],
            "reasoning": [],
            "summary": summary,
            "tags": tags
        }

        while thinker_loop < max_thinker_loops:
            thinker_loop += 1
            thinker_response = await self.thinker_agent.run(message, thinker_context)
            logger.debug(f"Thinker output: {thinker_response}")
            is_context_sufficient = thinker_response.get("is_context_sufficient", True)
            information_request = thinker_response.get("information_request", "")
            reasoning = thinker_response.get("reasoning", "")
            cassandra_flags = thinker_response.get("cassandra_flags", [])
            self.db_handler.cassandra_flags_col.insert_one({
                "flags": cassandra_flags,
                "timestamp": datetime.now(timezone.utc)
            })

            if is_context_sufficient:
                logger.debug("Thinker determined context is sufficient.")
                break
            
            queries_to_execute, insights_to_store = await self.curator_agent.run(information_request)
            logger.debug(f"Curator output - Queries: {queries_to_execute}, Insights: {insights_to_store}")
            if insights_to_store:
                # Store insights in the insights collection
                for insight in insights_to_store:
                    self.db_handler.insights_col.insert_one({
                        "insight": insight,
                        "timestamp": datetime.now(timezone.utc)
                    })
            # Execute queries and update thinker_context
            for query in queries_to_execute:
                query_type = query.get("query_type", "")
                tags = query.get("tags", [])
                time_filter = query.get("time_filter", "")
                if query_type == "search_by_tags":
                    results = self.db_handler.search_by_tags(tags, time_filter, top_k=5)
                    thinker_context.setdefault("search_results", []).extend(results)
                elif query_type == "hybrid_search":
                    embedded_vector = self._fetch_embeddings(tags)
                    results = self.db_handler.search(tags, embedded_vector, time_filter, top_k=5)
                    thinker_context.setdefault("search_results", []).extend(results)
                else:
                    logger.warning(f"Unknown query type: {query_type}")
                    continue

            thinker_context.setdefault("reasoning", []).append(reasoning)
            
        final_response = await self.generator_agent.run(message, thinker_context, timestamp)
        logger.debug(f"Generator output: {final_response}")
        response_summary, response_tags = await self.summarizer_agent.run(final_response)
        # Store the entire interaction
        interaction_data = {
            "user_id": self.user_name,
            "user_message": message,
            "user_summary": summary,
            "user_tags": tags,
            "user_embedding": query_vector,
            "agent_response": final_response,
            "response_summary": response_summary,
            "response_tags": response_tags,
            "response_embedding": await self._fetch_embeddings(final_response),
            "analysis": thinker_context
        }
        self.db_handler.store_interaction(interaction_data)
        return final_response
    
    async def stream_response(self, message: str):
        """Stream the final response back to the user."""
        # yield format: {"status": status, "message": anything we want to show the user}


        yield {"status": "chunking", "message": "Carlos is thinking..."}
        if len(message) > 4000:
            summary, tags = await self.chunk_message(message)
            logger.debug(f"Message was chunked. Summary: {summary}, Tags: {tags}")

        else:
            summary, tags = await self.summarizer_agent.run(message)
            logger.debug(f"Summarizer output - Summary: {summary}, Tags: {tags}")

        yield {"status": "embedding", "message": f"Hmm, let me think about that..."}
        # choose random tags from list of tags for flavor text
        yield {"status": "searching", "message": f"{Random.choice(tags) if tags else 'Interesting topic'}... let me see what I can find."}
        query_vector = await self._fetch_embeddings(summary)
        max_thinker_loops = 5
        thinker_loop = 0
        thinker_context = {
            "search_results": [],
            "reasoning": [],
            "summary": summary,
            "tags": tags
        }

        while thinker_loop < max_thinker_loops:
            thinker_loop += 1
            thinker_response = await self.thinker_agent.run(message, thinker_context)
            logger.debug(f"Thinker output: {thinker_response}")
            is_context_sufficient = thinker_response.get("is_context_sufficient", True)
            information_request = thinker_response.get("information_request", "")
            reasoning = thinker_response.get("reasoning", "")
            cassandra_flags = thinker_response.get("cassandra_flags", [])
            self.db_handler.cassandra_flags_col.insert_one({
                "flags": cassandra_flags,
                "timestamp": datetime.now(timezone.utc)
            })


            yield {"status": "thinking", "message": thinker_response.get("reasoning", "Let me think...")}
                
            if is_context_sufficient:
                logger.debug("Thinker determined context is sufficient.")
                break
            
            queries_to_execute, insights_to_store = await self.curator_agent.run(information_request)
            logger.debug(f"Curator output - Queries: {queries_to_execute}, Insights: {insights_to_store}")
            if insights_to_store:
                # Store insights in the insights collection
                for insight in insights_to_store:
                    self.db_handler.insights_col.insert_one({
                        "insight": insight,
                        "timestamp": datetime.now(timezone.utc)
                    })
            # Execute queries and update thinker_context
            for query in queries_to_execute:
                query_type = query.get("query_type", "")
                tags = query.get("tags", [])
                time_filter = query.get("time_filter", "")
                if query_type == "search_by_tags":
                    results = self.db_handler.search_by_tags(tags, time_filter, top_k=5)
                    thinker_context.setdefault("search_results", []).extend(results)
                elif query_type == "hybrid_search":
                    embedded_vector = self._fetch_embeddings(tags)
                    results = self.db_handler.search(tags, embedded_vector, time_filter, top_k=5)
                    thinker_context.setdefault("search_results", []).extend(results)
                else:
                    logger.warning(f"Unknown query type: {query_type}")
                    continue

            thinker_context.setdefault("reasoning", []).append(reasoning)

        final_response = ""
        async for chunk in self.generator_agent.stream(message, thinker_context, datetime.now(timezone.utc).isoformat()):
            final_response += chunk
            yield {"status": "response", "message": chunk}

        response_summary, response_tags = await self.summarizer_agent.run(final_response)
        # Store the entire interaction
        interaction_data = {
            "user_id": self.user_name,
            "user_message": message,
            "user_summary": summary,
            "user_tags": tags,
            "user_embedding": query_vector,
            "agent_response": final_response,
            "response_summary": response_summary,
            "response_tags": response_tags,
            "response_embedding": await self._fetch_embeddings(final_response),
            "analysis": thinker_context
        }
        self.db_handler.store_interaction(interaction_data)
        

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.DEBUG)

    carlos = Carlos(
        api_endpoint="http://localhost:1234",
        db_uri="mongodb://localhost:27017",  
        user_name="test_user"
    )

    async def test():
        user_message = "Can you help me understand the implications of quantum computing on modern cryptography?"
        response = await carlos._pipeline(user_message)
        print("Final Response:", response)

    asyncio.run(test())