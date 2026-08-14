/**
 * AI Chatbot - Full Conversational Assistant (ChatGPT-like)
 * Features:
 * - Full conversation like ChatGPT - chat about anything
 * - Chat history with save/delete/continue
 * - Streaming-like text effect
 * - Code syntax highlighting
 * - Markdown rendering
 * - Context-aware conversations
 * - Clean error handling (no console warnings)
 * 
 * Backend-only architecture:
 * - Uses local backend API for AI responses
 */

document.addEventListener('DOMContentLoaded', initializeChatbot);

const ChatState = {
  patientId: null,
  patientData: null,
  currentChatId: null,
  chatHistory: [],
  allChats: [],
  isWaitingForResponse: false,
  abortController: null,
  useLocalModel: true // Flag to track which API to use
};

function _apiBase() {
  return typeof getApiBaseUrl === 'function' ? getApiBaseUrl() : APP_CONFIG.localServer.baseUrl;
}

/** v2 JWT + MongoDB persisted chat */
function getChatbotApiUrl() {
  return _apiBase() + '/api/v2/chat/send';
}

function getChatbotUrl() {
  return getChatbotApiUrl();
}

/** Connection help: call on load and after failed sends */
function refreshChatbotBackendBanner() {
  const el = document.getElementById('chatbot-connection-banner');
  if (!el) return;
  const base = _apiBase();
  if (window.location.protocol === 'file:') {
    el.style.display = 'block';
    el.className = 'chatbot-connection-banner err';
    el.innerHTML =
      'Do not open this page from disk (<code>file://</code>). Run a local web server in the <code>frontend</code> folder: <code>python -m http.server 5500</code> — then open <a href="http://127.0.0.1:5500/chatbot.html" style="color:#fecaca;text-decoration:underline">http://127.0.0.1:5500/chatbot.html</a>.';
    return;
  }
  fetch(base + '/api/chatbot/health', { method: 'GET' })
    .then((r) => {
      if (!r.ok) throw new Error('bad status');
      return r.json();
    })
    .then(() => {
      el.style.display = 'block';
      el.className = 'chatbot-connection-banner ok';
      el.textContent = 'Connected to MedCare backend at ' + base;
      setTimeout(() => {
        el.style.display = 'none';
      }, 5000);
    })
    .catch(() => {
      el.style.display = 'block';
      el.className = 'chatbot-connection-banner err';
      el.innerHTML =
        'Cannot reach the API at <strong>' +
        base +
        '</strong>. Start the server: open a terminal in the <code>backend</code> folder and run <code>python app.py</code>, then click Retry or refresh. <button type="button" class="chatbot-banner-retry">Retry</button>';
      const btn = el.querySelector('.chatbot-banner-retry');
      if (btn) {
        btn.onclick = () => refreshChatbotBackendBanner();
      }
    });
}

window.refreshChatbotBackendBanner = refreshChatbotBackendBanner;

async function initializeChatbot() {
  ChatState.patientId = localStorage.getItem('medcare_mobile_number');
  
  if (ChatState.patientId) {
    const stored = localStorage.getItem(`medcare_patient_${ChatState.patientId}`);
    if (stored) {
      ChatState.patientData = JSON.parse(stored);
    }
  }
  
  loadAllChats();
  setupChatInput();
  setupSendButton();
  renderChatSidebar();
  
  if (!ChatState.currentChatId) {
    startNewChat();
  }

  refreshChatbotBackendBanner();
  console.log('AI Chatbot initialized');
}

function loadAllChats() {
  const chatsKey = ChatState.patientId 
    ? `medcare_chats_${ChatState.patientId}` 
    : 'medcare_chats_guest';
  
  const stored = localStorage.getItem(chatsKey);
  if (stored) {
    try {
      ChatState.allChats = JSON.parse(stored);
    } catch (e) {
      ChatState.allChats = [];
    }
  }
}

function saveAllChats() {
  const chatsKey = ChatState.patientId 
    ? `medcare_chats_${ChatState.patientId}` 
    : 'medcare_chats_guest';
  
  localStorage.setItem(chatsKey, JSON.stringify(ChatState.allChats));
}

function startNewChat() {
  const chatId = 'chat_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  const newChat = {
    id: chatId,
    title: 'New Conversation',
    messages: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString()
  };
  
  ChatState.allChats.unshift(newChat);
  ChatState.currentChatId = chatId;
  ChatState.chatHistory = [];
  
  saveAllChats();
  renderChatSidebar();
  clearChatWindow();
  
  const welcomeMessage = getWelcomeMessage();
  addBotMessage(welcomeMessage);
}

function getWelcomeMessage() {
  const name = ChatState.patientData?.full_name || ChatState.patientData?.patient_name || '';
  const greeting = name ? `Hello, ${name}! 👋` : 'Hello! 👋';
  
  return `${greeting}

I'm your **AI Health Assistant** - like having a knowledgeable friend who's always there to help! 🏥

I can assist you with virtually **ANYTHING** you'd like to know:

🩺 **Health & Medical**
   - Symptoms, conditions, and health concerns
   - Medication information and side effects
   - First aid and emergency guidance

🥗 **Nutrition & Wellness**
   - Healthy eating plans and diet tips
   - Vitamin and supplement advice
   - Weight management strategies

🏃 **Fitness & Exercise**
   - Workout recommendations
   - Exercise routines for all levels
   - Recovery and injury prevention

🧠 **Mental Health**
   - Stress management techniques
   - Sleep improvement tips
   - Mindfulness and meditation guidance

💡 **General Knowledge**
   - Science, technology, and more
   - Quick explanations on any topic
   - Health news and updates

**Just ask me anything!** I'm here to help 24/7. 🚀

*Note: For serious medical concerns, always consult a healthcare professional.*`;
}

function loadChat(chatId) {
  const chat = ChatState.allChats.find(c => c.id === chatId);
  if (!chat) return;
  
  ChatState.currentChatId = chatId;
  ChatState.chatHistory = [...chat.messages];
  
  clearChatWindow();
  
  if (chat.messages.length === 0) {
    addBotMessage(getWelcomeMessage());
  } else {
    chat.messages.forEach(msg => {
      if (msg.role === 'user') {
        addUserMessageToWindow(msg.content, msg.timestamp);
      } else {
        addBotMessageToWindow(msg.content, msg.timestamp);
      }
    });
  }
  
  renderChatSidebar();
}

function deleteChat(chatId) {
  if (!confirm('Are you sure you want to delete this conversation?')) return;
  
  ChatState.allChats = ChatState.allChats.filter(c => c.id !== chatId);
  saveAllChats();
  
  if (ChatState.currentChatId === chatId) {
    if (ChatState.allChats.length > 0) {
      loadChat(ChatState.allChats[0].id);
    } else {
      startNewChat();
    }
  }
  
  renderChatSidebar();
}

function renderChatSidebar() {
  const sidebar = document.getElementById('chat-sidebar');
  if (!sidebar) return;
  
  sidebar.innerHTML = `
    <div class="chat-sidebar-header">
      <h3>💬 Conversations</h3>
      <button class="new-chat-btn" onclick="startNewChat()" title="Start new conversation">
        <span>+</span> New Chat
      </button>
    </div>
    <div class="chat-list">
      ${ChatState.allChats.length === 0 ? `
        <div class="no-chats-message">
          <p>No conversations yet</p>
          <p style="font-size: 0.8rem; opacity: 0.7;">Start a new chat to begin</p>
        </div>
      ` : ChatState.allChats.map(chat => `
        <div class="chat-list-item ${chat.id === ChatState.currentChatId ? 'active' : ''}" 
             onclick="loadChat('${chat.id}')">
          <div class="chat-item-content">
            <div class="chat-item-title">${escapeHtml(chat.title)}</div>
            <div class="chat-item-date">${formatChatDate(chat.updatedAt)}</div>
          </div>
          <button class="delete-chat-btn" onclick="event.stopPropagation(); deleteChat('${chat.id}')" title="Delete">
            🗑️
          </button>
        </div>
      `).join('')}
    </div>
  `;
}

function setupChatInput() {
  const input = document.getElementById('chat-input');
  if (!input) return;
  
  input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 150) + 'px';
  });
  
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

function setupSendButton() {
  const btn = document.getElementById('send-button');
  if (btn) btn.addEventListener('click', sendMessage);
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('send-button');
  
  if (!input || !btn) return;
  
  const message = input.value.trim();
  if (!message || ChatState.isWaitingForResponse) return;
  
  ChatState.isWaitingForResponse = true;
  input.disabled = true;
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-loading"></span>';
  
  const timestamp = new Date().toISOString();
  addUserMessage(message, timestamp);
  input.value = '';
  input.style.height = 'auto';
  
  const typingId = showTyping();
  
  try {
    const response = await getAIResponse(message);
    removeTyping(typingId);
    await addBotMessageWithTyping(response, new Date().toISOString());
  } catch (error) {
    console.error('Chat error:', error);
    removeTyping(typingId);
    refreshChatbotBackendBanner();
    const hint =
      (error && error.message) ||
      'Unable to reach the server. Start the backend (python app.py in backend folder) and use http://127.0.0.1:5500/chatbot.html (not file://).';
    addBotMessage(
      '**Could not get a reply.**\n\n' +
        hint +
        '\n\n**Checklist:**\n1. Backend running: `cd backend` → `python app.py`\n2. Open the site via **http://127.0.0.1:5500/chatbot.html** (serve `frontend` with `python -m http.server 5500`).'
    );
  }
  
  ChatState.isWaitingForResponse = false;
  input.disabled = false;
  btn.disabled = false;
  btn.textContent = 'Send';
  input.focus();
}

/**
 * Complete backend API request handler with clean error handling.
 */
async function getAIResponse(userMessage) {
  const apiBase = _apiBase();
  try {
    function getUsableAuthToken() {
      const rawToken = (typeof getToken === 'function' ? getToken() : '') || '';
      if (!rawToken || typeof rawToken !== 'string') return '';

      // JWT must contain 3 base64url sections.
      const parts = rawToken.split('.');
      if (parts.length !== 3) {
        localStorage.removeItem('medcare_token');
        return '';
      }

      try {
        const payloadJson = atob(parts[1].replace(/-/g, '+').replace(/_/g, '/'));
        const payload = JSON.parse(payloadJson);
        const now = Math.floor(Date.now() / 1000);
        if (typeof payload.exp === 'number' && payload.exp <= now) {
          // Expired token; clear it to avoid repeated 401 calls.
          localStorage.removeItem('medcare_token');
          return '';
        }
      } catch (e) {
        localStorage.removeItem('medcare_token');
        return '';
      }

      return rawToken;
    }

    async function sendChatRequest(useV2Route, token) {
      const endpoint = useV2Route ? getChatbotUrl() : apiBase + '/api/chatbot';

      const headers = {
        'Content-Type': 'application/json'
      };
      if (useV2Route) {
        headers.Authorization = `Bearer ${token}`;
      }

      const body = useV2Route
        ? { message: userMessage, chat_id: ChatState.currentChatId || null }
        : { message: userMessage, session_id: ChatState.currentChatId || 'guest' };

      return fetch(endpoint, {
        method: 'POST',
        headers,
        body: JSON.stringify(body)
      });
    }

    const token = getUsableAuthToken();
    const useV2Route = Boolean(token);
    let response = await sendChatRequest(useV2Route, token);

    // If auth token is invalid/expired, gracefully retry as guest route.
    if (response.status === 401 && useV2Route) {
      response = await sendChatRequest(false, '');
    }

    // ✅ Check HTTP status
    if (!response.ok) {
      throw new Error(`Server returned ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    if (data.success && data.response) {
      let enrichedResponse = data.response;
      if (Array.isArray(data.suggested_symptoms) && data.suggested_symptoms.length > 0) {
        enrichedResponse += `\n\nRecognized symptoms: ${data.suggested_symptoms.join(', ')}`;
      }
      if (data.triage?.is_emergency) {
        enrichedResponse += '\n\nIf symptoms are severe or worsening, seek emergency care immediately.';
      }
      return enrichedResponse;
    }
    throw new Error(data.error || 'Unexpected response from backend');

  } catch (error) {
    console.error('Chatbot API error:', error);

    if (
      (error && error.message && error.message.includes('Failed to fetch')) ||
      (error && error.name === 'TypeError')
    ) {
      throw new Error(
        'Cannot connect to ' +
          apiBase +
          '. Start the Flask app (python app.py in backend). If you opened this page from disk, use http://127.0.0.1:5500/chatbot.html instead.'
      );
    }
    
    if (error.message.includes('500')) {
      throw new Error('Server error: The AI service is temporarily unavailable.');
    }
    
    throw new Error(error.message || 'AI service unavailable');
  }
}

/**
 * Sanitize AI response - remove internal prompts/markers that shouldn't be shown
 */
function sanitizeResponse(text) {
  if (!text) return 'Sorry, I could not generate a response.';
  
  let cleaned = text;
  
  // Remove common internal markers
  const patternsToRemove = [
    /^\.?\s*\n*/,                                    // Leading dots/whitespace
    /The user is an? \w+\.\s*\n*---\s*\n*/gi,       // "The user is an adult. ---"
    /User message:\s*\n*/gi,                         // "User message:"
    /---\s*$/g,                                      // Trailing ---
    /^\s*---\s*\n*/g,                               // Leading ---
    /System:\s*\n*/gi,                              // "System:"
    /Assistant:\s*\n*/gi,                           // "Assistant:"
    /Human:\s*\n*/gi,                               // "Human:"
  ];
  
  for (const pattern of patternsToRemove) {
    cleaned = cleaned.replace(pattern, '');
  }
  
  // If response starts with the user's own question, try to extract just the answer
  // Look for common AI response starters after removing noise
  cleaned = cleaned.trim();
  
  // If still contains internal structure, extract meaningful content
  if (cleaned.includes('---') && cleaned.split('---').length > 1) {
    const parts = cleaned.split('---').filter(p => p.trim());
    // Take the last meaningful part (usually the actual response)
    if (parts.length > 0) {
      cleaned = parts[parts.length - 1].trim();
    }
  }
  
  // Final cleanup
  cleaned = cleaned.trim();
  
  if (!cleaned || cleaned === '.') {
    return 'I apologize, but I could not generate a proper response. Please try again.';
  }
  
  return cleaned;
}

function getSystemPrompt() {
  return `You are a highly capable AI assistant, similar to ChatGPT. You can help with virtually any topic:

CAPABILITIES:
- Answer questions on any subject (science, history, technology, arts, etc.)
- Write and debug code in any programming language
- Help with creative writing, essays, and content creation
- Explain complex concepts in simple terms
- Solve math problems step by step
- Provide language translation and grammar help
- Brainstorm ideas and provide suggestions
- Analyze data and provide insights
- Help with research and learning

GUIDELINES:
- Be helpful, accurate, and thorough
- Use markdown formatting for better readability
- When writing code, always use proper code blocks with language specification
- For math, show step-by-step solutions
- Be conversational and engaging
- Admit when you don't know something
- Provide balanced, factual information
- Be concise but comprehensive

FORMAT:
- Use **bold** for emphasis
- Use \`code\` for inline code
- Use code blocks with language for multi-line code
- Use bullet points for lists
- Use numbered lists for steps
- Use headers (##) for sections in longer responses`;
}

function buildConversationHistory() {
  const history = [];
  const recentMessages = ChatState.chatHistory.slice(-20);
  
  for (const msg of recentMessages) {
    history.push({
      role: msg.role === 'user' ? 'user' : 'model',
      parts: [{ text: msg.content }]
    });
  }
  
  return history;
}

function addUserMessage(content, timestamp) {
  ChatState.chatHistory.push({
    role: 'user',
    content: content,
    timestamp: timestamp
  });
  
  addUserMessageToWindow(content, timestamp);
  updateCurrentChat();
}

function addBotMessage(content, timestamp = new Date().toISOString()) {
  ChatState.chatHistory.push({
    role: 'assistant',
    content: content,
    timestamp: timestamp
  });
  
  addBotMessageToWindow(content, timestamp);
  updateCurrentChat();
}

async function addBotMessageWithTyping(content, timestamp) {
  ChatState.chatHistory.push({
    role: 'assistant',
    content: content,
    timestamp: timestamp
  });
  
  await addBotMessageToWindowWithTyping(content, timestamp);
  updateCurrentChat();
}

function addUserMessageToWindow(content, timestamp) {
  const chatWindow = document.getElementById('chat-window');
  if (!chatWindow) return;
  
  const div = document.createElement('div');
  div.className = 'chat-message user-message';
  div.innerHTML = `
    <div class="message-avatar">👤</div>
    <div class="message-content">
      <div class="message-text">${escapeHtml(content)}</div>
      <div class="message-time">${formatTime(timestamp)}</div>
    </div>
  `;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addBotMessageToWindow(content, timestamp) {
  const chatWindow = document.getElementById('chat-window');
  if (!chatWindow) return;
  
  const div = document.createElement('div');
  div.className = 'chat-message bot-message';
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <div class="message-text">${formatMarkdown(content)}</div>
      <div class="message-time">${formatTime(timestamp)}</div>
      <div class="message-actions">
        <button class="copy-btn" onclick="copyMessage(this)" title="Copy">📋</button>
      </div>
    </div>
  `;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  
  highlightCodeBlocks(div);
}

async function addBotMessageToWindowWithTyping(content, timestamp) {
  const chatWindow = document.getElementById('chat-window');
  if (!chatWindow) return;
  
  const div = document.createElement('div');
  div.className = 'chat-message bot-message';
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <div class="message-text"></div>
      <div class="message-time">${formatTime(timestamp)}</div>
      <div class="message-actions">
        <button class="copy-btn" onclick="copyMessage(this)" title="Copy">📋</button>
      </div>
    </div>
  `;
  chatWindow.appendChild(div);
  
  const textDiv = div.querySelector('.message-text');
  
  const words = content.split(' ');
  let displayedContent = '';
  
  for (let i = 0; i < words.length; i += 3) {
    const chunk = words.slice(i, i + 3).join(' ');
    displayedContent += (displayedContent ? ' ' : '') + chunk;
    textDiv.innerHTML = formatMarkdown(displayedContent);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  
  textDiv.innerHTML = formatMarkdown(content);
  highlightCodeBlocks(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function updateCurrentChat() {
  const chat = ChatState.allChats.find(c => c.id === ChatState.currentChatId);
  if (!chat) return;
  
  chat.messages = [...ChatState.chatHistory];
  chat.updatedAt = new Date().toISOString();
  
  if (ChatState.chatHistory.length > 0 && chat.title === 'New Conversation') {
    const firstUserMsg = ChatState.chatHistory.find(m => m.role === 'user');
    if (firstUserMsg) {
      chat.title = firstUserMsg.content.substring(0, 35) + (firstUserMsg.content.length > 35 ? '...' : '');
    }
  }
  
  saveAllChats();
  renderChatSidebar();
}

function showTyping() {
  const chatWindow = document.getElementById('chat-window');
  if (!chatWindow) return null;
  
  const div = document.createElement('div');
  div.className = 'chat-message bot-message';
  div.id = 'typing-' + Date.now();
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <div class="typing-indicator"><span></span><span></span><span></span></div>
    </div>
  `;
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return div.id;
}

function removeTyping(id) {
  if (id) document.getElementById(id)?.remove();
}

function clearChatWindow() {
  const chatWindow = document.getElementById('chat-window');
  if (chatWindow) chatWindow.innerHTML = '';
}

function formatMarkdown(text) {
  if (!text) return '';
  
  let html = text;
  
  // Code blocks with language
  html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
    const language = lang || 'plaintext';
    const escapedCode = escapeHtml(code.trim());
    return `<div class="code-block"><div class="code-header"><span class="code-lang">${language}</span><button class="code-copy-btn" onclick="copyCode(this)">Copy</button></div><pre><code class="language-${language}">${escapedCode}</code></pre></div>`;
  });
  
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
  
  // Bold and italic
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
  
  // Headers
  html = html.replace(/^### (.*$)/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.*$)/gm, '<h3>$1</h3>');
  html = html.replace(/^# (.*$)/gm, '<h2>$1</h2>');
  
  // Lists
  html = html.replace(/^\d+\.\s+(.*$)/gm, '<li class="numbered-item">$1</li>');
  html = html.replace(/^[-•]\s+(.*$)/gm, '<li class="bullet-item">$1</li>');
  
  // Line breaks
  html = html.replace(/\n/g, '<br>');
  
  // Wrap lists
  html = html.replace(/(<li class="numbered-item">.*?<\/li>(<br>)?)+/g, (match) => {
    return '<ol>' + match.replace(/<br>/g, '') + '</ol>';
  });
  
  html = html.replace(/(<li class="bullet-item">.*?<\/li>(<br>)?)+/g, (match) => {
    return '<ul>' + match.replace(/<br>/g, '') + '</ul>';
  });
  
  return html;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function highlightCodeBlocks(container) {
  if (typeof Prism !== 'undefined') {
    Prism.highlightAllUnder(container);
  }
}

function copyMessage(btn) {
  const messageText = btn.closest('.message-content').querySelector('.message-text');
  const text = messageText.innerText || messageText.textContent;
  navigator.clipboard.writeText(text).then(() => {
    const originalText = btn.textContent;
    btn.textContent = '✓';
    setTimeout(() => btn.textContent = originalText, 1500);
  });
}

function copyCode(btn) {
  const codeBlock = btn.closest('.code-block').querySelector('code');
  const code = codeBlock.textContent;
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = 'Copy', 1500);
  });
}

function formatTime(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatChatDate(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  const now = new Date();
  const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
  
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function clearChatHistory() {
  if (confirm('Clear this conversation? This cannot be undone.')) {
    ChatState.chatHistory = [];
    clearChatWindow();
    addBotMessage(getWelcomeMessage());
    updateCurrentChat();
  }
}

function exportChatHistory() {
  const chat = ChatState.allChats.find(c => c.id === ChatState.currentChatId);
  if (!chat) return;
  
  let text = `Chat Export - ${chat.title}\n`;
  text += `Date: ${new Date().toLocaleString()}\n`;
  text += '='.repeat(50) + '\n\n';
  
  chat.messages.forEach(msg => {
    const role = msg.role === 'user' ? 'You' : 'AI Assistant';
    const time = formatTime(msg.timestamp);
    text += `[${time}] ${role}:\n${msg.content}\n\n`;
  });
  
  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `chat-${chat.id}.txt`;
  a.click();
}

function sendSuggestion(text) {
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = text;
    sendMessage();
  }
}

// Global exports
window.startNewChat = startNewChat;
window.loadChat = loadChat;
window.deleteChat = deleteChat;
window.clearChatHistory = clearChatHistory;
window.exportChatHistory = exportChatHistory;
window.sendSuggestion = sendSuggestion;
window.copyMessage = copyMessage;
window.copyCode = copyCode;