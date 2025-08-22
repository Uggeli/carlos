from flask import Flask, render_template, request, jsonify, session, g, redirect, url_for
from carlos import Carlos
import os

import logging
# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
# Secret key required for Flask sessions; in production set via environment
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# In-memory cache of Carlos instances keyed by username (simple for now)
_CARLOS_INSTANCES = {}


@app.route('/static/<path:path>')
def static_files(path):
    """Serve static files from the 'static' directory."""
    return app.send_static_file(path)

@app.route('/favicon.ico')
def favicon():
    """Serve the favicon."""
    return app.send_static_file('favicon.ico')

@app.route('/robots.txt')
def robots():
    """Serve the robots.txt file."""
    return app.send_static_file('robots.txt')

@app.before_request
def before_request():
    """Log each request."""
    logging.info(f"Request: {request.method} {request.path} - {request.remote_addr}")
    # Enforce simple login by username for non-static routes
    open_paths = {"/login", "/favicon.ico", "/robots.txt"}
    is_static = request.path.startswith("/static/")
    if request.path not in open_paths and not is_static:
        username = session.get("username")
        if not username:
            # For API calls, return 401 JSON; for pages, redirect
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(url_for("login", next=request.path))

        # Create or retrieve per-user Carlos instance and stash in g
        g.username = username
        if username not in _CARLOS_INSTANCES:
            _CARLOS_INSTANCES[username] = Carlos(username=username)
        g.carlos = _CARLOS_INSTANCES[username]




@app.get('/')
def index():
    initial_reply = session.pop('welcome_reply', None)
    return render_template('chat.html', username=session.get('username'), initial_reply=initial_reply)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Very simple name capture to start a session."""
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            return render_template('login.html', error="Please enter your name.")
        session['username'] = name
        session.permanent = True  # keep cookie a bit longer during dev
        # Initialize carlos for this user now so first call is fast
        if name not in _CARLOS_INSTANCES:
            _CARLOS_INSTANCES[name] = Carlos(username=name)
        # Trigger an initial message from Carlos and show it in chat
        try:
            welcome = _CARLOS_INSTANCES[name].chat(f"{name} just logged in! and says hi!")
            if welcome:
                session['welcome_reply'] = welcome
        except Exception as e:
            logging.warning(f"Welcome message failed: {e}")
        next_url = request.args.get('next') or url_for('index')
        return redirect(next_url)
    return render_template('login.html')


@app.post('/logout')
def logout():
    """Clear session and optional in-memory Carlos instance."""
    username = session.pop('username', None)
    try:
        if username and username in _CARLOS_INSTANCES:
            # Best-effort cleanup; Carlos doesn't expose close, so just drop ref
            _CARLOS_INSTANCES.pop(username, None)
    finally:
        return redirect(url_for('login'))

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


# @app.post('/api/embeddings')
# def api_embeddings():
#     data = request.get_json(silent=True) or {}
#     text = (data.get('text') or '').strip()
#     if not text:
#         return jsonify({"error": "text is required"}), 400
#     try:
#         embeddings = _carlos.get_embeddings(text)
#         return jsonify({"embeddings": embeddings})
#     except Exception as e:
#         # Keep error simple for client; log details server-side
#         print(f"/api/embeddings error: {e}")
#         return jsonify({"error": "Failed to get embeddings"}), 500


if __name__ == '__main__':
    # debug=True enables auto-reload and nicer errors during development
    # Bind to 0.0.0.0 so the app is reachable on the local network.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
