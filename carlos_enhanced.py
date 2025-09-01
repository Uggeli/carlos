"""
Carlos AI Assistant - Refactored Implementation
A conversational AI system implementing the Recursive Shard Architecture

This module provides a high-performance, type-safe implementation of the Carlos AI assistant
with proper async patterns, comprehensive error handling, and clean architecture.

Author: Enhanced by AI Assistant
Version: 2.0.0
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import (
    Any, Dict, List, Optional, Union, AsyncGenerator, 
    TypeVar, Generic, Protocol, runtime_checkable
)
from contextlib import asynccontextmanager
from enum import Enum

import httpx
from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

# Configure logging with proper formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('carlos.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

# Type definitions
T = TypeVar('T')
MessageDict = Dict[str, Any]
EmbeddingVector = List[float]

class MessageType(Enum):
    """Enumeration of message types in the system."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    
class ResponseStatus(Enum):
    """Enumeration of response statuses."""
    THINKING = "thinking"
    SEARCHING = "searching" 
    EMBEDDING = "embedding"
    CHUNKING = "chunking"
    RESPONSE = "response"
    EMOTE = "emote"
    DONE = "[DONE]"
    ERROR = "error"


@dataclass
class CarlosConfig:
    """Configuration for Carlos AI Assistant."""
    api_endpoint: str = "http://localhost:1234"
    db_uri: str = "mongodb://localhost:27017"
    user_name: str = "default_user"
    embedding_model: str = "text-embedding-nomic-embed-text-v1.5"
    max_thinker_loops: int = 15
    chunk_size: int = 4000
    search_limit: int = 5
    request_timeout: int = 60
    
    @classmethod
    def from_environment(cls) -> CarlosConfig:
        """Create configuration from environment variables."""
        return cls(
            api_endpoint=os.getenv("CARLOS_API_ENDPOINT", cls.api_endpoint),
            db_uri=os.getenv("CARLOS_DB_URI", cls.db_uri),
            user_name=os.getenv("CARLOS_USER_NAME", cls.user_name),
            embedding_model=os.getenv("CARLOS_EMBEDDING_MODEL", cls.embedding_model),
            max_thinker_loops=int(os.getenv("CARLOS_MAX_THINKER_LOOPS", str(cls.max_thinker_loops))),
            chunk_size=int(os.getenv("CARLOS_CHUNK_SIZE", str(cls.chunk_size))),
            search_limit=int(os.getenv("CARLOS_SEARCH_LIMIT", str(cls.search_limit))),
            request_timeout=int(os.getenv("CARLOS_REQUEST_TIMEOUT", str(cls.request_timeout))),
        )


@dataclass
class StreamingChunk:
    """Represents a chunk of streaming response data."""
    status: ResponseStatus
    message: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class InteractionData:
    """Complete interaction data structure."""
    user_id: str
    user_message: str
    user_summary: str
    user_tags: List[str]
    user_embedding: EmbeddingVector
    agent_response: str
    response_summary: str
    response_tags: List[str]
    response_embedding: EmbeddingVector
    analysis: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CarlosError(Exception):
    """Base exception for Carlos-related errors."""
    pass

class ConfigurationError(CarlosError):
    """Raised when configuration is invalid."""
    pass

class DatabaseError(CarlosError):
    """Raised when database operations fail."""
    pass

class APIError(CarlosError):
    """Raised when external API calls fail."""
    pass


class MongoJSONEncoder(json.JSONEncoder):
    """Enhanced JSON encoder for MongoDB types with better error handling."""
    
    def default(self, obj: Any) -> Any:
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


@runtime_checkable
class Agent(Protocol):
    """Protocol defining the interface for all agents."""
    
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the agent's primary function."""
        ...


class LlmAgent(ABC):
    """
    Abstract base class for Language Model agents.
    
    Provides a clean, type-safe interface for interacting with LLM APIs
    with proper resource management and error handling.
    """
    
    def __init__(self, api_endpoint: str, model_name: str = 'carlos') -> None:
        self.api_endpoint = api_endpoint
        self.model_name = model_name
        self._client: Optional[httpx.AsyncClient] = None
    
    @asynccontextmanager
    async def _get_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """Get an async HTTP client with proper resource management."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0))
        
        try:
            yield self._client
        except Exception as e:
            logger.error(f"HTTP client error: {e}")
            raise APIError(f"HTTP client error: {e}") from e
    
    async def _call_llm(
        self,
        messages: List[MessageDict],
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = -1,
        stream: bool = False
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """
        Call the LLM API with comprehensive error handling.
        
        Args:
            messages: List of message dictionaries
            schema: Optional response format schema
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate (-1 for unlimited)
            stream: Whether to stream the response
            
        Returns:
            Parsed response dictionary or async generator for streaming
            
        Raises:
            APIError: When API call fails
        """
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        if schema:
            payload["response_format"] = schema
            
        headers = {"Content-Type": "application/json"}
        url = f"{self.api_endpoint}/v1/chat/completions"
        
        try:
            async with self._get_client() as client:
                if stream:
                    return self._stream_response(client, url, headers, payload)
                else:
                    return await self._get_response(client, url, headers, payload)
        except httpx.HTTPError as e:
            logger.error(f"LLM API call failed: {e}")
            raise APIError(f"LLM API call failed: {e}") from e
    
    async def _get_response(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get a non-streaming response from the API."""
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            logger.debug(f"Non-JSON content returned: {content[:100]}...")
            return {"response_text": content}
    
    async def _stream_response(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Stream response chunks from the API."""
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                    
                data_str = line
                if data_str.startswith("data:"):
                    data_str = data_str[len("data:"):].strip()
                    
                if not data_str or data_str == "[DONE]":
                    continue
                    
                try:
                    obj = json.loads(data_str)
                    choices = obj.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {}) or choices[0].get("message", {})
                        chunk = delta.get("content")
                        if chunk:
                            yield chunk
                except json.JSONDecodeError:
                    # Fallback to raw text
                    yield data_str
    
    async def close(self) -> None:
        """Close the HTTP client and clean up resources."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the agent's primary function."""
        pass


class CuratorAgent(LlmAgent):
    """
    Agent responsible for curating and analyzing incoming messages.
    
    The Curator acts as the information gathering mechanism, assessing
    information needs and constructing context for each interaction.
    """
    
    def __init__(self, api_endpoint: str, system_prompt: str, schema: Dict[str, Any]) -> None:
        super().__init__(api_endpoint)
        self.system_prompt = system_prompt
        self.schema = schema
    
    async def run(self, message: str, chunk: Optional[str] = None) -> tuple[List[Dict[str, Any]], List[str]]:
        """
        Curate the incoming message and return analysis.
        
        Args:
            message: The user's message to analyze
            chunk: Optional chunk information for long messages
            
        Returns:
            Tuple of (queries_to_execute, insights_to_store)
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": message}
        ]
        
        if chunk:
            messages.extend([
                {"role": "system", "content": "Long input split into chunks. Directive: Store all information for later synthesis."},
                {"role": "system", "content": f"Chunk info: {chunk}"}
            ])
        
        response = await self._call_llm(messages, schema=self.schema, temperature=0)
        return response.get("queries_to_execute", []), response.get("insights_to_store", [])


class ThinkerAgent(LlmAgent):
    """
    Agent responsible for deep analytical reasoning.
    
    The Thinker performs cognitive processing using internal dialogue
    and grounds analysis in facts vs assumptions.
    """
    
    def __init__(self, api_endpoint: str, system_prompt: str, schema: Dict[str, Any]) -> None:
        super().__init__(api_endpoint)
        self.system_prompt = system_prompt
        self.schema = schema
    
    async def run(self, message: str, context_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze the provided context and return insights.
        
        Args:
            message: Original user message
            context_data: Curator-provided context data
            
        Returns:
            Dictionary containing analysis results
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": f"Context data: {json.dumps(context_data, cls=MongoJSONEncoder)}"},
            {"role": "user", "content": f"Original user message: {message}"}
        ]
        
        return await self._call_llm(messages, schema=self.schema, temperature=0)


class GeneratorAgent(LlmAgent):
    """
    Agent responsible for generating natural language responses.
    
    The Generator translates analytical insights into empathetic,
    natural language with appropriate emotional formatting.
    """
    
    def __init__(self, api_endpoint: str, system_prompt: str, schema: Optional[Dict[str, Any]]) -> None:
        super().__init__(api_endpoint)
        self.system_prompt = system_prompt
        self.schema = schema
    
    async def run(self, message: str, context: Dict[str, Any], timestamp: str) -> str:
        """
        Generate a complete response based on analysis.
        
        Args:
            message: Original user message
            context: Analysis context from thinker
            timestamp: Current timestamp
            
        Returns:
            Generated response text
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": f"Analysis context: {json.dumps(context, cls=MongoJSONEncoder)}"},
            {"role": "system", "content": f"Current time: {timestamp}"},
            {"role": "user", "content": f"Original user message: {message}"}
        ]
        
        response = await self._call_llm(messages, schema=self.schema, temperature=0.7)
        return response.get("response_text", str(response))
    
    async def stream(self, message: str, context: Dict[str, Any], timestamp: str) -> AsyncGenerator[str, None]:
        """
        Stream response generation for real-time output.
        
        Args:
            message: Original user message
            context: Analysis context from thinker
            timestamp: Current timestamp
            
        Yields:
            Response chunks as they are generated
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": f"Analysis context: {json.dumps(context, cls=MongoJSONEncoder)}"},
            {"role": "system", "content": f"Current time: {timestamp}"},
            {"role": "user", "content": f"Original user message: {message}"}
        ]
        
        async for chunk in await self._call_llm(messages, schema=self.schema, temperature=0.7, stream=True):
            yield chunk


class SummarizerAgent(LlmAgent):
    """
    Agent responsible for creating summaries and tags.
    
    Enables semantic search and memory organization by generating
    concise summaries and relevant tags for content.
    """
    
    def __init__(self, api_endpoint: str, system_prompt: str, schema: Dict[str, Any]) -> None:
        super().__init__(api_endpoint)
        self.system_prompt = system_prompt
        self.schema = schema
    
    async def run(self, text: str) -> tuple[str, List[str]]:
        """
        Generate summary and tags for the given text.
        
        Args:
            text: Text to summarize and tag
            
        Returns:
            Tuple of (summary, tags)
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": text}
        ]
        
        response = await self._call_llm(messages, schema=self.schema, temperature=0)
        return response.get("summary", ""), response.get("tags", [])


class CarlosDatabaseHandler:
    """
    Enhanced database handler with proper error handling and type safety.
    
    Manages all MongoDB operations with connection pooling, proper indexing,
    and comprehensive error handling.
    """
    
    def __init__(self, db_uri: str, user_name: str) -> None:
        self.db_uri = db_uri
        self.user_name = user_name
        
        try:
            self.client = MongoClient(db_uri)
            self.db: Database = self.client[f"carlos_{user_name}"]
            
            # Initialize collections with proper typing
            self.messages_col: Collection = self.db.messages
            self.responses_col: Collection = self.db.responses
            self.analyses_col: Collection = self.db.analyses
            self.interactions_col: Collection = self.db.interactions
            self.insights_col: Collection = self.db.insights
            self.cassandra_flags_col: Collection = self.db.cassandra_flags
            
            self._create_indexes()
            logger.info(f"Database initialized for user: {user_name}")
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}") from e
    
    def _create_indexes(self) -> None:
        """Create necessary indexes for optimal query performance."""
        try:
            # Create indexes for efficient querying
            self.messages_col.create_index([("tags", 1), ("timestamp", -1)])
            self.responses_col.create_index([("tags", 1), ("timestamp", -1)])
            self.interactions_col.create_index([("tags", 1), ("timestamp", -1)])
            self.interactions_col.create_index([("user_id", 1), ("timestamp", -1)])
            
            logger.debug("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Index creation failed: {e}")
    
    def store_user_message(
        self, 
        message: str, 
        summary: str, 
        tags: List[str], 
        embedding: EmbeddingVector
    ) -> str:
        """Store a user message with metadata."""
        try:
            doc = {
                "user_id": self.user_name,
                "message": message,
                "summary": summary,
                "tags": tags,
                "embedding": embedding,
                "timestamp": datetime.now(timezone.utc)
            }
            result = self.messages_col.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store user message: {e}")
            raise DatabaseError(f"Failed to store user message: {e}") from e
    
    def store_agent_response(
        self, 
        message: str, 
        summary: str, 
        tags: List[str], 
        embedding: EmbeddingVector
    ) -> str:
        """Store an agent response with metadata."""
        try:
            doc = {
                "user_id": self.user_name,
                "message": message,
                "summary": summary,
                "tags": tags,
                "embedding": embedding,
                "timestamp": datetime.now(timezone.utc)
            }
            result = self.responses_col.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store agent response: {e}")
            raise DatabaseError(f"Failed to store agent response: {e}") from e
    
    def store_analysis(self, analysis_data: Dict[str, Any]) -> str:
        """Store analysis data with timestamp."""
        try:
            doc = {
                **analysis_data,
                "timestamp": datetime.now(timezone.utc)
            }
            result = self.analyses_col.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store analysis: {e}")
            raise DatabaseError(f"Failed to store analysis: {e}") from e
    
    def store_interaction(self, interaction_data: InteractionData) -> str:
        """Store complete interaction data."""
        try:
            # Store individual components
            user_message_id = self.store_user_message(
                interaction_data.user_message,
                interaction_data.user_summary,
                interaction_data.user_tags,
                interaction_data.user_embedding
            )
            
            agent_response_id = self.store_agent_response(
                interaction_data.agent_response,
                interaction_data.response_summary,
                interaction_data.response_tags,
                interaction_data.response_embedding
            )
            
            analysis_id = self.store_analysis(interaction_data.analysis)
            
            # Store interaction document
            all_tags = interaction_data.user_tags + interaction_data.response_tags
            doc = {
                "user_id": interaction_data.user_id,
                "timestamp": interaction_data.timestamp,
                "tags": all_tags,
                "user_message_id": ObjectId(user_message_id),
                "agent_response_id": ObjectId(agent_response_id),
                "analysis_id": ObjectId(analysis_id),
                "embedding": interaction_data.user_embedding
            }
            
            result = self.interactions_col.insert_one(doc)
            return str(result.inserted_id)
            
        except Exception as e:
            logger.error(f"Failed to store interaction: {e}")
            raise DatabaseError(f"Failed to store interaction: {e}") from e
    
    def search(
        self, 
        tags: List[str], 
        query_vector: EmbeddingVector, 
        time_filter: str = '', 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search using tags and vector similarity.
        
        Uses MongoDB aggregation pipeline with manual cosine similarity calculation
        for compatibility with local MongoDB instances.
        """
        if not query_vector:
            logger.warning("Empty query vector provided, falling back to tag search")
            return self.search_by_tags(tags, time_filter, top_k)
        
        try:
            pipeline = [
                # Fast initial filtering using tags index
                {"$match": {"tags": {"$in": tags}}},
                
                # Calculate cosine similarity manually
                {
                    "$addFields": {
                        "similarity": {
                            "$let": {
                                "vars": {
                                    "dotProduct": {
                                        "$reduce": {
                                            "input": {"$range": [0, {"$size": "$embedding"}]},
                                            "initialValue": 0,
                                            "in": {
                                                "$add": [
                                                    "$$value",
                                                    {
                                                        "$multiply": [
                                                            {"$arrayElemAt": ["$embedding", "$$this"]},
                                                            {"$arrayElemAt": [query_vector, "$$this"]}
                                                        ]
                                                    }
                                                ]
                                            }
                                        }
                                    },
                                    "normA": {
                                        "$sqrt": {
                                            "$reduce": {
                                                "input": "$embedding",
                                                "initialValue": 0,
                                                "in": {"$add": ["$$value", {"$pow": ["$$this", 2]}]}
                                            }
                                        }
                                    },
                                    "normB": {
                                        "$sqrt": {
                                            "$reduce": {
                                                "input": query_vector,
                                                "initialValue": 0,
                                                "in": {"$add": ["$$value", {"$pow": ["$$this", 2]}]}
                                            }
                                        }
                                    }
                                },
                                "in": {
                                    "$divide": [
                                        "$$dotProduct",
                                        {"$multiply": ["$$normA", "$$normB"]}
                                    ]
                                }
                            }
                        }
                    }
                },
                
                # Sort by similarity and limit results
                {"$sort": {"similarity": -1}},
                {"$limit": top_k},
                
                # Join with message and response data
                {
                    "$lookup": {
                        "from": "messages",
                        "localField": "user_message_id",
                        "foreignField": "_id",
                        "as": "user_message_data"
                    }
                },
                {
                    "$lookup": {
                        "from": "responses",
                        "localField": "agent_response_id",
                        "foreignField": "_id",
                        "as": "agent_response_data"
                    }
                },
                {
                    "$lookup": {
                        "from": "analyses",
                        "localField": "analysis_id",
                        "foreignField": "_id",
                        "as": "analysis_data"
                    }
                },
                
                # Project final output
                {
                    "$project": {
                        "_id": 0,
                        "interaction_id": "$_id",
                        "timestamp": 1,
                        "tags": 1,
                        "user_id": 1,
                        "similarity": 1,
                        "user_message_summary": {"$arrayElemAt": ["$user_message_data.summary", 0]},
                        "agent_response_summary": {"$arrayElemAt": ["$agent_response_data.summary", 0]},
                        "analysis": {"$arrayElemAt": ["$analysis_data", 0]}
                    }
                }
            ]
            
            results = list(self.interactions_col.aggregate(pipeline))
            
            if not results:
                # Fallback to message search
                logger.debug("No interaction results found, falling back to message search")
                results = list(
                    self.messages_col.find({"tags": {"$in": tags}})
                    .sort("timestamp", -1)
                    .limit(top_k)
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Search operation failed: {e}")
            raise DatabaseError(f"Search operation failed: {e}") from e
    
    def search_by_tags(
        self, 
        tags: List[str], 
        time_filter: str = '', 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for relevant messages using only tags."""
        try:
            query = {"tags": {"$in": tags}}
            
            # Add time filter if specified
            if time_filter:
                # Implementation for time filtering would go here
                pass
            
            results = list(
                self.interactions_col.find(query)
                .sort("timestamp", -1)
                .limit(top_k)
            )
            
            if not results:
                results = list(
                    self.messages_col.find(query)
                    .sort("timestamp", -1)
                    .limit(top_k)
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Tag search failed: {e}")
            raise DatabaseError(f"Tag search failed: {e}") from e
    
    def close(self) -> None:
        """Close the database connection."""
        try:
            self.client.close()
            logger.info("Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")


class Carlos:
    """
    Main Carlos AI Assistant class implementing the Recursive Shard Architecture.
    
    This class orchestrates the multi-agent pipeline with proper async patterns,
    comprehensive error handling, and optimal resource management.
    """
    
    def __init__(self, config: Optional[CarlosConfig] = None) -> None:
        """
        Initialize Carlos with configuration.
        
        Args:
            config: Configuration object. If None, loads from environment.
        """
        self.config = config or CarlosConfig.from_environment()
        
        # Initialize database handler
        self.db_handler = CarlosDatabaseHandler(self.config.db_uri, self.config.user_name)
        
        # Load prompts and schemas
        self._load_prompts_and_schemas()
        
        # Initialize agents
        self._initialize_agents()
        
        # Response formatting state
        self._reset_formatting_state()
        
        logger.info(f"Carlos initialized for user: {self.config.user_name}")
    
    def _load_prompts_and_schemas(self) -> None:
        """Load system prompts and response schemas from files."""
        try:
            base_path = os.path.dirname(os.path.abspath(__file__))
            
            # Load prompts
            prompts_path = os.path.join(base_path, 'prompts')
            with open(os.path.join(prompts_path, 'curator_system_prompt.txt'), 'r', encoding='utf-8') as f:
                self.curator_prompt = f.read()
            with open(os.path.join(prompts_path, 'thinker_system_prompt.txt'), 'r', encoding='utf-8') as f:
                self.thinker_prompt = f.read()
            with open(os.path.join(prompts_path, 'response_generator_system_prompt.txt'), 'r', encoding='utf-8') as f:
                self.generator_prompt = f.read()
            with open(os.path.join(prompts_path, 'summarizer_system_prompt.txt'), 'r', encoding='utf-8') as f:
                self.summarizer_prompt = f.read()
            
            # Load schemas
            schemas_path = os.path.join(base_path, 'schemas')
            with open(os.path.join(schemas_path, 'curator_schema.json'), 'r', encoding='utf-8') as f:
                self.curator_schema = json.loads(f.read())
            with open(os.path.join(schemas_path, 'thinker_schema.json'), 'r', encoding='utf-8') as f:
                self.thinker_schema = json.loads(f.read())
            with open(os.path.join(schemas_path, 'response_generator_schema.json'), 'r', encoding='utf-8') as f:
                self.generator_schema = json.loads(f.read())
            with open(os.path.join(schemas_path, 'summarizer_schema.json'), 'r', encoding='utf-8') as f:
                self.summarizer_schema = json.loads(f.read())
            
            logger.debug("Prompts and schemas loaded successfully")
            
        except FileNotFoundError as e:
            logger.error(f"Required prompt or schema file not found: {e}")
            raise ConfigurationError(f"Required prompt or schema file not found: {e}") from e
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in schema file: {e}")
            raise ConfigurationError(f"Invalid JSON in schema file: {e}") from e
    
    def _initialize_agents(self) -> None:
        """Initialize all agent instances."""
        try:
            self.curator_agent = CuratorAgent(
                self.config.api_endpoint, 
                self.curator_prompt, 
                self.curator_schema
            )
            self.thinker_agent = ThinkerAgent(
                self.config.api_endpoint, 
                self.thinker_prompt, 
                self.thinker_schema
            )
            self.generator_agent = GeneratorAgent(
                self.config.api_endpoint, 
                self.generator_prompt, 
                self.generator_schema
            )
            self.summarizer_agent = SummarizerAgent(
                self.config.api_endpoint, 
                self.summarizer_prompt, 
                self.summarizer_schema
            )
            
            logger.debug("All agents initialized successfully")
            
        except Exception as e:
            logger.error(f"Agent initialization failed: {e}")
            raise ConfigurationError(f"Agent initialization failed: {e}") from e
    
    def _reset_formatting_state(self) -> None:
        """Reset response formatting state variables."""
        self.in_response = False
        self.response = ''
        self.in_tone = False
        self.tone = ''
        self.in_emote = False
        self.emote = ''
        self.full_text = ''
    
    async def _fetch_embeddings(self, text: str) -> EmbeddingVector:
        """
        Fetch embeddings for the given text with proper error handling.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or empty list if failed
        """
        payload = {
            "model": self.config.embedding_model,
            "input": text
        }
        headers = {"Content-Type": "application/json"}
        
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.config.request_timeout)) as client:
                response = await client.post(
                    f"{self.config.api_endpoint}/v1/embeddings",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                return result.get("data", [{}])[0].get("embedding", [])
                
        except httpx.HTTPError as e:
            logger.error(f"Embedding API request failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in embedding fetch: {e}")
            return []
    
    async def _chunk_message(self, message: str) -> tuple[str, List[str]]:
        """
        Handle large messages by chunking and summarizing.
        
        Args:
            message: Large message to chunk
            
        Returns:
            Tuple of (summary, tags) for the complete message
        """
        chunks = [
            message[i:i + self.config.chunk_size] 
            for i in range(0, len(message), self.config.chunk_size)
        ]
        
        chunk_summaries = []
        all_tags = []
        
        for i, chunk in enumerate(chunks):
            try:
                summary, tags = await self.summarizer_agent.run(chunk)
                chunk_summaries.append(f"Chunk {i+1}: {summary}")
                all_tags.extend(tags)
            except Exception as e:
                logger.error(f"Failed to process chunk {i+1}: {e}")
                chunk_summaries.append(f"Chunk {i+1}: Processing failed")
        
        # Create overall summary
        combined_summary = " | ".join(chunk_summaries)
        unique_tags = list(set(all_tags))
        
        return combined_summary, unique_tags
    
    def _format_with_emotes(self, text: str) -> Optional[StreamingChunk]:
        """
        Format streaming text with emote detection and processing.
        
        Args:
            text: Raw text chunk from stream
            
        Returns:
            Formatted streaming chunk or None if processing
        """
        self.full_text += text
        
        # Handle JSON response parsing
        if '{' in text and not self.in_response:
            if '"response_text"' in self.full_text:
                self.in_response = True
                # Find the start of the actual response text
                start_pattern = r'"response_text":\s*"'
                match = re.search(start_pattern, self.full_text)
                if match:
                    response_start = match.end()
                    actual_text = self.full_text[response_start:]
                    return self._process_response_text(actual_text)
        
        if self.in_response:
            return self._process_response_text(text)
        
        # Handle emote detection
        if '[' in text and not self.in_emote:
            self.in_emote = True
            self.emote = text
            return None
        
        if self.in_emote:
            if ']' in text:
                self.emote += text
                emote_text = self.emote.strip()
                self.emote = ""
                self.in_emote = False
                # Clean up emote text
                emote_text = re.sub(r'[\.,;:!?]+$', '', emote_text)
                return StreamingChunk(
                    status=ResponseStatus.EMOTE,
                    message=emote_text
                )
            else:
                self.emote += text
                return None
        
        # Default response text
        if len(self.full_text) >= len('{\n  "response":}') and not self.full_text.endswith('}'):
            return StreamingChunk(
                status=ResponseStatus.RESPONSE,
                message=text
            )
        
        return None
    
    def _process_response_text(self, text: str) -> Optional[StreamingChunk]:
        """Process response text and handle JSON parsing."""
        # Remove JSON artifacts
        cleaned_text = text.replace('\\"', '"').replace('\\n', '\n')
        
        # Check for end of JSON
        if '"}' in text:
            self.in_response = False
            # Extract text before the closing JSON
            end_pos = text.find('"}')
            if end_pos > 0:
                actual_text = text[:end_pos]
                return StreamingChunk(
                    status=ResponseStatus.RESPONSE,
                    message=actual_text
                )
        
        return StreamingChunk(
            status=ResponseStatus.RESPONSE,
            message=cleaned_text
        )
    
    async def stream_response(self, message: str) -> AsyncGenerator[StreamingChunk, None]:
        """
        Process a message and stream the response with full pipeline execution.
        
        Args:
            message: User message to process
            
        Yields:
            StreamingChunk objects containing response data
        """
        self._reset_formatting_state()
        
        try:
            # Step 1: Message chunking and summarization
            yield StreamingChunk(ResponseStatus.CHUNKING, "Carlos is thinking...")
            
            if len(message) > self.config.chunk_size:
                summary, tags = await self._chunk_message(message)
                logger.debug(f"Message chunked - Summary: {summary[:100]}..., Tags: {tags}")
            else:
                summary, tags = await self.summarizer_agent.run(message)
                logger.debug(f"Message summarized - Summary: {summary}, Tags: {tags}")
            
            # Step 2: Embedding generation
            yield StreamingChunk(ResponseStatus.EMBEDDING, "Hmm, let me think about that...")
            
            import random
            if tags:
                yield StreamingChunk(
                    ResponseStatus.SEARCHING, 
                    f"{random.choice(tags)}... let me see what I can find."
                )
            else:
                yield StreamingChunk(ResponseStatus.SEARCHING, "Interesting topic... let me see what I can find.")
            
            query_vector = await self._fetch_embeddings(summary)
            search_results = self.db_handler.search(tags, query_vector, top_k=self.config.search_limit)
            logger.debug(f"Search completed - Found {len(search_results)} results")
            
            # Step 3: Iterative thinking loop
            thinker_context = {
                "search_results": search_results,
                "reasoning": [],
                "summary": summary,
                "tags": tags
            }
            
            for loop_count in range(self.config.max_thinker_loops):
                try:
                    thinker_response = await self.thinker_agent.run(message, thinker_context)
                    logger.debug(f"Thinker loop {loop_count + 1}: {thinker_response}")
                    
                    is_context_sufficient = thinker_response.get("is_context_sufficient", True)
                    information_request = thinker_response.get("information_request", "")
                    reasoning = thinker_response.get("reasoning", "")
                    cassandra_flags = thinker_response.get("cassandra_flags", [])
                    
                    # Store cassandra flags for monitoring
                    if cassandra_flags:
                        try:
                            self.db_handler.cassandra_flags_col.insert_one({
                                "flags": cassandra_flags,
                                "timestamp": datetime.now(timezone.utc)
                            })
                        except Exception as e:
                            logger.error(f"Failed to store cassandra flags: {e}")
                    
                    yield StreamingChunk(
                        ResponseStatus.THINKING,
                        reasoning or "Let me think about this..."
                    )
                    
                    if is_context_sufficient:
                        logger.debug("Thinker determined context is sufficient")
                        break
                    
                    # Get additional context from curator
                    queries_to_execute, insights_to_store = await self.curator_agent.run(information_request)
                    logger.debug(f"Curator provided {len(queries_to_execute)} queries and {len(insights_to_store)} insights")
                    
                    # Store insights
                    if insights_to_store:
                        for insight in insights_to_store:
                            try:
                                self.db_handler.insights_col.insert_one({
                                    "insight": insight,
                                    "timestamp": datetime.now(timezone.utc)
                                })
                            except Exception as e:
                                logger.error(f"Failed to store insight: {e}")
                    
                    # Execute queries
                    for query in queries_to_execute:
                        try:
                            query_type = query.get("query_type", "")
                            query_tags = query.get("tags", [])
                            time_filter = query.get("time_filter", "")
                            
                            if query_type == "search_by_tags":
                                results = self.db_handler.search_by_tags(
                                    query_tags, time_filter, self.config.search_limit
                                )
                            elif query_type == "hybrid_search":
                                embedded_vector = await self._fetch_embeddings(" ".join(query_tags))
                                results = self.db_handler.search(
                                    query_tags, embedded_vector, time_filter, self.config.search_limit
                                )
                            else:
                                logger.warning(f"Unknown query type: {query_type}")
                                continue
                            
                            thinker_context.setdefault("search_results", []).extend(results)
                            logger.debug(f"Query executed: {query_type}, found {len(results)} results")
                            
                        except Exception as e:
                            logger.error(f"Query execution failed: {e}")
                            continue
                    
                    thinker_context.setdefault("reasoning", []).append(reasoning)
                    
                except Exception as e:
                    logger.error(f"Thinker loop {loop_count + 1} failed: {e}")
                    yield StreamingChunk(
                        ResponseStatus.ERROR,
                        f"Thinking process encountered an error: {str(e)}"
                    )
                    break
            
            # Step 4: Response generation
            final_response = ""
            
            try:
                async for chunk in self.generator_agent.stream(
                    message, thinker_context, datetime.now(timezone.utc).isoformat()
                ):
                    final_response += chunk
                    formatted_chunk = self._format_with_emotes(chunk)
                    
                    if formatted_chunk:
                        yield formatted_chunk
                        
            except Exception as e:
                logger.error(f"Response generation failed: {e}")
                yield StreamingChunk(
                    ResponseStatus.ERROR,
                    f"Response generation failed: {str(e)}"
                )
                return
            
            # Step 5: Store interaction data
            try:
                response_summary, response_tags = await self.summarizer_agent.run(final_response)
                
                interaction_data = InteractionData(
                    user_id=self.config.user_name,
                    user_message=message,
                    user_summary=summary,
                    user_tags=tags,
                    user_embedding=query_vector,
                    agent_response=final_response,
                    response_summary=response_summary,
                    response_tags=response_tags,
                    response_embedding=await self._fetch_embeddings(final_response),
                    analysis=thinker_context
                )
                
                self.db_handler.store_interaction(interaction_data)
                logger.debug("Interaction data stored successfully")
                
            except Exception as e:
                logger.error(f"Failed to store interaction data: {e}")
            
            # Reset state and signal completion
            self._reset_formatting_state()
            yield StreamingChunk(ResponseStatus.DONE, "")
            
        except Exception as e:
            logger.error(f"Stream response failed: {e}")
            yield StreamingChunk(
                ResponseStatus.ERROR,
                f"An unexpected error occurred: {str(e)}"
            )
    
    async def chat(self, message: str) -> str:
        """
        Process a message and return the complete response.
        
        Args:
            message: User message to process
            
        Returns:
            Complete response text
        """
        response_parts = []
        
        async for chunk in self.stream_response(message):
            if chunk.status == ResponseStatus.RESPONSE:
                response_parts.append(chunk.message)
            elif chunk.status == ResponseStatus.ERROR:
                return f"Error: {chunk.message}"
            elif chunk.status == ResponseStatus.DONE:
                break
        
        return "".join(response_parts)
    
    async def close(self) -> None:
        """Clean up resources and close connections."""
        try:
            # Close agent connections
            await asyncio.gather(
                self.curator_agent.close(),
                self.thinker_agent.close(),
                self.generator_agent.close(),
                self.summarizer_agent.close(),
                return_exceptions=True
            )
            
            # Close database connection
            self.db_handler.close()
            
            logger.info("Carlos shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    async def __aenter__(self) -> Carlos:
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()


# Convenience function for backward compatibility
def create_carlos(
    api_endpoint: str = "http://localhost:1234",
    db_uri: str = "mongodb://localhost:27017",
    user_name: str = "test_user"
) -> Carlos:
    """
    Create a Carlos instance with the specified parameters.
    
    Args:
        api_endpoint: API endpoint for LLM services
        db_uri: MongoDB connection URI
        user_name: User identifier for database
        
    Returns:
        Configured Carlos instance
    """
    config = CarlosConfig(
        api_endpoint=api_endpoint,
        db_uri=db_uri,
        user_name=user_name
    )
    return Carlos(config)


if __name__ == "__main__":
    # Example usage
    async def main():
        """Example usage of the enhanced Carlos implementation."""
        config = CarlosConfig.from_environment()
        
        async with Carlos(config) as carlos:
            response = await carlos.chat("Hello, how are you today?")
            print("Carlos:", response)
    
    # Run example only if script is executed directly
    import asyncio
    asyncio.run(main())