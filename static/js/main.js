const chat = document.getElementById('chat');
const form = document.getElementById('composer');
const input = document.getElementById('message');
const sendBtn = document.getElementById('send');
const rootElement = document.querySelector('body');
const isNewSession = rootElement.dataset.isNewSession === 'True';
// A simple utility to create and append a chat bubble
function addBubble(text, role = 'assistant', isThinking = false) {
    const div = document.createElement('div');
    div.className = `bubble ${role}${isThinking ? ' typing' : ''}`;
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

// Handles the emote formatting
function addEmote(emoteName) {
    const span = document.createElement('span');
    span.className = 'emote';
    span.textContent = ` [${emoteName}] `;
    return span;
}

// Show a loading message with the "thinking dots" animation
function showStatus(text) {
    const statusDiv = document.getElementById('status-indicator');
    if (statusDiv) {
        statusDiv.textContent = text;
    } else {
        const div = document.createElement('div');
        div.id = 'status-indicator';
        div.className = 'bubble typing';
        div.innerHTML = `<span class="typing-dots">${text}</span>`;
        chat.appendChild(div);
        chat.scrollTop = chat.scrollHeight;
    }
}

// Hide the status indicator
function hideStatus() {
    const statusDiv = document.getElementById('status-indicator');
    if (statusDiv) {
        statusDiv.remove();
    }
}

async function streamWelcomeMessage() {
    const url = '/api/welcome/stream';
    showStatus('Thinking...');

    let assistantBubble = null;

    try {
        const response = await fetch(url, {
            method: 'GET'
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to start stream.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        // The streaming logic from our previous example
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split('\n');
            buffer = lines.pop();

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i];
                if (line.startsWith('event: ')) {
                    const eventName = line.substring(7).trim();
                    const dataLine = lines[i + 1]; // The next line should be 'data:'
                    if (dataLine && dataLine.startsWith('data: ')) {
                        const data = JSON.parse(dataLine.substring(6).trim());
                        if (eventName === 'status') {
                            showStatus(data.message);
                        } else if (eventName === 'token') {
                            if (!assistantBubble) {
                                hideStatus();
                                assistantBubble = addBubble('', 'assistant');
                            }
                            assistantBubble.textContent += data.text;
                        } else if (eventName === 'emote') {
                            if (!assistantBubble) {
                                hideStatus();
                                assistantBubble = addBubble('', 'assistant');
                            }
                            assistantBubble.appendChild(addEmote(data.emote));
                        } else if (eventName === 'error' || eventName === 'close') {
                            hideStatus();
                        }
                        i++; // Skip the data line since it's already processed
                    }
                }
            }
        }
    } catch (err) {
        hideStatus();
        const errorBubble = addBubble(err.message || 'Something went wrong.', 'assistant');
        errorBubble.classList.add('error');
    }
}

// Call the streaming function on page load if it's a new session
if (isNewSession) {
    streamWelcomeMessage();
}

// The main function to handle form submission and streaming
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    addBubble(message, 'user');
    input.value = '';
    input.style.height = 'auto';
    sendBtn.disabled = true;

    showStatus('Curating...');

    let assistantBubble = null;

    try {
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to start stream.');
        }

        // Get a reader from the streaming body
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            let lines = buffer.split('\n');
            buffer = lines.pop(); // Keep the last, possibly incomplete, line in the buffer

            for (let i = 0; i < lines.length; i++) {
                const line = lines[i].trim();
                if (line.startsWith('event: ')) {
                    const eventName = line.substring(7).trim();
                    const dataLine = lines[i + 1] ? lines[i + 1].trim() : null;
                    if (dataLine && dataLine.startsWith('data: ')) {
                        const data = JSON.parse(dataLine.substring(6));
                        if (eventName === 'token') {
                            if (!assistantBubble) {
                                hideStatus();
                                assistantBubble = addBubble('', 'assistant');
                            }
                            assistantBubble.textContent += data.text;
                            chat.scrollTop = chat.scrollHeight;
                        } else if (eventName === 'emote') {
                            if (!assistantBubble) {
                                hideStatus();
                                assistantBubble = addBubble('', 'assistant');
                            }
                            assistantBubble.appendChild(addEmote(data.name));
                            chat.scrollTop = chat.scrollHeight;
                        } else if (eventName === 'status') {
                            showStatus(data.message);
                        } else if (eventName === 'close' || eventName === 'error') {
                            hideStatus();
                        }
                        i++; // Skip the data line since it's already processed
                    }
                }
            }
        }
    } catch (err) {
        hideStatus();
        addBubble(err.message || 'Something went wrong.', 'error');
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
});

// Helper to resize textarea
input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';
});