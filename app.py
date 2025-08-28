from carlos import Carlos
from flask import Flask, render_template, Response, g, request
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CARLOS_INSTANCES = []

carlos_instance = Carlos(
	api_endpoint="http://localhost:1234",
	db_uri="mongodb://localhost:27017",  
	user_name="test_user"
	)


@app.route('/favicon.ico', methods=['GET'])
def favicon():
	return '', 200

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Implement login logic here
	return "Login Page"

@app.route('/logout')
def logout():
	# Implement logout logic here
	return "Logout Page"

@app.route('/stream', methods=['GET', 'POST'])
def stream():
	prompt = request.args.get('prompt', 'Default prompt')
	if not prompt:
		return Response("data: {\"error\": \"No prompt provided\"}\n\n", mimetype='text/event-stream')
	
	import json
	import asyncio
	import logging
	
	def generate():
		loop = None
		try:
			# Create a new event loop for this request
			loop = asyncio.new_event_loop()
			asyncio.set_event_loop(loop)
			logging.info(f"Event loop created for streaming request: {id(loop)}")
			
			async def run_stream():
				try:
					async for data in carlos_instance.stream_response(prompt):
						# Check if this is the done signal
						if data.get('status') == '[DONE]':
							yield f"data: {json.dumps(data)}\n\n"
							return
						else:
							yield f"data: {json.dumps(data)}\n\n"
				except Exception as e:
					logging.error(f"Stream error: {e}")
					yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"
			
			# Run the async generator synchronously
			async_gen = run_stream()
			
			try:
				while True:
					try:
						# Get next chunk from async generator
						chunk = loop.run_until_complete(async_gen.__anext__())
						yield chunk
						
						# Check if we just sent the [DONE] signal
						if '"status": "[DONE]"' in chunk:
							logging.info("Stream completed successfully")
							break
							
					except StopAsyncIteration:
						logging.info("Stream completed via StopAsyncIteration")
						break
						
			except Exception as gen_error:
				logging.error(f"Generator error: {gen_error}")
				yield f"data: {json.dumps({'status': 'error', 'message': f'Generator error: {str(gen_error)}'})}\n\n"
					
		except Exception as e:
			logging.error(f"Stream setup error: {e}")
			yield f"data: {json.dumps({'status': 'error', 'message': f'Server error: {str(e)}'})}\n\n"
		finally:
			# Always clean up the event loop
			if loop:
				try:
					# Close any remaining tasks
					if not loop.is_closed():
						# Cancel any pending tasks
						pending = asyncio.all_tasks(loop)
						if pending:
							logging.info(f"Cancelling {len(pending)} pending tasks")
							for task in pending:
								task.cancel()
							# Wait for tasks to complete cancellation
							loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
						
						logging.info(f"Closing event loop: {id(loop)}")
						loop.close()
				except Exception as cleanup_error:
					logging.error(f"Error cleaning up event loop: {cleanup_error}")
			
			# Clear the event loop from thread-local storage
			try:
				asyncio.set_event_loop(None)
			except Exception:
				pass
	
	response = Response(generate(), mimetype='text/event-stream')
	response.headers['Cache-Control'] = 'no-cache' 
	response.headers['Connection'] = 'keep-alive'
	response.headers['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
	return response
	
	
if __name__ == '__main__':
	app.run(debug=True)