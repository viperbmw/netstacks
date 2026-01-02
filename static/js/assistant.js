/**
 * NetStacks AI Assistant
 *
 * Handles the sidebar chat interface for the AI assistant.
 * Uses Socket.IO for real-time communication with the assistant agent.
 * Persists session and chat history across page navigations.
 */

(function() {
    'use strict';

    // Storage keys
    const STORAGE_KEY_SESSION = 'netstacks_assistant_session';
    const STORAGE_KEY_MESSAGES = 'netstacks_assistant_messages';
    const STORAGE_KEY_SIDEBAR_OPEN = 'netstacks_assistant_sidebar_open';

    // State
    let socket = null;
    let sessionId = null;
    let isConnected = false;
    let isTyping = false;
    let currentPage = window.location.pathname;
    let chatMessages = [];  // In-memory message cache

    // DOM Elements
    let sidebar = null;
    let toggleBtn = null;
    let overlay = null;
    let messagesContainer = null;
    let inputField = null;
    let sendBtn = null;
    let statusDot = null;
    let statusText = null;

    // Initialize when DOM is ready
    document.addEventListener('DOMContentLoaded', initAssistant);

    function initAssistant() {
        // AI Assistant disabled - WebSocket server not implemented yet
        console.log('AI Assistant disabled (WebSocket server not available)');
        return;

        // Check if assistant is enabled before initializing
        checkAssistantEnabled().then(function(enabled) {
            if (!enabled) {
                console.log('AI Assistant is disabled');
                return;
            }

            // Create and inject the sidebar HTML
            injectSidebarHTML();

            // Cache DOM elements
            sidebar = document.getElementById('assistant-sidebar');
            toggleBtn = document.getElementById('assistant-toggle-btn');
            overlay = document.getElementById('assistant-overlay');
            messagesContainer = document.getElementById('assistant-messages');
            inputField = document.getElementById('assistant-input');
            sendBtn = document.getElementById('assistant-send-btn');
            statusDot = document.querySelector('.assistant-status-dot');
            statusText = document.querySelector('.assistant-status-text');

            if (!sidebar) return;

            // Bind events
            bindEvents();

            // Load persisted state
            loadPersistedState();

            // Initialize Socket.IO connection
            initSocket();
        });
    }

    // Check if the assistant is enabled in settings
    function checkAssistantEnabled() {
        return new Promise(function(resolve) {
            $.get('/api/settings/assistant/config')
                .done(function(data) {
                    if (data.config) {
                        resolve(data.config.enabled === true || data.config.enabled === 'true');
                    } else {
                        resolve(false);
                    }
                })
                .fail(function(error) {
                    console.warn('Could not check assistant config:', error);
                    resolve(false);
                });
        });
    }

    function injectSidebarHTML() {
        const html = `
            <!-- Assistant Toggle Button -->
            <button id="assistant-toggle-btn" class="assistant-toggle-btn" title="NetStacks Assistant">
                <i class="fas fa-robot"></i>
            </button>

            <!-- Overlay for mobile -->
            <div id="assistant-overlay" class="assistant-overlay"></div>

            <!-- Assistant Sidebar -->
            <div id="assistant-sidebar" class="assistant-sidebar">
                <div class="assistant-header">
                    <h5><i class="fas fa-robot"></i> NetStacks Assistant</h5>
                    <div class="assistant-header-actions">
                        <button class="assistant-new-chat-btn" id="assistant-new-chat-btn" title="New Chat">
                            <i class="fas fa-plus"></i>
                        </button>
                        <button class="assistant-close-btn" id="assistant-close-btn">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>

                <div class="assistant-status">
                    <span class="assistant-status-dot"></span>
                    <span class="assistant-status-text">Connecting...</span>
                </div>

                <div id="assistant-messages" class="assistant-messages">
                    <div class="assistant-welcome">
                        <div class="assistant-welcome-icon">
                            <i class="fas fa-robot"></i>
                        </div>
                        <h4>Hi! I'm your NetStacks Assistant</h4>
                        <p>I can help you navigate the app, create MOPs, and build templates.</p>
                        <div class="assistant-welcome-suggestions">
                            <button class="assistant-suggestion-btn" data-message="How do I create a MOP?">
                                <i class="fas fa-list-check"></i> How do I create a MOP?
                            </button>
                            <button class="assistant-suggestion-btn" data-message="Help me create a Jinja2 template">
                                <i class="fas fa-file-code"></i> Help me create a template
                            </button>
                            <button class="assistant-suggestion-btn" data-message="Where can I manage devices?">
                                <i class="fas fa-server"></i> Where can I manage devices?
                            </button>
                        </div>
                    </div>
                </div>

                <div class="assistant-input-area">
                    <div class="assistant-input-container">
                        <textarea
                            id="assistant-input"
                            class="assistant-input"
                            placeholder="Ask me anything..."
                            rows="1"
                        ></textarea>
                        <button id="assistant-send-btn" class="assistant-send-btn" disabled>
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.insertAdjacentHTML('beforeend', html);
    }

    function bindEvents() {
        // Toggle sidebar
        toggleBtn.addEventListener('click', toggleSidebar);
        document.getElementById('assistant-close-btn').addEventListener('click', closeSidebar);
        document.getElementById('assistant-new-chat-btn').addEventListener('click', startNewChat);
        overlay.addEventListener('click', closeSidebar);

        // Input handling
        inputField.addEventListener('input', handleInput);
        inputField.addEventListener('keydown', handleKeyDown);
        sendBtn.addEventListener('click', sendMessage);

        // Suggestion buttons
        document.querySelectorAll('.assistant-suggestion-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const message = this.dataset.message;
                sendMessage(message);
            });
        });

        // Close on Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && sidebar.classList.contains('open')) {
                closeSidebar();
            }
        });
    }

    // =========================================================================
    // Session Persistence
    // =========================================================================

    function loadPersistedState() {
        // Load saved session ID
        const savedSession = sessionStorage.getItem(STORAGE_KEY_SESSION);
        if (savedSession) {
            sessionId = savedSession;
            console.log('Loaded persisted session:', sessionId);
        }

        // Load saved messages
        const savedMessages = sessionStorage.getItem(STORAGE_KEY_MESSAGES);
        if (savedMessages) {
            try {
                chatMessages = JSON.parse(savedMessages);
                console.log('Loaded', chatMessages.length, 'persisted messages');
            } catch (e) {
                console.warn('Failed to parse saved messages:', e);
                chatMessages = [];
            }
        }

        // Restore sidebar state
        const sidebarWasOpen = sessionStorage.getItem(STORAGE_KEY_SIDEBAR_OPEN) === 'true';
        if (sidebarWasOpen) {
            // Delay opening to ensure DOM is ready
            setTimeout(function() {
                openSidebar();
            }, 100);
        }
    }

    function saveSessionState() {
        if (sessionId) {
            sessionStorage.setItem(STORAGE_KEY_SESSION, sessionId);
        }
        sessionStorage.setItem(STORAGE_KEY_MESSAGES, JSON.stringify(chatMessages));
    }

    function saveSidebarState(isOpen) {
        sessionStorage.setItem(STORAGE_KEY_SIDEBAR_OPEN, isOpen ? 'true' : 'false');
    }

    function clearPersistedState() {
        sessionStorage.removeItem(STORAGE_KEY_SESSION);
        sessionStorage.removeItem(STORAGE_KEY_MESSAGES);
        chatMessages = [];
        sessionId = null;
    }

    function restoreMessages() {
        // If we have messages but no welcome screen, restore them
        if (chatMessages.length > 0) {
            // Clear welcome message
            const welcome = messagesContainer.querySelector('.assistant-welcome');
            if (welcome) {
                welcome.remove();
            }

            // Clear existing messages (in case of re-render)
            messagesContainer.innerHTML = '';

            // Restore all messages
            chatMessages.forEach(function(msg) {
                addMessageToUI(msg.role === 'user' ? 'user' : 'assistant', msg.content, false);
            });
        }
    }

    // =========================================================================
    // Socket.IO Connection
    // =========================================================================

    function initSocket() {
        // Load Socket.IO if not already loaded
        if (typeof io === 'undefined') {
            const script = document.createElement('script');
            script.src = 'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.min.js';
            script.onload = connectSocket;
            document.head.appendChild(script);
        } else {
            connectSocket();
        }
    }

    function connectSocket() {
        updateStatus('connecting', 'Connecting...');

        // Connect to the /agents namespace for WebSocket communication
        socket = io('/agents', {
            path: '/socket.io',
            transports: ['websocket', 'polling']
        });

        socket.on('connect', function() {
            isConnected = true;
            updateStatus('connected', 'Connected');
            console.log('Socket connected to /agents namespace');

            // Try to resume existing session or start new one
            if (sessionId) {
                resumeSession();
            } else {
                startSession();
            }
        });

        socket.on('connected', function(data) {
            console.log('WebSocket connected confirmation:', data);
        });

        socket.on('disconnect', function() {
            isConnected = false;
            updateStatus('error', 'Disconnected');
            sendBtn.disabled = true;
        });

        socket.on('connect_error', function(error) {
            console.error('Socket connection error:', error);
            updateStatus('error', 'Connection failed');
            sendBtn.disabled = true;
        });

        // Handle agent events
        socket.on('agent_event', handleAgentEvent);

        // Handle session started (new session)
        socket.on('session_started', function(data) {
            sessionId = data.session_id;
            console.log('Assistant session started:', sessionId);
            saveSessionState();
            sendBtn.disabled = false;
            updateStatus('connected', 'Ready');
        });

        // Handle session resumed (existing session)
        socket.on('session_resumed', function(data) {
            sessionId = data.session_id;
            console.log('Assistant session resumed:', sessionId);
            saveSessionState();
            restoreMessages();
            sendBtn.disabled = false;
            updateStatus('connected', 'Ready');
        });

        // Handle session expired
        socket.on('session_expired', function(data) {
            console.log('Session expired, starting new one:', data);
            clearPersistedState();
            startSession();
        });

        // Handle errors
        socket.on('error', function(data) {
            console.error('Socket error:', data);
            addMessage('system', 'Error: ' + (data.message || 'Unknown error'));
        });
    }

    function startSession() {
        if (!socket || !isConnected) return;

        socket.emit('start_session', {
            agent_type: 'assistant',
            context: {
                current_page: currentPage
            }
        });
    }

    function resumeSession() {
        if (!socket || !isConnected || !sessionId) return;

        console.log('Attempting to resume session:', sessionId);
        socket.emit('resume_session', {
            session_id: sessionId
        });
    }

    function handleAgentEvent(event) {
        console.log('Agent event:', event);

        switch (event.type) {
            case 'thought':
                // Optionally show agent's thinking
                break;

            case 'tool_call':
                // Optionally show tool usage
                break;

            case 'tool_result':
                // Optionally show tool results
                break;

            case 'final_response':
                hideTypingIndicator();
                if (event.content) {
                    addMessage('assistant', event.content);
                }
                break;

            case 'error':
                hideTypingIndicator();
                addMessage('error', event.content || 'An error occurred');
                break;

            case 'done':
                hideTypingIndicator();
                break;
        }
    }

    // =========================================================================
    // UI Functions
    // =========================================================================

    function toggleSidebar() {
        if (sidebar.classList.contains('open')) {
            closeSidebar();
        } else {
            openSidebar();
        }
    }

    function openSidebar() {
        sidebar.classList.add('open');
        overlay.classList.add('open');
        toggleBtn.classList.add('active');
        inputField.focus();
        saveSidebarState(true);

        // Restore messages if we have them
        if (chatMessages.length > 0 && messagesContainer.querySelector('.assistant-welcome')) {
            restoreMessages();
        }

        // Start session if not connected
        if (!sessionId && isConnected) {
            startSession();
        }
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        overlay.classList.remove('open');
        toggleBtn.classList.remove('active');
        saveSidebarState(false);
    }

    function startNewChat() {
        // Clear state
        clearPersistedState();

        // Clear UI
        messagesContainer.innerHTML = `
            <div class="assistant-welcome">
                <div class="assistant-welcome-icon">
                    <i class="fas fa-robot"></i>
                </div>
                <h4>Hi! I'm your NetStacks Assistant</h4>
                <p>I can help you navigate the app, create MOPs, and build templates.</p>
                <div class="assistant-welcome-suggestions">
                    <button class="assistant-suggestion-btn" data-message="How do I create a MOP?">
                        <i class="fas fa-list-check"></i> How do I create a MOP?
                    </button>
                    <button class="assistant-suggestion-btn" data-message="Help me create a Jinja2 template">
                        <i class="fas fa-file-code"></i> Help me create a template
                    </button>
                    <button class="assistant-suggestion-btn" data-message="Where can I manage devices?">
                        <i class="fas fa-server"></i> Where can I manage devices?
                    </button>
                </div>
            </div>
        `;

        // Re-bind suggestion button events
        messagesContainer.querySelectorAll('.assistant-suggestion-btn').forEach(btn => {
            btn.addEventListener('click', function() {
                const message = this.dataset.message;
                sendMessage(message);
            });
        });

        // Start new session
        if (isConnected) {
            startSession();
        }
    }

    function handleInput() {
        // Auto-resize textarea
        inputField.style.height = 'auto';
        inputField.style.height = Math.min(inputField.scrollHeight, 120) + 'px';

        // Enable/disable send button
        sendBtn.disabled = !inputField.value.trim() || !isConnected;
    }

    function handleKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    function sendMessage(messageText) {
        const message = typeof messageText === 'string' ? messageText : inputField.value.trim();
        if (!message || !isConnected || !sessionId) return;

        // Clear input
        if (typeof messageText !== 'string') {
            inputField.value = '';
            inputField.style.height = 'auto';
            sendBtn.disabled = true;
        }

        // Hide welcome message
        const welcome = messagesContainer.querySelector('.assistant-welcome');
        if (welcome) {
            welcome.remove();
        }

        // Add user message
        addMessage('user', message);

        // Show typing indicator
        showTypingIndicator();

        // Send to agent
        socket.emit('send_message', {
            session_id: sessionId,
            message: message,
            context: {
                current_page: currentPage
            }
        });
    }

    function addMessage(type, content) {
        // Store in memory for persistence
        if (type === 'user' || type === 'assistant') {
            chatMessages.push({
                role: type,
                content: content
            });
            saveSessionState();
        }

        addMessageToUI(type, content, true);
    }

    function addMessageToUI(type, content, scroll) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `assistant-message ${type}`;

        // Process markdown-like formatting for code blocks
        let processedContent = content;
        if (type === 'assistant') {
            processedContent = processContent(content);
        } else {
            processedContent = escapeHtml(content);
        }

        messageDiv.innerHTML = processedContent;
        messagesContainer.appendChild(messageDiv);

        // Scroll to bottom
        if (scroll) {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
    }

    function processContent(content) {
        // Escape HTML first
        let processed = escapeHtml(content);

        // Process code blocks (```code```)
        processed = processed.replace(/```(\w*)\n?([\s\S]*?)```/g, function(match, lang, code) {
            return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
        });

        // Process inline code (`code`)
        processed = processed.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Process bold (**text**)
        processed = processed.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Process links [text](url)
        processed = processed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

        // Process line breaks
        processed = processed.replace(/\n/g, '<br>');

        return processed;
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showTypingIndicator() {
        if (isTyping) return;
        isTyping = true;

        const typingDiv = document.createElement('div');
        typingDiv.className = 'typing-indicator';
        typingDiv.id = 'typing-indicator';
        typingDiv.innerHTML = '<span></span><span></span><span></span>';
        messagesContainer.appendChild(typingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function hideTypingIndicator() {
        isTyping = false;
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.remove();
        }
    }

    function updateStatus(status, text) {
        if (!statusDot || !statusText) return;

        statusDot.className = 'assistant-status-dot ' + status;
        statusText.textContent = text;
    }

    // Expose for external use
    window.NetStacksAssistant = {
        open: openSidebar,
        close: closeSidebar,
        toggle: toggleSidebar,
        sendMessage: sendMessage,
        newChat: startNewChat
    };

})();
