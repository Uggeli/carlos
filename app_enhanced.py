"""
Enhanced FastAPI application for Carlos AI Assistant
Modern, type-safe web server with proper error handling and async patterns
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from carlos_enhanced import Carlos, CarlosConfig, StreamingChunk, ResponseStatus, CarlosError

import logging
import json
import asyncio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global Carlos instance
carlos_instance: Optional[Carlos] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    global carlos_instance
    
    # Startup
    try:
        config = CarlosConfig.from_environment()
        carlos_instance = Carlos(config)
        logger.info("Carlos instance initialized successfully")
        yield
    except Exception as e:
        logger.error(f"Failed to initialize Carlos: {e}")
        raise
    finally:
        # Shutdown
        if carlos_instance:
            await carlos_instance.close()
            logger.info("Carlos instance closed")


# Create FastAPI app with lifespan management
app = FastAPI(
    title="Carlos AI Assistant",
    description="Advanced AI Assistant implementing the Recursive Shard Architecture",
    version="2.0.0",
    lifespan=lifespan
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class ChatRequest(BaseModel):
    """Request model for chat endpoints."""
    message: str = Field(..., min_length=1, max_length=10000, description="User message")
    stream: bool = Field(default=False, description="Whether to stream the response")


class ChatResponse(BaseModel):
    """Response model for chat endpoints."""
    response: str = Field(..., description="Carlos's response")
    status: str = Field(default="success", description="Response status")


@app.get("/")
async def root(request: Request):
    """Serve the main chat interface."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve favicon."""
    try:
        with open("static/images/favicon.png", "rb") as f:
            return StreamingResponse(
                iter([f.read()]), 
                media_type="image/x-icon"
            )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Favicon not found")


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Handle chat requests with non-streaming response.
    
    Args:
        request: Chat request containing the message
        
    Returns:
        Complete chat response
        
    Raises:
        HTTPException: If chat processing fails
    """
    if not carlos_instance:
        raise HTTPException(status_code=503, detail="Carlos is not available")
    
    try:
        response = await carlos_instance.chat(request.message)
        return ChatResponse(response=response)
    except CarlosError as e:
        logger.error(f"Carlos error: {e}")
        raise HTTPException(status_code=500, detail=f"Carlos error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error in chat: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/stream")
async def stream_chat(message: str) -> StreamingResponse:
    """
    Handle streaming chat requests.
    
    Args:
        message: User message as query parameter
        
    Returns:
        Streaming response with real-time updates
        
    Raises:
        HTTPException: If streaming fails
    """
    if not carlos_instance:
        raise HTTPException(status_code=503, detail="Carlos is not available")
    
    if not message or len(message.strip()) == 0:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    async def stream_generator():
        """Generate streaming response chunks."""
        try:
            async for chunk in carlos_instance.stream_response(message):
                # Convert chunk to dict for JSON serialization
                chunk_data = {
                    "status": chunk.status.value,
                    "message": chunk.message,
                    "metadata": chunk.metadata
                }
                
                yield f"data: {json.dumps(chunk_data)}\n\n"
                
                # End stream on completion or error
                if chunk.status in [ResponseStatus.DONE, ResponseStatus.ERROR]:
                    break
                    
        except CarlosError as e:
            error_chunk = {
                "status": ResponseStatus.ERROR.value,
                "message": f"Carlos error: {str(e)}",
                "metadata": None
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            error_chunk = {
                "status": ResponseStatus.ERROR.value,
                "message": "An unexpected error occurred",
                "metadata": None
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )


@app.post("/api/chat/stream")
async def stream_chat_post(request: ChatRequest) -> StreamingResponse:
    """
    Handle streaming chat requests via POST.
    
    Args:
        request: Chat request containing the message
        
    Returns:
        Streaming response with real-time updates
    """
    return await stream_chat(request.message)


@app.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.
    
    Returns:
        Health status information
    """
    status = "healthy" if carlos_instance else "unhealthy"
    return {
        "status": status,
        "service": "Carlos AI Assistant",
        "version": "2.0.0"
    }


@app.exception_handler(CarlosError)
async def carlos_error_handler(request: Request, exc: CarlosError):
    """Handle Carlos-specific errors."""
    logger.error(f"Carlos error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Carlos error: {str(exc)}"}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app_enhanced:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        log_level="info"
    )