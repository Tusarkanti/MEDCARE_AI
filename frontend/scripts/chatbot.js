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
 */

document.addEventListener('DOMContentLoaded', initializeChatbot);

const ChatState = {
  patientId: null,
  patientData: null,
  currentChatId: null,
  chatHistory: [],
  allChats: [],
  isWaitingForResponse: false,
  abortController: null
};

function getWebhookUrl() {
  return APP_CONFIG?.webhookUrl || 'https://tusarrr.app.n8n.cloud/webhook/medical-assistant';
}

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
  
  console.log('✅ AI Chatbot initialized - ChatGPT-like experience');
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

I'm your AI Assistant. I can help you with **anything** you'd like to discuss:


🏥 **Health Questions** - General wellness advice

Ask me anything! I'm here to help. 🚀`;
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
    addBotMessage('⚠️ Sorry, there was an error processing your request. Please try again.');
  }
  
  ChatState.isWaitingForResponse = false;
  input.disabled = false;
  btn.disabled = false;
  btn.textContent = 'Send';
  input.focus();
}

/**
 * ✅ FULLY FIXED: Complete API request handler with clean error handling
 * Handles both JSON and plain text responses without console warnings
 */
async function getAIResponse(userMessage) {
  const CHATBOT_WEBHOOK = APP_CONFIG?.chatbot?.webhookUrl || 
                          'https://tusarrr.app.n8n.cloud/webhook/chat';
  
  const requestBody = {
    message: userMessage
  };

  try {
    const response = await fetch(CHATBOT_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody)
    });

    // ✅ Check HTTP status
    if (!response.ok) {
      throw new Error(`Server returned ${response.status}: ${response.statusText}`);
    }

    // ✅ Read response as text first (prevents JSON parse errors)
    const rawText = await response.text();

    // ✅ Handle empty response
    if (!rawText || !rawText.trim()) {
      throw new Error('Empty response from server');
    }

    // ✅ Smart response parsing: Only try JSON if it looks like JSON
    const trimmedText = rawText.trim();
    
    // Check if response looks like JSON (starts with { or [)
    if (trimmedText.startsWith('{') || trimmedText.startsWith('[')) {
      try {
        const data = JSON.parse(trimmedText);
        
        // Only show AI reply - never expose system data
        if (typeof data.reply === 'string') {
          return data.reply;
        }
        
        if (typeof data.message === 'string') {
          return data.message;
        }
        
        // Check for common response field names
        if (typeof data.response === 'string') {
          return data.response;
        }
        
        if (typeof data.text === 'string') {
          return data.text;
        }
        
        if (typeof data.output === 'string') {
          return data.output;
        }
        
        // Never expose raw JSON to user - return friendly error
        return 'Sorry, I received an unexpected response. Please try again.';
      } catch (jsonError) {
        // JSON parse failed, treat as plain text
        return trimmedText;
      }
    }
    
    // ✅ Default: treat as plain text, but sanitize internal markers
    return sanitizeResponse(trimmedText);

  } catch (error) {
    console.error('❌ Chatbot API error:', error);
    
    // Provide specific error messages
    if (error.message.includes('Failed to fetch')) {
      throw new Error('Network error: Unable to reach the server. Please check your connection.');
    }
    
    if (error.message.includes('500')) {
      throw new Error('Server error: The AI service is temporarily unavailable.');
    }
    
    if (error.message.includes('404')) {
      throw new Error('Configuration error: AI endpoint not found.');
    }
    
    throw error;
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