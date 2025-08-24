from flask import Flask, Response, render_template, request, jsonify, session, g, redirect, url_for
from carlos import Carlos
import os

import logging
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
app = Flask(__name__)
# Secret key required for Flask sessions; in production set via environment
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# In-memory cache of Carlos instances keyed by username (simple for now)
_CARLOS_INSTANCES = {}


@app.route('/static/<path:path>')
def static_files(path):
    """Serve static files from the 'static' directory."""
    return app.send_static_file(path)

@app.route('/robots.txt')
def robots():
    """Serve the robots.txt file."""
    return app.send_static_file('robots.txt')

@app.before_request
def before_request():
    """Authenticate user before processing request, except for open paths."""
    logging.info(f"Request: {request.method} {request.path} - {request.remote_addr}")
    open_paths = {"/login", "/favicon.ico", "/robots.txt"}
    is_static = request.path.startswith("/static/")
    if request.path not in open_paths and not is_static:
        username = session.get("username")
        if not username:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login", next=request.path))

        g.username = username
        if username not in _CARLOS_INSTANCES:
            _CARLOS_INSTANCES[username] = Carlos(username=username)
        g.carlos = _CARLOS_INSTANCES[username]

@app.get('/')
def index():
    initial_reply = session.pop('welcome_reply', None)
    # Pass a flag to the template to indicate if it's a new session
    is_new_session = session.pop('is_new_session', False)
    return render_template('chat.html', username=session.get('username'), initial_reply=initial_reply, is_new_session=is_new_session)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Very simple name capture to start a session."""
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            return render_template('login.html', error="Please enter your name.")
        
        session['username'] = name
        session.permanent = True
        
        # Set a flag to signal the frontend to stream the welcome message
        session['is_new_session'] = True
        
        if name not in _CARLOS_INSTANCES:
            _CARLOS_INSTANCES[name] = Carlos(username=name)
        
        next_url = request.args.get('next') or url_for('index')
        return redirect(next_url)
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Clear session and optional in-memory Carlos instance."""
    username = session.pop('username', None)
    try:
        if username and username in _CARLOS_INSTANCES:
            # Properly shutdown autonomous shards
            carlos_instance = _CARLOS_INSTANCES[username]
            carlos_instance.shutdown()
            _CARLOS_INSTANCES.pop(username, None)
    finally:
        return redirect(url_for('login'))

@app.route('/api/welcome/stream', methods=['GET'])
def api_welcome_stream():
    try:
        carlos: Carlos = getattr(g, 'carlos', None)
        if carlos is None:
            return jsonify({"error": "Unauthorized"}), 401
        
        # Craft a special prompt for the welcome message
        welcome_prompt = f"{g.username} has just logged in! Please greet them warmly."
        
        return Response(carlos.chat_stream(welcome_prompt), content_type='text/event-stream')

    except Exception as e:
        print(f"/api/welcome/stream error: {e}")
        return jsonify({"error": "Failed to get welcome message"}), 500
    
@app.post('/api/chat')
def api_chat():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    try:
        carlos = getattr(g, 'carlos', None)
        if carlos is None:
            return jsonify({"error": "Unauthorized"}), 401
        reply = carlos.chat(message)
        return jsonify({"reply": reply})
    except Exception as e:
        # Keep error simple for client; log details server-side
        # In real app, use proper logging
        print(f"/api/chat error: {e}")
        return jsonify({"error": "Failed to get response"}), 500

@app.route('/api/chat/stream', methods=['GET', 'POST'])
def api_chat_stream():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    try:
        carlos: Carlos = getattr(g, 'carlos', None)
        if carlos is None:
            return jsonify({"error": "Unauthorized"}), 401
        return Response(carlos.chat_stream(message), content_type='text/event-stream')

    except Exception as e:
        print(f"/api/chat/stream error: {e}")
        return jsonify({"error": "Failed to get response"}), 500

@app.route('/api/proactive', methods=['GET'])
def api_proactive():
    """Check for proactive messages from autonomous shards"""
    try:
        carlos: Carlos = getattr(g, 'carlos', None)
        if carlos is None:
            return jsonify({"error": "Unauthorized"}), 401
        
        proactive_message = carlos.check_proactive_messages()
        if proactive_message:
            return jsonify({"message": proactive_message, "has_message": True})
        else:
            return jsonify({"has_message": False})
    
    except Exception as e:
        print(f"/api/proactive error: {e}")
        return jsonify({"error": "Failed to check proactive messages"}), 500

@app.route('/api/thoughts', methods=['GET'])
def api_internal_thoughts():
    """Get internal thoughts for monitoring panel"""
    try:
        carlos: Carlos = getattr(g, 'carlos', None)
        if carlos is None:
            return jsonify({"error": "Unauthorized"}), 401
        
        limit = int(request.args.get('limit', 20))
        thoughts = carlos.get_internal_thoughts(limit)
        
        # Convert ObjectId and datetime for JSON serialization
        from bson import ObjectId
        from carlos import MongoJSONEncoder
        import json
        
        serialized_thoughts = json.loads(json.dumps(thoughts, cls=MongoJSONEncoder))
        return jsonify({"thoughts": serialized_thoughts})
    
    except Exception as e:
        print(f"/api/thoughts error: {e}")
        return jsonify({"error": "Failed to get internal thoughts"}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
