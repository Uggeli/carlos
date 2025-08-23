from datetime import datetime, timedelta, timezone
import json
from typing import Any, Dict, List
from bson import ObjectId
from pymongo import DESCENDING, MongoClient, TEXT
import logging
logger = logging.getLogger(__name__)


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