/**
 * NetStacks AI Assistant
 *
 * Handles the sidebar chat interface for the AI assistant.
 * Uses HTTP/SSE (Server-Sent Events) for real-time communication.
 * Persists session and chat history across page navigations.
 */

(function() {
    'use strict';

    // Storage keys
    const STORAGE_KEY_SESSION = 'netstacks_assistant_session';
    const STORAGE_KEY_MESSAGES = 'netstacks_assistant_messages';
    const STORAGE_KEY_SIDEBAR_OPEN = 'netstacks_assistant_sidebar_open';

    // State
    let sessionId = null;
    let isProcessing = false;
    let currentPage = window.location.pathname;
    let chatMessages = [];  // In-memory message cache
    let currentEventSource = null;  // For SSE connection
    let assistantAgentId = null;  // The agent ID to use for chat

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
        // Check if assistant is enabled before initializing
        checkAssistantEnabled().then(function(config) {
            if (!config.enabled) {
                console.log('AI Assistant is disabled');
                return;
            }

            // Store the agent ID if provided
            assistantAgentId = config.agentId;

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

            // Update status to ready
            updateStatus('connected', 'Ready');
        });
    }

    // Check if the assistant is enabled in settings
    function checkAssistantEnabled() {
        return new Promise(function(resolve) {
            $.get('/api/settings/assistant/config')
                .done(function(data) {
                    if (data.config) {
                        resolve({
                            enabled: data.config.enabled === true || data.config.enabled === 'true',
                            agentId: data.config.agent_id || null
                        });
                    } else {
                        resolve({ enabled: false, agentId: null });
                    }
                })
                .fail(function(error) {
                    console.warn('Could not check assistant config:', error);
                    resolve({ enabled: false, agentId: null });
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
                    <span class="assistant-status-text">Ready</span>
                </div>

                <div id="assistant-messages" class="assistant-messages">
                    <div class="assistant-welcome">
                        <div class="assistant-welcome-icon">
                            <i class="fas fa-robot"></i>
                        </div>
                        <h4>Hi! I'm your NetStacks Assistant</h4>
                        <p>I can help you with network operations, troubleshooting, and navigating the platform.</p>
                        <div class="assistant-welcome-suggestions">
                            <button class="assistant-suggestion-btn" data-message="What can you help me with?">
                                <i class="fas fa-question-circle"></i> What can you help me with?
                            </button>
                            <button class="assistant-suggestion-btn" data-message="Show me the network status">
                                <i class="fas fa-network-wired"></i> Show network status
                            </button>
                            <button class="assistant-suggestion-btn" data-message="Help me troubleshoot a device">
                                <i class="fas fa-wrench"></i> Troubleshoot a device
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
                        <button id="assistant-send-btn" class="assistant-send-btn">
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
        sendBtn.addEventListener('click', function() { sendMessage(); });

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
    // Chat API Communication
    // =========================================================================

    async function startSession() {
        if (!assistantAgentId) {
            // Try to find an assistant agent
            try {
                const response = await $.get('/api/agents/');
                const agents = response.agents || response || [];
                const assistantAgent = agents.find(a =>
                    a.agent_type === 'assistant' ||
                    a.name.toLowerCase().includes('assistant')
                );
                if (assistantAgent) {
                    assistantAgentId = assistantAgent.agent_id;
                } else if (agents.length > 0) {
                    // Use first available enabled agent
                    const enabledAgent = agents.find(a => a.is_enabled);
                    if (enabledAgent) {
                        assistantAgentId = enabledAgent.agent_id;
                    }
                }
            } catch (e) {
                console.warn('Could not fetch agents:', e);
            }
        }

        if (!assistantAgentId) {
            addMessage('system', 'No AI agent is configured. Please set up an agent in the AI Agents settings.');
            updateStatus('error', 'No agent configured');
            return false;
        }

        try {
            updateStatus('connecting', 'Starting session...');

            const response = await $.ajax({
                url: '/api/chat/start',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ agent_id: assistantAgentId })
            });

            if (response.success && response.session_id) {
                sessionId = response.session_id;
                saveSessionState();
                console.log('Started chat session:', sessionId);
                updateStatus('connected', 'Ready');
                return true;
            } else {
                throw new Error('Failed to start session');
            }
        } catch (error) {
            console.error('Error starting session:', error);
            const errorMsg = error.responseJSON?.detail || error.message || 'Failed to start session';
            addMessage('system', 'Error: ' + errorMsg);
            updateStatus('error', 'Connection failed');
            return false;
        }
    }

    async function sendMessage(messageText) {
        const message = typeof messageText === 'string' ? messageText : inputField.value.trim();
        if (!message || isProcessing) return;

        // Clear input
        if (typeof messageText !== 'string') {
            inputField.value = '';
            inputField.style.height = 'auto';
        }

        // Hide welcome message
        const welcome = messagesContainer.querySelector('.assistant-welcome');
        if (welcome) {
            welcome.remove();
        }

        // Add user message
        addMessage('user', message);

        // Start session if needed
        if (!sessionId) {
            const started = await startSession();
            if (!started) return;
        }

        // Show typing indicator
        isProcessing = true;
        sendBtn.disabled = true;
        updateStatus('processing', 'Thinking...');
        showTypingIndicator();

        try {
            // Use the sync endpoint for simpler handling
            const response = await $.ajax({
                url: `/api/chat/${sessionId}/message/sync`,
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ message: message }),
                timeout: 120000  // 2 minute timeout for long responses
            });

            hideTypingIndicator();

            if (response.success && response.response) {
                addMessage('assistant', response.response);
            } else if (response.error) {
                addMessage('system', 'Error: ' + response.error);
            } else {
                addMessage('system', 'No response received from assistant.');
            }

        } catch (error) {
            hideTypingIndicator();
            console.error('Error sending message:', error);

            // Check if session expired
            if (error.status === 404 || error.status === 400) {
                // Session invalid, clear and retry
                sessionId = null;
                sessionStorage.removeItem(STORAGE_KEY_SESSION);
                addMessage('system', 'Session expired. Please try again.');
            } else {
                const errorMsg = error.responseJSON?.detail || error.message || 'Failed to send message';
                addMessage('system', 'Error: ' + errorMsg);
            }
        } finally {
            isProcessing = false;
            sendBtn.disabled = !inputField.value.trim();
            updateStatus('connected', 'Ready');
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
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        overlay.classList.remove('open');
        toggleBtn.classList.remove('active');
        saveSidebarState(false);
    }

    function startNewChat() {
        // End current session if exists
        if (sessionId) {
            $.ajax({
                url: `/api/chat/${sessionId}/end`,
                method: 'POST',
                contentType: 'application/json'
            }).catch(function() {
                // Ignore errors when ending session
            });
        }

        // Clear state
        clearPersistedState();

        // Clear UI
        messagesContainer.innerHTML = `
            <div class="assistant-welcome">
                <div class="assistant-welcome-icon">
                    <i class="fas fa-robot"></i>
                </div>
                <h4>Hi! I'm your NetStacks Assistant</h4>
                <p>I can help you with network operations, troubleshooting, and navigating the platform.</p>
                <div class="assistant-welcome-suggestions">
                    <button class="assistant-suggestion-btn" data-message="What can you help me with?">
                        <i class="fas fa-question-circle"></i> What can you help me with?
                    </button>
                    <button class="assistant-suggestion-btn" data-message="Show me the network status">
                        <i class="fas fa-network-wired"></i> Show network status
                    </button>
                    <button class="assistant-suggestion-btn" data-message="Help me troubleshoot a device">
                        <i class="fas fa-wrench"></i> Troubleshoot a device
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

        updateStatus('connected', 'Ready');
    }

    function handleInput() {
        // Auto-resize textarea
        inputField.style.height = 'auto';
        inputField.style.height = Math.min(inputField.scrollHeight, 120) + 'px';

        // Enable/disable send button
        sendBtn.disabled = !inputField.value.trim() || isProcessing;
    }

    function handleKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
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
        if (type === 'assistant' || type === 'system') {
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

        // Process navigation commands [[Navigate: text | /path]]
        processed = processed.replace(/\[\[Navigate:\s*([^\|]+)\s*\|\s*([^\]]+)\]\]/g, function(match, text, path) {
            return `<button class="assistant-nav-btn" onclick="window.NetStacksAssistant.navigateTo('${path.trim()}')">${text.trim()} <i class="fas fa-arrow-right"></i></button>`;
        });

        // Process regular links [text](url) - make internal links navigatable
        processed = processed.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function(match, text, url) {
            // Check if it's an internal link (starts with /)
            if (url.startsWith('/')) {
                return `<a href="${url}" class="assistant-internal-link" onclick="event.preventDefault(); window.NetStacksAssistant.navigateTo('${url}')">${text}</a>`;
            }
            return `<a href="${url}" target="_blank">${text}</a>`;
        });

        // Process line breaks
        processed = processed.replace(/\n/g, '<br>');

        return processed;
    }

    function navigateTo(path) {
        // Close sidebar first
        closeSidebar();

        // Navigate after a brief delay for smooth transition
        setTimeout(function() {
            window.location.href = path;
        }, 150);
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function showTypingIndicator() {
        const existing = document.getElementById('typing-indicator');
        if (existing) return;

        const typingDiv = document.createElement('div');
        typingDiv.className = 'typing-indicator';
        typingDiv.id = 'typing-indicator';
        typingDiv.innerHTML = '<span></span><span></span><span></span>';
        messagesContainer.appendChild(typingDiv);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function hideTypingIndicator() {
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
        newChat: startNewChat,
        navigateTo: navigateTo
    };

})();
