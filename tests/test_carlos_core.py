"""
Comprehensive test suite for the enhanced Carlos AI Assistant
Tests the refactored implementation with proper type safety and error handling
"""
import pytest
import asyncio
import tempfile
import os
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any, List

# Add the parent directory to sys.path to import carlos_enhanced
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from carlos_enhanced import (
    Carlos, CarlosConfig, CarlosDatabaseHandler, MongoJSONEncoder,
    CuratorAgent, ThinkerAgent, GeneratorAgent, SummarizerAgent,
    StreamingChunk, ResponseStatus, InteractionData,
    CarlosError, ConfigurationError, DatabaseError, APIError
)


class TestCarlosConfig:
    """Test suite for CarlosConfig class."""
    
    def test_config_initialization(self):
        """Test default configuration initialization."""
        config = CarlosConfig()
        assert config.api_endpoint == "http://localhost:1234"
        assert config.db_uri == "mongodb://localhost:27017"
        assert config.user_name == "default_user"
        assert config.max_thinker_loops == 15
    
    def test_config_from_environment(self):
        """Test configuration from environment variables."""
        with patch.dict(os.environ, {
            'CARLOS_API_ENDPOINT': 'http://test:8080',
            'CARLOS_USER_NAME': 'test_user',
            'CARLOS_MAX_THINKER_LOOPS': '10'
        }):
            config = CarlosConfig.from_environment()
            assert config.api_endpoint == "http://test:8080"
            assert config.user_name == "test_user"
            assert config.max_thinker_loops == 10


class TestStreamingChunk:
    """Test suite for StreamingChunk dataclass."""
    
    def test_streaming_chunk_creation(self):
        """Test StreamingChunk creation and properties."""
        chunk = StreamingChunk(ResponseStatus.RESPONSE, "Hello world")
        assert chunk.status == ResponseStatus.RESPONSE
        assert chunk.message == "Hello world"
        assert chunk.metadata is None
    
    def test_streaming_chunk_with_metadata(self):
        """Test StreamingChunk with metadata."""
        metadata = {"confidence": 0.95}
        chunk = StreamingChunk(ResponseStatus.THINKING, "Processing...", metadata)
        assert chunk.metadata == metadata


class TestInteractionData:
    """Test suite for InteractionData dataclass."""
    
    def test_interaction_data_creation(self):
        """Test InteractionData creation with required fields."""
        data = InteractionData(
            user_id="test_user",
            user_message="Hello",
            user_summary="Greeting",
            user_tags=["greeting"],
            user_embedding=[0.1, 0.2],
            agent_response="Hello there!",
            response_summary="Friendly greeting",
            response_tags=["response", "greeting"],
            response_embedding=[0.3, 0.4],
            analysis={"context": "test"}
        )
        assert data.user_id == "test_user"
        assert data.user_message == "Hello"
        assert len(data.user_embedding) == 2


class TestCarlosCore:
    """Test suite for core Carlos functionality."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing."""
        return CarlosConfig(
            api_endpoint="http://localhost:1234",
            db_uri="mongodb://localhost:27017/test",
            user_name="test_user"
        )
    
    @pytest.fixture
    def mock_db_handler(self):
        """Mock database handler for testing."""
        handler = Mock(spec=CarlosDatabaseHandler)
        handler.search.return_value = []
        handler.search_by_tags.return_value = []
        handler.store_interaction.return_value = "test_id"
        handler.cassandra_flags_col = Mock()
        handler.insights_col = Mock()
        handler.close.return_value = None
        return handler
    
    @pytest.fixture
    def carlos_instance(self, mock_config, mock_db_handler):
        """Create a Carlos instance with mocked dependencies for testing."""
        with patch('carlos_enhanced.CarlosDatabaseHandler', return_value=mock_db_handler), \
             patch.object(Carlos, '_load_prompts_and_schemas'), \
             patch.object(Carlos, '_initialize_agents'):
            instance = Carlos(mock_config)
            # Mock agents
            instance.curator_agent = Mock(spec=CuratorAgent)
            instance.thinker_agent = Mock(spec=ThinkerAgent)
            instance.generator_agent = Mock(spec=GeneratorAgent)
            instance.summarizer_agent = Mock(spec=SummarizerAgent)
            
            # Add close methods to agents
            instance.curator_agent.close = AsyncMock()
            instance.thinker_agent.close = AsyncMock()
            instance.generator_agent.close = AsyncMock()
            instance.summarizer_agent.close = AsyncMock()
            
            return instance
    
    def test_carlos_initialization(self, mock_config, mock_db_handler):
        """Test that Carlos initializes properly with all required components."""
        with patch('carlos_enhanced.CarlosDatabaseHandler', return_value=mock_db_handler), \
             patch.object(Carlos, '_load_prompts_and_schemas'), \
             patch.object(Carlos, '_initialize_agents'):
            instance = Carlos(mock_config)
            assert instance.config == mock_config
            assert instance.db_handler == mock_db_handler
    
    @pytest.mark.asyncio
    async def test_embedding_fetch_success(self, carlos_instance):
        """Test successful embedding fetch."""
        mock_response_data = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status.return_value = None
            
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            embeddings = await carlos_instance._fetch_embeddings("test text")
            assert embeddings == [0.1, 0.2, 0.3]
    
    @pytest.mark.asyncio
    async def test_embedding_fetch_failure(self, carlos_instance):
        """Test embedding fetch failure handling."""
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = Exception("API Error")
            
            embeddings = await carlos_instance._fetch_embeddings("test text")
            assert embeddings == []
    
    @pytest.mark.asyncio
    async def test_chunk_message(self, carlos_instance):
        """Test message chunking functionality."""
        # Mock summarizer agent
        carlos_instance.summarizer_agent.run = AsyncMock(
            return_value=("Test summary", ["test", "chunk"])
        )
        
        long_message = "A" * 5000  # Longer than default chunk size
        summary, tags = await carlos_instance._chunk_message(long_message)
        
        assert "Chunk 1" in summary
        assert "test" in tags
        assert "chunk" in tags
    
    def test_format_with_emotes_response(self, carlos_instance):
        """Test emote formatting for regular response."""
        result = carlos_instance._format_with_emotes("Hello world")
        
        # Should return a StreamingChunk for response text
        assert isinstance(result, StreamingChunk)
        assert result.status == ResponseStatus.RESPONSE
        assert result.message == "Hello world"
    
    def test_format_with_emotes_detection(self, carlos_instance):
        """Test emote detection and processing."""
        # Test emote start
        carlos_instance._reset_formatting_state()
        result = carlos_instance._format_with_emotes("[laughs")
        assert result is None  # Still processing
        assert carlos_instance.in_emote is True
        
        # Test emote completion
        result = carlos_instance._format_with_emotes("]")
        assert isinstance(result, StreamingChunk)
        assert result.status == ResponseStatus.EMOTE
        assert "[laughs]" in result.message
        assert carlos_instance.in_emote is False
    
    @pytest.mark.asyncio
    async def test_chat_method(self, carlos_instance):
        """Test the chat method functionality."""
        # Mock the stream_response method
        async def mock_stream():
            yield StreamingChunk(ResponseStatus.RESPONSE, "Hello ")
            yield StreamingChunk(ResponseStatus.RESPONSE, "there!")
            yield StreamingChunk(ResponseStatus.DONE, "")
        
        carlos_instance.stream_response = Mock(return_value=mock_stream())
        
        result = await carlos_instance.chat("Hello")
        assert result == "Hello there!"
    
    @pytest.mark.asyncio
    async def test_close_method(self, carlos_instance):
        """Test proper resource cleanup."""
        await carlos_instance.close()
        
        # Verify all agents' close methods were called
        carlos_instance.curator_agent.close.assert_called_once()
        carlos_instance.thinker_agent.close.assert_called_once()
        carlos_instance.generator_agent.close.assert_called_once()
        carlos_instance.summarizer_agent.close.assert_called_once()
        
        # Verify database handler close was called
        carlos_instance.db_handler.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_context_manager(self, carlos_instance):
        """Test async context manager functionality."""
        async with carlos_instance as instance:
            assert instance == carlos_instance
        
        # Verify close was called automatically
        carlos_instance.curator_agent.close.assert_called_once()


class TestAgentComponents:
    """Test suite for individual agent components."""
    
    @pytest.mark.asyncio
    async def test_curator_agent(self):
        """Test CuratorAgent functionality."""
        agent = CuratorAgent(
            "http://localhost:1234",
            "Test system prompt",
            {"type": "object"}
        )
        
        # Mock the _call_llm method
        agent._call_llm = AsyncMock(return_value={
            "queries_to_execute": [{"type": "test"}],
            "insights_to_store": ["test insight"]
        })
        
        queries, insights = await agent.run("Test message")
        assert len(queries) == 1
        assert len(insights) == 1
        assert queries[0]["type"] == "test"
        assert insights[0] == "test insight"
    
    @pytest.mark.asyncio
    async def test_thinker_agent(self):
        """Test ThinkerAgent functionality."""
        agent = ThinkerAgent(
            "http://localhost:1234",
            "Test system prompt",
            {"type": "object"}
        )
        
        # Mock the _call_llm method
        agent._call_llm = AsyncMock(return_value={
            "is_context_sufficient": True,
            "reasoning": "Test reasoning"
        })
        
        result = await agent.run("Test message", {"context": "test"})
        assert result["is_context_sufficient"] is True
        assert result["reasoning"] == "Test reasoning"
    
    @pytest.mark.asyncio
    async def test_generator_agent(self):
        """Test GeneratorAgent functionality."""
        agent = GeneratorAgent(
            "http://localhost:1234",
            "Test system prompt",
            {"type": "object"}
        )
        
        # Mock the _call_llm method
        agent._call_llm = AsyncMock(return_value={
            "response_text": "Generated response"
        })
        
        result = await agent.run("Test message", {"context": "test"}, "2023-01-01T00:00:00Z")
        assert result == "Generated response"
    
    @pytest.mark.asyncio
    async def test_summarizer_agent(self):
        """Test SummarizerAgent functionality."""
        agent = SummarizerAgent(
            "http://localhost:1234",
            "Test system prompt",
            {"type": "object"}
        )
        
        # Mock the _call_llm method
        agent._call_llm = AsyncMock(return_value={
            "summary": "Test summary",
            "tags": ["test", "summary"]
        })
        
        summary, tags = await agent.run("Test text to summarize")
        assert summary == "Test summary"
        assert tags == ["test", "summary"]


class TestUtilities:
    """Test suite for utility functions and classes."""
    
    def test_mongo_json_encoder(self):
        """Test the MongoJSONEncoder for handling special MongoDB types."""
        encoder = MongoJSONEncoder()
        
        # Test ObjectId encoding
        from bson import ObjectId
        obj_id = ObjectId()
        result = encoder.default(obj_id)
        assert result == str(obj_id)
        
        # Test datetime encoding
        from datetime import datetime
        dt = datetime.now()
        result = encoder.default(dt)
        assert result == dt.isoformat()
    
    def test_response_status_enum(self):
        """Test ResponseStatus enum values."""
        assert ResponseStatus.THINKING.value == "thinking"
        assert ResponseStatus.RESPONSE.value == "response"
        assert ResponseStatus.DONE.value == "[DONE]"
        assert ResponseStatus.ERROR.value == "error"


class TestErrorHandling:
    """Test suite for error handling and exceptions."""
    
    def test_carlos_error_hierarchy(self):
        """Test that custom exceptions inherit properly."""
        assert issubclass(ConfigurationError, CarlosError)
        assert issubclass(DatabaseError, CarlosError)
        assert issubclass(APIError, CarlosError)
    
    def test_configuration_error(self):
        """Test ConfigurationError exception."""
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("Test configuration error")
    
    def test_database_error(self):
        """Test DatabaseError exception."""
        with pytest.raises(DatabaseError):
            raise DatabaseError("Test database error")
    
    def test_api_error(self):
        """Test APIError exception."""
        with pytest.raises(APIError):
            raise APIError("Test API error")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])