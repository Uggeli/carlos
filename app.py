
import json
import logging
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import carlos

# Configure logging for FastAPI
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

carlos_instance = carlos.Carlos(
	api_endpoint="http://localhost:1234",
	db_uri="mongodb://localhost:27017/carlos",  
	user_name="test_user"
	)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
	return StreamingResponse(open("static/images/favicon.png", "rb"), media_type="image/x-icon")

@app.get("/")
async def root(request: Request):
	return templates.TemplateResponse("index.html", {"request": request})

# This async generator is the core logic
async def stream_generator(prompt: str):
    """
    An async generator that yields formatted data chunks from the AI.
    """
    try:
        # The 'async for' loop works natively here! No more manual bridging.
        async for data in carlos_instance.stream_response(prompt):
            yield f"data: {json.dumps(data)}\n\n"
            # If we receive the done signal, we can stop
            if data.get('status') == '[DONE]':
                break
    except Exception as e:
        # Handle errors gracefully
        yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

@app.post("/stream")
async def stream(request: Request):
    """
    The main endpoint that returns the streaming response.
    """
    try:
        body = await request.json()
        prompt = body.get("prompt", "Default prompt")
        return StreamingResponse(stream_generator(prompt), media_type="text/event-stream")
    except Exception as e:
        return StreamingResponse(
            stream_generator_error(f"Error parsing request: {str(e)}"), 
            media_type="text/event-stream"
        )

async def stream_generator_error(error_msg: str):
    """Generator for error responses."""
    yield f"data: {json.dumps({'status': 'error', 'message': error_msg})}\n\n"

# To run this:
# 1. pip install fastapi "uvicorn[standard]"
# 2. uvicorn main:app --reload