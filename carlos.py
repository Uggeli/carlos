import re
import requests
from datetime import datetime
import os
import json
from typing import Optional, Dict, Any
from CarlosDatabase import CarlosDatabaseHandler, MongoJSONEncoder, CuratorHandler
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
        max_chunk_size = 4000
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
    
    def chat_stream(self, message: str, timestamp: str):
        """Generator to stream chat response."""
        timestamp = datetime.now().isoformat()
        logger.info(f"Received message at {timestamp}: {message}")
        message += f" [{timestamp}]"
        message += f" [username: {self.username}]"
        yield "event: status\ndata: {\"status\": \"thinking\"}\n\n"
        curator_analysis = self._process_big_input(message)
        yield "event: status\ndata: {\"status\": \"formulating\"}\n\n"
        think_data, needs_curator = self._think(message, curator_analysis)
        yield "event: status\ndata: {\"status\": \"pondering\"}\n\n"
        if needs_curator:
            logger.info("Rethinking required, querying curator again...")
            # fire up curator again with thinker data

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
            "stream": True,
        }

        emote_pattern = re.compile(r"(\[.*?\])")

        with requests.post(f"{self.api_endpoint}/v1/chat/completions", json=response_message, stream=True) as response:
            response.raise_for_status()
            full_response = ""
            for line in response.iter_lines():
                if not line:
                    continue
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[5:].strip()
                    if json_str == "[DONE]":
                        break
                    try:
                        data = json.loads(json_str)
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content_chunk = delta.get("content", "")
                        if content_chunk:
                            full_response += content_chunk
                            parts = emote_pattern.split(full_response)
                            for part in parts[:-1]:
                                if emote_pattern.match(part):
                                    emote_name = part.strip("[]")
                                    yield f"event: emote\ndata: {{\"emote\": \"{emote_name}\"}}\n\n"
                                else:
                                    yield f"event: message\ndata: {{\"message\": \"{part}\"}}\n\n"
                            full_response = parts[-1]
                    except json.JSONDecodeError:
                        logger.error(f"Failed to decode JSON from stream: {json_str}")
            if full_response:
                yield f"event: message\ndata: {{\"message\": \"{full_response}\"}}\n\n"
        
        try:
            final_response_data = json.loads(full_response)
            assistant_response = final_response_data.get("response", full_response)
        except json.JSONDecodeError:
            assistant_response = "Error: Failed to parse final response."
        # Store the conversation turn
        self.db_handler.store_conversation(
            user_input=message,
            assistant_response=assistant_response,
            entities=curator_analysis.get("retrieved_context", {}).get("entities", []),
            semantic_tags=curator_analysis.get("retrieved_context", {}).get("semantic_tags", [])
        )

    def store_conversation(self, user_input: str, assistant_response: str, entities: list[str], semantic_tags: list[str]) -> None:
        """Public method to store a conversation turn."""
        self.db_handler.store_conversation(user_input, assistant_response, entities, semantic_tags)

    def get_debug_info(self, message: str) -> Dict[str, Any]:
        response = requests.post(f"{self.api_endpoint}/debug", json={"message": message})
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Debug API error: {response.status_code} - {response.text}")

        

if __name__ == "__main__":
    carlos = Carlos()

    print("Carlos initialized with MongoDB client and API endpoint.")