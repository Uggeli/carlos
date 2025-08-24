const chat = document.getElementById('chat');
const form = document.getElementById('composer');
const input = document.getElementById('message');
const sendBtn = document.getElementById('send');
const rootElement = document.querySelector('body');
const isNewSession = rootElement.dataset.isNewSession === 'True';

// Proactive message polling
let proactivePolling = false;
let lastActivityTime = Date.now();

// Internal thoughts panel
let thoughtsPanel = null;
let thoughtsVisible = false;
// A simple utility to create and append a chat bubble
function addBubble(text, role = 'assistant', isThinking = false) {
    const div = document.createElement('div');
    div.className = `bubble ${role}${isThinking ? ' typing' : ''}`;
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

// Create a proactive message bubble with special styling
function addProactiveBubble(text) {
    const div = document.createElement('div');
    div.className = 'bubble assistant proactive';
    div.textContent = text;
    
    // Add a subtle animation
    div.style.opacity = '0';
    div.style.transform = 'translateY(10px)';
    
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    
    // Animate in
    requestAnimationFrame(() => {
        div.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
        div.style.opacity = '1';
        div.style.transform = 'translateY(0)';
    });
    
    return div;
}

// Handles the emote formatting - creates a div for line break
function addEmote(emoteName) {
    const div = document.createElement('div');
    div.className = 'emote';
    div.textContent = `[${emoteName}]`;
    return div;
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

// Check for proactive messages from autonomous shards
async function checkProactiveMessages() {
    try {
        const response = await fetch('/api/proactive');
        if (response.ok) {
            const data = await response.json();
            if (data.has_message && data.message) {
                addProactiveBubble(data.message);
                // Reset activity time since we got a message
                lastActivityTime = Date.now();
            }
        }
    } catch (error) {
        console.error('Error checking proactive messages:', error);
    }
}

// Start proactive message polling
function startProactivePolling() {
    if (proactivePolling) return;
    
    proactivePolling = true;
    
    // Check every 30 seconds when idle
    const pollInterval = setInterval(() => {
        const timeSinceActivity = Date.now() - lastActivityTime;
        const idleThreshold = 30000; // 30 seconds
        
        if (timeSinceActivity >= idleThreshold) {
            checkProactiveMessages();
        }
    }, 30000);
    
    // Also check immediately after conversations
    setTimeout(checkProactiveMessages, 5000);
}

// Update activity time whenever user interacts
function updateActivity() {
    lastActivityTime = Date.now();
}

// Internal thoughts panel functions
function initializeThoughtsPanel() {
    thoughtsPanel = document.getElementById('thoughts-panel');
    const toggleBtn = document.getElementById('thoughts-toggle');
    const closeBtn = document.getElementById('thoughts-close');
    
    toggleBtn.addEventListener('click', toggleThoughtsPanel);
    closeBtn.addEventListener('click', closeThoughtsPanel);
}

function toggleThoughtsPanel() {
    if (thoughtsVisible) {
        closeThoughtsPanel();
    } else {
        openThoughtsPanel();
    }
}

function openThoughtsPanel() {
    thoughtsPanel.style.display = 'flex';
    thoughtsPanel.classList.add('open');
    thoughtsVisible = true;
    loadInternalThoughts();
}

function closeThoughtsPanel() {
    thoughtsPanel.classList.remove('open');
    thoughtsVisible = false;
    setTimeout(() => {
        thoughtsPanel.style.display = 'none';
    }, 300);
}

async function loadInternalThoughts() {
    const content = document.getElementById('thoughts-content');
    content.innerHTML = '<div class="loading">Loading thoughts...</div>';
    
    try {
        const response = await fetch('/api/thoughts?limit=15');
        if (response.ok) {
            const data = await response.json();
            displayThoughts(data.thoughts);
        } else {
            content.innerHTML = '<div class="loading">Failed to load thoughts</div>';
        }
    } catch (error) {
        console.error('Error loading thoughts:', error);
        content.innerHTML = '<div class="loading">Error loading thoughts</div>';
    }
}

function displayThoughts(thoughts) {
    const content = document.getElementById('thoughts-content');
    
    if (!thoughts || thoughts.length === 0) {
        content.innerHTML = '<div class="loading">No thoughts yet... Carlos is still learning!</div>';
        return;
    }
    
    content.innerHTML = '';
    
    thoughts.forEach(thought => {
        const thoughtDiv = document.createElement('div');
        thoughtDiv.className = `thought-item ${thought.source || 'internal'}`;
        
        const timestamp = new Date(thought.timestamp).toLocaleTimeString();
        const urgencyColor = getUrgencyColor(thought.urgency || 0.5);
        
        if (thought.source === 'cyclical') {
            // Display cyclical thinking chain with more detail
            const cycles = thought.thinking_cycles || [];
            const cyclesHtml = cycles.slice(0, 3).map((cycle, idx) => 
                `<div class="thinking-cycle">
                    <strong>Cycle ${cycle.cycle || idx + 1}:</strong> ${cycle.observation || ''}
                    ${cycle.connection ? `<br><em>→ ${cycle.connection}</em>` : ''}
                </div>`
            ).join('');
            
            thoughtDiv.innerHTML = `
                <div class="thought-meta">
                    <span class="thought-type cyclical">🔄 cyclical (${thought.depth || 1} levels)</span>
                    <span class="thought-urgency" style="color: ${urgencyColor}">
                        ${(thought.urgency * 100).toFixed(0)}% ${timestamp}
                    </span>
                </div>
                <div class="thought-insight">${thought.insight || 'Processing...'}</div>
                ${cyclesHtml ? `<div class="thinking-cycles">${cyclesHtml}</div>` : ''}
                ${thought.synthesis ? `<div class="synthesis"><strong>Synthesis:</strong> ${thought.synthesis}</div>` : ''}
                ${thought.suggested_step ? `<div class="thought-step">${thought.suggested_step}</div>` : ''}
            `;
        } else {
            // Regular internal thought display
            thoughtDiv.innerHTML = `
                <div class="thought-meta">
                    <span class="thought-type">${thought.original_context || 'analysis'}</span>
                    <span class="thought-urgency" style="color: ${urgencyColor}">
                        ${(thought.urgency * 100).toFixed(0)}% ${timestamp}
                    </span>
                </div>
                <div class="thought-insight">${thought.insight || 'Processing...'}</div>
                ${thought.suggested_step ? `<div class="thought-step">${thought.suggested_step}</div>` : ''}
            `;
        }
        
        content.appendChild(thoughtDiv);
    });
}

function getUrgencyColor(urgency) {
    if (urgency >= 0.8) return '#ef4444'; // High urgency - red
    if (urgency >= 0.6) return '#f59e0b'; // Medium urgency - orange  
    if (urgency >= 0.4) return '#eab308'; // Low-medium urgency - yellow
    return '#9fb3c8'; // Low urgency - muted
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
                        const jsonStr = dataLine.substring(6).trim();
                        console.log('Parsing JSON:', jsonStr);
                        const data = JSON.parse(jsonStr);
                        if (eventName === 'status') {
                            showStatus(data.message);
                        } else if (eventName === 'token') {
                            if (!assistantBubble) {
                                hideStatus();
                                assistantBubble = addBubble('', 'assistant');
                            }
                            // Create text node instead of using textContent to preserve emotes
                            const textNode = document.createTextNode(data.text);
                            assistantBubble.appendChild(textNode);
                        } else if (eventName === 'emote') {
                            if (!assistantBubble) {
                                hideStatus();
                                assistantBubble = addBubble('', 'assistant');
                            }
                            assistantBubble.appendChild(addEmote(data.name));
                        } else if (eventName === 'proactive') {
                            hideStatus();
                            addProactiveBubble(data.message);
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

    updateActivity(); // Track user activity
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
        let buffer = '';
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
                        const jsonStr = dataLine.substring(6);
                        console.log('Parsing JSON:', jsonStr);
                        const data = JSON.parse(jsonStr);
                        if (eventName === 'token') {
                            if (!assistantBubble) {
                                hideStatus();
                                assistantBubble = addBubble('', 'assistant');
                            }
                            // Create text node instead of using textContent to preserve emotes
                            const textNode = document.createTextNode(data.text);
                            assistantBubble.appendChild(textNode);
                            chat.scrollTop = chat.scrollHeight;
                        } else if (eventName === 'emote') {
                            if (!assistantBubble) {
                                hideStatus();
                                assistantBubble = addBubble('', 'assistant');
                            }
                            assistantBubble.appendChild(addEmote(data.name));
                            chat.scrollTop = chat.scrollHeight;
                        } else if (eventName === 'proactive') {
                            hideStatus();
                            addProactiveBubble(data.message);
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
        // Check for proactive messages after conversation ends
        setTimeout(checkProactiveMessages, 3000);
    }
});

// Helper to resize textarea and track activity
input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';
    updateActivity(); // Track typing as activity
});

// Start proactive polling when page loads
document.addEventListener('DOMContentLoaded', () => {
    startProactivePolling();
    initializeThoughtsPanel();
});

// Also start after welcome message if new session
if (isNewSession) {
    setTimeout(startProactivePolling, 2000);
}