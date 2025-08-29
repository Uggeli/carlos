
import json
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import carlos
# Assuming 'carlos_instance' is initialized somewhere, just like in your Flask app
# from your_code import carlos_instance 

carlos_instance = carlos.Carlos(
	api_endpoint="http://localhost:1234",
	db_uri="mongodb://localhost:27017",  
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

@app.get("/stream")
async def stream(request: Request, prompt: str = "Default prompt"):
    """
    The main endpoint that returns the streaming response.
    """
    return StreamingResponse(stream_generator(prompt), media_type="text/event-stream")

# To run this:
# 1. pip install fastapi "uvicorn[standard]"
# 2. uvicorn main:app --reload