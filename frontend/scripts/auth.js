/**
 * Authentication System
 * Email verification-based auth using n8n webhook
 * Features: Signup, Login, Email Verification, Session Management
 */

const AUTH_CONFIG = {
  API_URL: 'https://tusarrr.app.n8n.cloud/webhook/medical-assistant',
  SESSION_KEY: 'medcare_session',
  USER_KEY: 'medcare_user'
};

// ============================================================================
// Session Management
// ============================================================================

function getSession() {
  try {
    const session = localStorage.getItem(AUTH_CONFIG.SESSION_KEY);
    return session ? JSON.parse(session) : null;
  } catch {
    return null;
  }
}

function getUser() {
  try {
    const user = localStorage.getItem(AUTH_CONFIG.USER_KEY);
    return user ? JSON.parse(user) : null;
  } catch {
    return null;
  }
}

function saveSession(sessionData, userData) {
  localStorage.setItem(AUTH_CONFIG.SESSION_KEY, JSON.stringify({
    ...sessionData,
    createdAt: new Date().toISOString()
  }));
  localStorage.setItem(AUTH_CONFIG.USER_KEY, JSON.stringify(userData));
}

function clearSession() {
  localStorage.removeItem(AUTH_CONFIG.SESSION_KEY);
  localStorage.removeItem(AUTH_CONFIG.USER_KEY);
}

function isLoggedIn() {
  const session = getSession();
  return session !== null;
}

// ============================================================================
// Auth Protection
// ============================================================================

function requireAuth() {
  if (!isLoggedIn()) {
    window.location.href = 'login.html';
    return false;
  }
  return true;
}

function redirectIfLoggedIn() {
  if (isLoggedIn()) {
    window.location.href = 'index.html';
    return true;
  }
  return false;
}

// ============================================================================
// API Calls
// ============================================================================

async function authRequest(data) {
  try {
    const response = await fetch(AUTH_CONFIG.API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify(data)
    });
    
    // Try to parse JSON, handle empty response
    let result = {};
    const text = await response.text();
    
    if (text && text.trim()) {
      try {
        result = JSON.parse(text);
      } catch (parseError) {
        console.warn('Response is not JSON:', text);
        result = { message: text };
      }
    }
    
    // If response is empty but status is OK, treat as success
    if (response.ok && Object.keys(result).length === 0) {
      result = { success: true };
    }
    
    return { success: response.ok, data: result };
  } catch (error) {
    console.error('Auth request failed:', error);
    
    // Check if it's a CORS error (likely testing locally)
    if (error.message.includes('Failed to fetch') || error.name === 'TypeError') {
      console.warn('⚠️ CORS Error: You may be testing locally. Please test from: https://medtech-hackathon-482215.web.app');
      
      // For local development, simulate success to allow UI testing
      if (window.location.protocol === 'file:' || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        console.log('📝 Local development mode - simulating auth for UI testing');
        return handleLocalDevelopment(data);
      }
    }
    
    return { success: false, error: 'Network error. Please check your connection or try from the deployed site.' };
  }
}

// Handle local development without backend
function handleLocalDevelopment(data) {
  const action = data.action;
  
  switch (action) {
    case 'signup':
      // Simulate signup success
      return { 
        success: true, 
        data: { 
          success: true, 
          message: '[DEV MODE] Signup simulated. In production, verification email would be sent.' 
        } 
      };
      
    case 'login':
      // Check localStorage for simulated user
      const users = JSON.parse(localStorage.getItem('dev_users') || '{}');
      const user = users[data.email];
      
      if (!user) {
        return { success: false, data: { message: '[DEV MODE] User not found. Sign up first.' } };
      }
      
      if (user.password !== data.password) {
        return { success: false, data: { message: '[DEV MODE] Incorrect password.' } };
      }
      
      return { 
        success: true, 
        data: { 
          success: true, 
          email_verified: true,
          user: { email: data.email, name: user.name },
          token: 'dev_token_' + Date.now()
        } 
      };
      
    case 'verify_email':
      return { 
        success: true, 
        data: { 
          success: true, 
          email: 'dev@example.com',
          name: 'Dev User',
          token: 'dev_token_' + Date.now()
        } 
      };
      
    default:
      return { success: true, data: { success: true } };
  }
}

// Save user for local dev mode
function saveDevUser(email, password, name) {
  const users = JSON.parse(localStorage.getItem('dev_users') || '{}');
  users[email] = { password, name, verified: true };
  localStorage.setItem('dev_users', JSON.stringify(users));
}

// ============================================================================
// Signup
// ============================================================================

async function signup(email, password, name) {
  showLoading('Creating account...');
  
  // Save for local dev mode
  saveDevUser(email.toLowerCase().trim(), password, name);
  
  const result = await authRequest({
    action: 'signup',
    email: email.toLowerCase().trim(),
    password,
    name
  });
  
  hideLoading();
  
  if (result.success && result.data.success !== false) {
    return {
      success: true,
      message: result.data.message || 'Verification email sent. Please check your inbox.'
    };
  }
  
  return {
    success: false,
    message: result.data?.message || result.error || 'Signup failed. Please try again.'
  };
}

// ============================================================================
// Login
// ============================================================================

async function login(email, password) {
  showLoading('Logging in...');
  
  const result = await authRequest({
    action: 'login',
    email: email.toLowerCase().trim(),
    password
  });
  
  hideLoading();
  
  if (result.success && result.data.success !== false) {
    if (result.data.email_verified === false) {
      return {
        success: false,
        needsVerification: true,
        email: email,
        message: 'Please verify your email before logging in.'
      };
    }
    
    saveSession(
      { token: result.data.token || 'session_' + Date.now() },
      { 
        email: email,
        name: result.data.name || result.data.user?.name,
        ...result.data.user
      }
    );
    
    return { success: true };
  }
  
  return {
    success: false,
    message: result.data?.message || 'Invalid email or password.'
  };
}

// ============================================================================
// Email Verification
// ============================================================================

async function verifyEmail(token) {
  showLoading('Verifying email...');
  
  const result = await authRequest({
    action: 'verify_email',
    token
  });
  
  hideLoading();
  
  if (result.success && result.data.success !== false) {
    saveSession(
      { token: result.data.token || 'session_' + Date.now() },
      { 
        email: result.data.email,
        name: result.data.name,
        ...result.data.user
      }
    );
    
    return { success: true };
  }
  
  return {
    success: false,
    expired: result.data?.expired === true,
    message: result.data?.message || 'Verification failed or link expired.'
  };
}

async function resendVerification(email) {
  showLoading('Sending verification email...');
  
  const result = await authRequest({
    action: 'resend_verification',
    email: email.toLowerCase().trim()
  });
  
  hideLoading();
  
  if (result.success) {
    return {
      success: true,
      message: 'Verification email sent. Please check your inbox.'
    };
  }
  
  return {
    success: false,
    message: result.data?.message || 'Failed to send verification email.'
  };
}

// ============================================================================
// Logout
// ============================================================================

async function logout() {
  showLoading('Logging out...');
  
  await authRequest({
    action: 'logout',
    email: getUser()?.email
  });
  
  clearSession();
  hideLoading();
  
  window.location.href = 'login.html';
}

// ============================================================================
// UI Helpers
// ============================================================================

function showLoading(message = 'Loading...') {
  let loader = document.getElementById('auth-loader');
  if (!loader) {
    loader = document.createElement('div');
    loader.id = 'auth-loader';
    loader.innerHTML = `
      <div class="loader-overlay">
        <div class="loader-content">
          <div class="loader-spinner"></div>
          <p class="loader-message">${message}</p>
        </div>
      </div>
    `;
    document.body.appendChild(loader);
  } else {
    loader.querySelector('.loader-message').textContent = message;
    loader.style.display = 'block';
  }
}

function hideLoading() {
  const loader = document.getElementById('auth-loader');
  if (loader) {
    loader.style.display = 'none';
  }
}

function showAuthMessage(message, isError = false) {
  const container = document.getElementById('auth-message');
  if (container) {
    container.textContent = message;
    container.className = `auth-message ${isError ? 'error' : 'success'}`;
    container.style.display = 'block';
  }
}

function hideAuthMessage() {
  const container = document.getElementById('auth-message');
  if (container) {
    container.style.display = 'none';
  }
}

// ============================================================================
// Form Validation
// ============================================================================

function validateEmail(email) {
  const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return re.test(email);
}

function validatePassword(password) {
  return password.length >= 6;
}

// ============================================================================
// Update UI with User Info
// ============================================================================

function updateUserDisplay() {
  const user = getUser();
  if (!user) return;
  
  const nameElements = document.querySelectorAll('.user-name');
  const emailElements = document.querySelectorAll('.user-email');
  
  nameElements.forEach(el => {
    el.textContent = user.name || user.email?.split('@')[0] || 'User';
  });
  
  emailElements.forEach(el => {
    el.textContent = user.email || '';
  });
}

// ============================================================================
// Global Exports
// ============================================================================

window.signup = signup;
window.login = login;
window.logout = logout;
window.verifyEmail = verifyEmail;
window.resendVerification = resendVerification;
window.requireAuth = requireAuth;
window.redirectIfLoggedIn = redirectIfLoggedIn;
window.isLoggedIn = isLoggedIn;
window.getUser = getUser;
window.getSession = getSession;
window.showAuthMessage = showAuthMessage;
window.hideAuthMessage = hideAuthMessage;
window.validateEmail = validateEmail;
window.validatePassword = validatePassword;
window.updateUserDisplay = updateUserDisplay;
