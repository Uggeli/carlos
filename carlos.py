import re
from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.operations import IndexModel
from bson import ObjectId
import requests
from datetime import datetime, timedelta, timezone
import os
import json
from typing import Optional, List, Dict, Any
import logging
logger = logging.getLogger(__name__)

# Phase 1: Perception & Ingestion
# What happens: The Listener perceives the Speaker's utterance.

# Speaker's action: "Person says something." This is the raw data input. It's not just words; it includes tone of voice, cadence, volume (prosody), and in face-to-face conversation, body language and facial expressions.

# Example: Speaker says, "I'm thinking of getting a dog."

# Phase 2: Analysis & Deconstruction
# What happens: The Listener's brain (or an AI's processor) breaks the input down into meaningful components. This isn't just a single action, but several simultaneous processes.

# Listener's action: "Person 2 does analysis what person 1 said."

# Linguistic Parsing: Identifying the words, grammar, and sentence structure. (e.g., Subject: "I", Verb: "am thinking", Object: "getting a dog").

# Semantic Analysis: Understanding the literal meaning of the words. (e.g., The speaker is contemplating the acquisition of a canine.)

# Intent Recognition (Pragmatics): Figuring out the purpose behind the words. Is it a simple statement? Are they seeking an opinion? Are they expressing a desire for companionship? (e.g., This is likely a conversation starter, possibly seeking feedback or sharing a life update.)

# Entity Extraction: Identifying the key concepts. (e.g., Key entities are "I" (the Speaker) and "dog".)

# Phase 3: Contextualization & Retrieval
# What happens: The analyzed information is connected to a vast network of existing knowledge.

# Listener's action: "maybe retrieves some memories about stuff." This is crucial for a relevant response.

# Short-Term / Conversational Context: "What were we just talking about? Did they mention pets before?"

# Long-Term / Relational Memory: "I remember the Speaker telling me their apartment has a 'no pets' policy. This is new." or "They grew up with a golden retriever and loved it."

# World Knowledge: "What do I know about dogs? They need walks, food, vet visits. Certain breeds are better for apartments. Shelters are a good place to look."

# Example Retrieval: The Listener recalls: 1) The Speaker mentioned feeling lonely last week. 2) The Speaker lives in a small apartment. 3) The Listener's cousin just adopted a rescue dog and is very happy.

# Phase 4: Synthesis & Response Generation
# What happens: Based on the analysis and retrieved context, the Listener constructs a response.

# Listener's action: "says something based on that."

# Goal Formulation: The Listener decides on the purpose of their response. Do they want to be encouraging? Cautious? Inquisitive? (e.g., Goal: Be encouraging but also practical).

# Content Selection: Choose which pieces of retrieved information are most relevant. (e.g., Acknowledge their feeling of loneliness, mention the apartment size as a consideration, and bring up the positive adoption story).

# Linguistic Encoding: The chosen content is translated into actual words and sentences with an appropriate tone.

# Example Response: "Oh, that's exciting! A dog would be great company. Have you thought about what breed would be happy in an apartment?"

# Phase 5: Memory Update & Pruning
# What happens: The cycle concludes, and the context is updated for the next turn.

# Listener's action: "stores that cycle context and filters out irrelevant stuff to next cycle."

# Context Integration: The immediate memory is updated. The new "state" of the conversation is: "The topic is the Speaker getting a dog. I have just asked them about breeds suitable for apartments."

# Salience Filtering (Pruning): The mind doesn't store everything verbatim. It holds on to the most important information (the gist) and lets go of the less relevant details. The core concept ("thinking of getting a dog") is highly salient. The exact phrasing ("I'm thinking of...") is less so and might be forgotten. This prevents cognitive overload.

# Memory Consolidation: The key takeaway from this cycle might be stored in long-term memory. (e.g., "Note to self: My friend is considering getting a dog.")

# 2025-08-22 09:17:57  [INFO]
#  [LM STUDIO SERVER] ->	GET  http://192.168.50.202:1234/v1/models
# 2025-08-22 09:17:57  [INFO]
#  [LM STUDIO SERVER] ->	POST http://192.168.50.202:1234/v1/chat/completions
# 2025-08-22 09:17:57  [INFO]
#  [LM STUDIO SERVER] ->	POST http://192.168.50.202:1234/v1/completions
# 2025-08-22 09:17:57  [INFO]
#  [LM STUDIO SERVER] ->	POST http://192.168.50.202:1234/v1/embeddings

# curl http://localhost:1234/v1/chat/completions \
#   -H "Content-Type: application/json" \
#   -d '{
#     "model": "curator",
#     "messages": [
#       { "role": "system", "content": "Always answer in rhymes. Today is Thursday" },
#       { "role": "user", "content": "What day is it today?" }
#     ],
#     "temperature": 0.7,
#     "max_tokens": -1,
#     "stream": false
# }'

class CarlosDatabaseHandler:
    """Handles database operations for the Carlos AI system."""

    ENUM_MAPS = {
        "sentiment": {
            "positive_sentiment": ["positive", "excited", "happy", "satisfied"],
            "negative_sentiment": ["negative", "frustrated", "angry", "disappointed"],
            "neutral_sentiment": ["neutral", "calm", "indifferent"]
        },
        "event_type": {
            "critical_event": ["problem", "decision", "urgent"],
            "progress_update": ["milestone", "update", "goal", "achievement"],
            "social_event": ["meeting", "conversation", "collaboration"]
        }
    }

    def __init__(self, mongo_uri: str, username: str):
        """Initialize database handler for a specific user."""
        self.client = MongoClient(mongo_uri)
        self.username = username
        self.db_name = f"carlos_{username}"
        self.db = self.client[self.db_name]
        self._ensure_indexes()
        print(f"✓ Database handler initialized for user '{username}' on DB '{self.db_name}'")

    def _ensure_indexes(self):
        """Create indexes for better query performance."""
        try:
            # Conversations collection indexes
            conversations = self.get_collection("conversations")
            conversations.create_index([("timestamp", DESCENDING)])
            conversations.create_index([("entities", TEXT)])
            conversations.create_index([("semantic_tags", 1)])
            
            # Events collection indexes
            events = self.get_collection("events")
            events.create_index([("timestamp", DESCENDING)])
            events.create_index([("related_entities", 1)])
            events.create_index([("type", 1)])
            
            # User state collection index
            user_state = self.get_collection("user_state")
            user_state.create_index([("user_id", 1)])
            
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Index creation warning: {e}")

    def get_collection(self, collection_name: str):
        """Get a MongoDB collection by name."""
        return self.db[collection_name]

    def _get_timeframe_query(self, timeframe: str) -> Dict[str, Any]:
        """Generate MongoDB timestamp query from timeframe string."""
        now = datetime.now(timezone.utc)
        time_query = {}
        
        timeframe_map = {
            "last_hour": now - timedelta(hours=1),
            "today": now.replace(hour=0, minute=0, second=0, microsecond=0),
            "this_week": (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0),
            "recent": now - timedelta(days=3),
            "weeks": now - timedelta(weeks=2),
            "months": now - timedelta(days=30)
        }
        
        if timeframe in timeframe_map:
            time_query = {"$gte": timeframe_map[timeframe]}
        
        return {"timestamp": time_query} if time_query else {}

    def _expand_query(self, query: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively expand query using ENUM_MAPS and handle nested fields."""
        expanded_query = {}
        for field, value in query.items():
            if isinstance(value, dict):
                expanded_query[field] = self._expand_query(value)
            elif field in self.ENUM_MAPS and value in self.ENUM_MAPS[field]:
                expanded_query[field] = {"$in": self.ENUM_MAPS[field][value]}
            # Handle nested user_state queries
            elif field == "travel_history" and isinstance(value, str):
                # Convert to array contains query
                expanded_query[f"travel_history.{value}"] = {"$exists": True}
            else:
                expanded_query[field] = value
        return expanded_query

    def store_conversation(self, user_input: str, assistant_response: str, entities: List[str] = None, semantic_tags: List[str] = None):
        """Store a conversation turn in the database."""
        conversation_doc = {
            "user_id": self.username,
            "timestamp": datetime.now(timezone.utc),
            "user_input": user_input,
            "assistant_response": assistant_response,
            "entities": entities or [],
            "semantic_tags": semantic_tags or [],
            "sentiment": "neutral"  # Could be enhanced with sentiment analysis
        }
        
        collection = self.get_collection("conversations")
        result = collection.insert_one(conversation_doc)
        logger.info(f"Stored conversation with ID: {result.inserted_id}")
        return result.inserted_id

    def process_and_store_data(self, fresh_data: Dict[str, Any]):
        """Store new information from curator's output."""
        logger.info("Storing fresh data from curator...")
        now_timestamp = datetime.now(timezone.utc)
        stored_counts = {}

        try:
            # Store entities
            if "entities" in fresh_data and fresh_data["entities"]:
                collection = self.get_collection("entities")
                for entity in fresh_data["entities"]:
                    entity["user_id"] = self.username
                    entity["timestamp"] = now_timestamp
                result = collection.insert_many(fresh_data["entities"])
                stored_counts["entities"] = len(result.inserted_ids)

            # Store events
            if "events" in fresh_data and fresh_data["events"]:
                collection = self.get_collection("events")
                for event in fresh_data["events"]:
                    event["user_id"] = self.username
                    event["timestamp"] = now_timestamp
                result = collection.insert_many(fresh_data["events"])
                stored_counts["events"] = len(result.inserted_ids)

            collection = self.get_collection("user_state")
            update_payload = {}

            # Handle user_state_updates with nested structure support
            if "user_state_updates" in fresh_data and fresh_data["user_state_updates"]:
                for key, value in fresh_data["user_state_updates"].items():
                    if key == "context_flags" and isinstance(value, list):
                        # Append to existing flags array
                        update_payload.setdefault("$addToSet", {})["context_flags"] = {"$each": value}
                    elif key in ["active_projects", "preferences"] and isinstance(value, dict):
                        # Merge nested objects
                        for subkey, subvalue in value.items():
                            update_payload[f"{key}.{subkey}"] = subvalue
                    else:
                        update_payload[key] = value

            # Handle the new key_value_facts
            if "key_value_facts" in fresh_data and fresh_data["key_value_facts"]:
                for fact in fresh_data["key_value_facts"]:
                    update_payload[fact["key"]] = fact["value"]

            # If there's anything to update, perform database operation
            if update_payload:
                update_payload["last_updated"] = now_timestamp
                
                # Split $addToSet operations from $set operations
                set_operations = {k: v for k, v in update_payload.items() if not k.startswith("$")}
                add_operations = update_payload.get("$addToSet", {})
                
                update_doc = {}
                if set_operations:
                    update_doc["$set"] = set_operations
                if add_operations:
                    update_doc["$addToSet"] = add_operations
                
                result = collection.update_one(
                    {"user_id": self.username},
                    update_doc,
                    upsert=True
                )
                stored_counts["user_state"] = "updated" if result.modified_count > 0 else "created"

            logger.info(f"Storage complete: {stored_counts}")
            
        except Exception as e:
            logger.error(f"Error storing data: {e}")
            raise

    def retrieve_context(self, retrieval_queries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute queries to fetch relevant context."""
        logger.info("Retrieving context from database...")
        context_results = {}
        
        # Sort by priority (highest first)
        sorted_queries = sorted(retrieval_queries, key=lambda q: q.get("priority", 0), reverse=True)

        for item in sorted_queries:
            purpose = item.get("purpose", "unknown_purpose")
            collection_name = item.get("collection")
            query = item.get("query", {})
            timeframe = item.get("timeframe")

            if not collection_name:
                logger.warning(f"Skipping query '{purpose}' - missing collection")
                continue

            try:
                collection = self.get_collection(collection_name)

                # Expand and enhance query
                final_query = self._expand_query(query)
                
                # Add user_id to all queries
                final_query["user_id"] = self.username
                
                # Add timeframe if specified
                if timeframe and timeframe not in ["all", "all_time"]:
                    timeframe_query = self._get_timeframe_query(timeframe)
                    if "timestamp" in timeframe_query and "timestamp" not in final_query:
                        final_query.update(timeframe_query)

                # Execute query with limits and sorting
                cursor = collection.find(final_query)
                cursor = cursor.sort("timestamp", DESCENDING).limit(item.get("limit", 10))
                
                results = list(cursor)
                context_results[purpose] = results
                
                logger.info(f"Query '{purpose}': {len(results)} results")
                
            except Exception as e:
                logger.error(f"Error executing query '{purpose}': {e}")
                context_results[purpose] = []

            if context_results[purpose] is None:
                context_results[purpose] = 'No results found'                
        return context_results
    
    def retrieve_from_conversations(self, entities: List[str], semantic_tags: List[str], timeframe: str = "recent", limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve relevant conversations based on entities, semantic tags, and timeframe."""
        collection = self.get_collection("conversations")
        query = {"user_id": self.username}

        if entities:
            query["entities"] = {"$in": entities}
        if semantic_tags:
            query["semantic_tags"] = {"$in": semantic_tags}
        
        if timeframe and timeframe not in ["all", "all_time"]:
            timeframe_query = self._get_timeframe_query(timeframe)
            if "timestamp" in timeframe_query:
                query.update(timeframe_query)

        try:
            cursor = collection.find(query)
            cursor = cursor.sort("timestamp", DESCENDING).limit(limit)
            results = list(cursor)
            logger.info(f"Retrieved {len(results)} conversations matching criteria")
            return results
        except Exception as e:
            logger.error(f"Error retrieving conversations: {e}")
            return []

class CuratorHandler:
    """Orchestrates interaction between curator output and database."""
    
    def __init__(self, db_handler: CarlosDatabaseHandler):
        self.db_handler = db_handler

    def process_curator_output(self, curator_output: Dict[str, Any]) -> Dict[str, Any]:
        """Process complete curator output."""
        logger.info("Processing curator output...")
        
        # Store fresh data
        if "fresh_data_to_store" in curator_output and curator_output["fresh_data_to_store"]:
            self.db_handler.process_and_store_data(curator_output["fresh_data_to_store"])
        
        # Retrieve context
        retrieved_context = {}
        if "context_retrieval_queries" in curator_output and curator_output["context_retrieval_queries"]:
            retrieved_context = self.db_handler.retrieve_context(curator_output["context_retrieval_queries"])

        return retrieved_context

class MongoJSONEncoder(json.JSONEncoder):
    """
    JSONEncoder subclass that handles ObjectId and datetime objects.
    """
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)

class Carlos:
    """Carlos is a conversational AI system that interacts with users, processes messages, and retrieves information from a MongoDB database."""
    curator_schema = "" 
    curator_system_prompt = ""
    thinker_schema = ""
    thinker_system_prompt = ""
    response_generator_schema = ""
    response_generator_system_prompt = ""
    
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, mongo_uri: Optional[str] = None, api_endpoint: Optional[str] = None):
        """Initialize Carlos with MongoDB client and API endpoint."""
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI", "mongodb://localhost:27017/carlos")
        self.api_endpoint = api_endpoint or os.getenv("API_ENDPOINT", "http://192.168.50.202:1234")
    
        self.username = username or os.getenv("CARLOS_USERNAME", "test_user")
        self.password = password or os.getenv("CARLOS_PASSWORD", "foobar")
        
        self.db_handler = CarlosDatabaseHandler(self.mongo_uri, username)
        self.curator_handler = CuratorHandler(self.db_handler)

        # Load systems prompts and schemas
        try:
            with open("promts/curator_schema.json", "r") as f:
                self.curator_schema = json.loads(f.read())
            with open("promts/curator_system_prompt.txt", "r") as f:
                self.curator_system_prompt = f.read()
            with open("promts/thinker_schema.json", "r") as f:
                self.thinker_schema = json.loads(f.read())
            with open("promts/thinker_system_prompt.txt", "r") as f:
                self.thinker_system_prompt = f.read()
            with open("promts/response_generator_schema.json", "r") as f:
                self.response_generator_schema = json.loads(f.read())
            with open("promts/response_generator_system_prompt.txt", "r") as f:
                self.response_generator_system_prompt = f.read()
            logger.info("Loaded system prompts and schemas successfully")
        except Exception as e:
            logger.error(f"Error loading prompts/schemas: {e}")
            raise   

    def _api_talk(self, message: str, url: str) -> dict:
        """Send Message to API endpoint and return response."""
        headers = {
            "Content-Type": "application/json"
        }
        response = requests.post(f"{self.api_endpoint}/{url}", headers=headers, json=message)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"API error: {response.status_code} - {response.text}")

    def _curate(self, message: str) -> dict[str, Any]:
        """Send Message to curator model"""
        curator_message = {
            "model": "carlos",
            "messages": [
                {"role": "system", "content": self.curator_system_prompt},
                {"role": "user", "content": message}
            ],
            "response_format": self.curator_schema,
            "temperature": 0,
            "max_tokens": -1,
            "stream": False
        }
        response = self._api_talk(curator_message, url="v1/chat/completions")
        logger.debug(f"Curator response: {response}")
        fresh_data_to_store, context_retrieval_queries, context_focus, curiosity_analysis = self._parse_curator_response(response)
        handler_output = self.curator_handler.process_curator_output({
            "fresh_data_to_store": fresh_data_to_store,
            "context_retrieval_queries": context_retrieval_queries,
        })

        from_conversations = self.db_handler.retrieve_from_conversations(
            entities=handler_output.get("entities", []),
            semantic_tags=handler_output.get("semantic_tags", []),
            timeframe="recent",
            limit=5
        )
        
        return {
            "context_focus": context_focus,
            "curiosity_analysis": curiosity_analysis,
            "retrieved_context": handler_output,
            "from_conversations": from_conversations
        }
    
    def _think(self, message: str, curator_analysis: dict) -> tuple[dict[str, Any], bool]:
        """Think about the curator provided data. return true if we need to query curator."""
        thinker_message = {
            "model": "carlos",
            "messages": [
                {"role": "system", "content": self.thinker_system_prompt},
                {"role": "system", "content": "Curator data: " + json.dumps(curator_analysis, cls=MongoJSONEncoder)},
                {"role": "user", "content": f"Orginal user message: {message}"}
            ],
            "response_format": self.thinker_schema,
            "temperature": 0,
            "max_tokens": -1,
            "stream": False
        }

        response = self._api_talk(thinker_message, url="v1/chat/completions")
        logger.debug(f"Thinker response: {response}")
        try:
            think_data = json.loads(response.get("choices", [{}])[0].get("message", {}).get("content", "{}"))
        except json.JSONDecodeError:
            logger.error("Failed to parse thinker response as JSON")
            return {}, False
        return think_data, False  # Flag lets add rethinking logic later
    
    def _build_response(self, think_data: dict[str, Any], message: str, timestamp: str) -> str:
        response_message = {
            "model": "carlos",
            "messages": [
                {"role": "system", "content": self.response_generator_system_prompt},
                {"role": "system", "content": "Thinker data: " + json.dumps(think_data, cls=MongoJSONEncoder)},
                {"role": "system", "content": f"Current time is {timestamp}"},
                {"role": "user", "content": f"Original user message: {message}"}
            ],
            "response_format": self.response_generator_schema,
            "temperature": 0.7,
        }
        response = self._api_talk(response_message, url="v1/chat/completions")
        if response.get("choices"):
            return response["choices"][0].get("message", {}).get("content", "")
        else:
            logger.error("Response generator returned no choices")
            return "I'm not sure how to respond to that right now."
        
    def _parse_curator_response(self, response: dict) -> tuple:
        """Parse the curator response and extract relevant data."""
        try:
            curator_analysis = json.loads(response.get("choices", [{}])[0].get("message", {}).get("content", ""))
        except json.JSONDecodeError:
            logger.error("Failed to parse curator response as JSON")
            return {}, [], {}, {}
        
        fresh_data_to_store = curator_analysis.get("fresh_data_to_store", {})
        context_retrieval_queries = curator_analysis.get("context_retrieval_queries", {})
        context_focus = curator_analysis.get("context_focus", {})
        curiosity_analysis = curator_analysis.get("curiosity_analysis", {})
        return fresh_data_to_store, context_retrieval_queries, context_focus, curiosity_analysis
    
    def _process_big_input(self, message: str) -> dict[str, Any]:
        """Split big input into smaller chunks if needed."""
        max_chunk_size = 2000
        if len(message) <= max_chunk_size:
            return self._curate(message)
        # Split by sentences for better coherence
        sentences = re.split(r'(?<=[.!?]) +', message)
        chunks = []
        current_chunk = ""
        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                current_chunk += (" " if current_chunk else "") + sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence
        if current_chunk:
            chunks.append(current_chunk)
        combined_analysis = {
            "context_focus": {},
            "curiosity_analysis": {},
            "retrieved_context": {
                "entities": [],
                "semantic_tags": []
            }
        }

        for chunk in chunks:
            chunk_analysis = self._curate(chunk)
            # Combine retrieved context
            for key in ["entities", "semantic_tags"]:
                combined_analysis["retrieved_context"][key].extend(chunk_analysis.get("retrieved_context", {}).get(key, []))
            # Merge context_focus and curiosity_analysis (simple overwrite for now)
            combined_analysis["context_focus"].update(chunk_analysis.get("context_focus", {}))
            combined_analysis["curiosity_analysis"].update(chunk_analysis.get("curiosity_analysis", {}))

        # Deduplicate entities and semantic tags
        combined_analysis["retrieved_context"]["entities"] = list(set(combined_analysis["retrieved_context"]["entities"]))
        combined_analysis["retrieved_context"]["semantic_tags"] = list(set(combined_analysis["retrieved_context"]["semantic_tags"]))
        return combined_analysis

    def chat(self, message: str) -> str:
        """Process a chat message and return a response."""
        timestamp = datetime.now().isoformat()
        logger.info(f"Received message at {timestamp}: {message}")
        message += f" [{timestamp}]"
        message += f" [username: {self.username}]"

        curator_analysis = self._process_big_input(message)
        think_data, needs_curator = self._think(message, curator_analysis)
        if needs_curator:
            logger.info("Rethinking required, querying curator again...")
            # fire up curator again with thinker data

        response_text = self._build_response(think_data, message, timestamp)
        # Store the conversation turn
        self.db_handler.store_conversation(
            user_input=message,
            assistant_response=response_text,
            entities=curator_analysis.get("retrieved_context", {}).get("entities", []),
            semantic_tags=curator_analysis.get("retrieved_context", {}).get("semantic_tags", [])
        )

        return response_text

    def get_debug_info(self, message: str) -> Dict[str, Any]:
        response = requests.post(f"{self.api_endpoint}/debug", json={"message": message})
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Debug API error: {response.status_code} - {response.text}")

        

if __name__ == "__main__":
    carlos = Carlos()

    print("Carlos initialized with MongoDB client and API endpoint.")