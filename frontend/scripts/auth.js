/**
 * Authentication System
 * Local JWT-based authentication with MongoDB backend
 * Features: Signup, Login, Session Management, Token handling
 */

const AUTH_CONFIG = {
  SESSION_KEY: 'medcare_session',
  USER_KEY: 'medcare_user',
  TOKEN_KEY: 'medcare_token'
};

// Authentication is retained for future use, but it is currently disconnected
// from the public site. Set this to true to restore the existing login gate.
const AUTH_ENABLED = false;

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

function getToken() {
  return localStorage.getItem(AUTH_CONFIG.TOKEN_KEY);
}

function saveSession(sessionData, userData, token) {
  localStorage.setItem(AUTH_CONFIG.SESSION_KEY, JSON.stringify({
    ...sessionData,
    createdAt: new Date().toISOString()
  }));
  localStorage.setItem(AUTH_CONFIG.USER_KEY, JSON.stringify(userData));
  if (token) {
    localStorage.setItem(AUTH_CONFIG.TOKEN_KEY, token);
  }
}

function clearSession() {
  localStorage.removeItem(AUTH_CONFIG.SESSION_KEY);
  localStorage.removeItem(AUTH_CONFIG.USER_KEY);
  localStorage.removeItem(AUTH_CONFIG.TOKEN_KEY);
}

function isLoggedIn() {
  const session = getSession();
  const token = getToken();
  return session !== null && token !== null;
}

// ============================================================================
// Auth Protection
// ============================================================================

function requireAuth() {
  if (!AUTH_ENABLED) {
    return true;
  }

  if (!isLoggedIn()) {
    window.location.href = 'login.html';
    return false;
  }
  return true;
}

function redirectIfLoggedIn() {
  if (!AUTH_ENABLED) {
    return false;
  }

  if (isLoggedIn()) {
    window.location.href = 'index.html';
    return true;
  }
  return false;
}

// ============================================================================
// Development Mode Handler (Fallback when backend not running)
// ============================================================================

function handleDevMode(data, method, endpoint = '') {
  const action = data?.action || method;
  
  // Dev mode users storage
  const DEV_USERS_KEY = 'medcare_dev_users';
  
  function getDevUsers() {
    try {
      return JSON.parse(localStorage.getItem(DEV_USERS_KEY) || '{}');
    } catch {
      return {};
    }
  }
  
  function saveDevUser(email, password, name) {
    const users = getDevUsers();
    const userId = 'dev_' + Date.now();
    users[email.toLowerCase()] = {
      password,
      name,
      user_id: userId,
      createdAt: new Date().toISOString()
    };
    localStorage.setItem(DEV_USERS_KEY, JSON.stringify(users));
    return userId;
  }
  
  function getDevUser(email) {
    const users = getDevUsers();
    return users[email.toLowerCase()];
  }
  
  // Handle different auth actions
  const endpointLower = String(endpoint || '').toLowerCase();
  const isRegister = endpointLower.includes('/register');
  const isLogin = endpointLower.includes('/login');

  if ((method === 'POST' || method === 'post') && isRegister) {
    // Register new user
    const email = data?.email;
    const password = data?.password;
    const name = data?.name;
    
    if (!email || !password || !name) {
      return { success: false, data: { error: 'Missing required fields' } };
    }
    
    const existing = getDevUser(email);
    if (existing) {
      return { success: false, data: { error: 'Email already registered' } };
    }
    
    const userId = saveDevUser(email, password, name);
    const token = 'dev_token_' + Date.now();
    
    return {
      success: true,
      data: {
        success: true,
        message: '[DEV MODE] Account created successfully!',
        token: token,
        user_id: userId,
        email: email,
        name: name
      }
    };
  }
  
  // Login
  if ((method === 'POST' || method === 'post') && isLogin) {
    const email = data?.email;
    const password = data?.password;
    
    if (email && password) {
      const user = getDevUser(email);
      
      if (!user) {
        return { success: false, data: { error: 'User not found. Sign up first.' } };
      }
      
      if (user.password !== password) {
        return { success: false, data: { error: 'Invalid password.' } };
      }
      
      const token = 'dev_token_' + Date.now();
      
      return {
        success: true,
        data: {
          success: true,
          token: token,
          user_id: user.user_id,
          email: email,
          name: user.name
        }
      };
    }
  }

  if (method === 'GET' || (data && !data.action)) {
    // This is a login attempt - check if we have the right data
    const email = data?.email;
    const password = data?.password;
    
    if (email && password) {
      const user = getDevUser(email);
      
      if (!user) {
        return { success: false, data: { error: 'User not found. Sign up first.' } };
      }
      
      if (user.password !== password) {
        return { success: false, data: { error: 'Invalid password.' } };
      }
      
      const token = 'dev_token_' + Date.now();
      
      return {
        success: true,
        data: {
          success: true,
          token: token,
          user_id: user.user_id,
          email: email,
          name: user.name
        }
      };
    }
  }
  
  // Default success
  return { success: true, data: { success: true, message: '[DEV MODE] Operation successful' } };
}

// ============================================================================
// API Calls with JWT
// ============================================================================

async function authApiRequest(endpoint, data = null, method = 'POST') {
  const token = getToken();
  
  // Check if we're in development mode (backend not running)
  const isLocalDev = endpoint.includes('localhost:5000');
  
  // Development mode fallback - simulate auth without backend
  if ((isLocalDev && !navigator.onLine) || endpoint.includes('localhost')) {
    // Try the request first
    try {
      const options = {
        method: method,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      };
      
      if (token) {
        options.headers['Authorization'] = `Bearer ${token}`;
      }
      
      if (data) {
        options.body = JSON.stringify(data);
      }
      
      const response = await fetch(endpoint, options);
      
      // If backend is running, use real response
      if (response.ok || response.status !== 0) {
        const text = await response.text();
        if (text && text.trim()) {
          try {
            const result = JSON.parse(text);
            return { success: response.ok, data: result };
          } catch {
            return { success: response.ok, data: { message: text } };
          }
        }
      }
    } catch (e) {
      console.log('Backend not available, using dev mode fallback');
    }
    
    // Dev mode: simulate auth using localStorage
    return handleDevMode(data, method, endpoint);
  }
  
  try {
    const options = {
      method: method,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    };
    
    // Add authorization header if token exists
    if (token) {
      options.headers['Authorization'] = `Bearer ${token}`;
    }
    
    if (data) {
      options.body = JSON.stringify(data);
    }
    
    const response = await fetch(endpoint, options);
    
    // Try to parse JSON
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
    
    if (response.ok) {
      return { success: true, data: result };
    } else {
      return { success: false, data: result, status: response.status };
    }
  } catch (error) {
    console.error('Auth request failed:', error);
    return { success: false, error: 'Network error. Please check your connection.' };
  }
}

// ============================================================================
// Signup
// ============================================================================

async function signup(email, password, name) {
  showLoading('Creating account...');
  
  const result = await authApiRequest(getRegisterUrl(), {
    email: email.toLowerCase().trim(),
    password: password,
    name: name
  });
  
  hideLoading();
  
  if (result.success && result.data.success !== false) {
    return {
      success: true,
      message: result.data.message || 'Account created. Verify your email.',
      requiresVerification: Boolean(result.data.email_verification_required),
      devVerifyUrl: result.data.dev_verify_url || null,
      emailSent: Boolean(result.data.email_sent)
    };
  }
  
  return {
    success: false,
    message: result.data?.error || result.error || 'Signup failed. Please check if the backend server is running.'
  };
}

// ============================================================================
// Login
// ============================================================================

async function login(email, password) {
  showLoading('Logging in...');
  
  const result = await authApiRequest(getLoginUrl(), {
    email: email.toLowerCase().trim(),
    password: password
  });
  
  hideLoading();
  
  if (result.success && result.data.success !== false) {
    saveSession(
      { token: result.data.token },
      { 
        email: result.data.email,
        name: result.data.name,
        user_id: result.data.user_id
      },
      result.data.token
    );
    
    return { success: true };
  }
  
  if (result.data?.needs_verification) {
    return {
      success: false,
      needsVerification: true,
      email,
      message: result.data?.error || 'Please verify your email before login.'
    };
  }

  return {
    success: false,
    message: result.data?.error || 'Invalid email or password.'
  };
}

async function verifyEmail(token) {
  const result = await authApiRequest(`${getAuthApiUrl()}/api/auth/verify-email`, { token }, 'POST');
  if (result.success && result.data.success) {
    if (result.data.token) {
      saveSession(
        { token: result.data.token },
        {
          email: result.data.email,
          name: result.data.name,
          user_id: result.data.user_id
        },
        result.data.token
      );
    }
    return { success: true };
  }
  return {
    success: false,
    expired: Boolean(result.data?.expired),
    message: result.data?.error || result.error || 'Verification failed'
  };
}

async function resendVerification(email) {
  const result = await authApiRequest(`${getAuthApiUrl()}/api/auth/resend-verification`, { email }, 'POST');
  if (result.success && result.data.success) {
    return {
      success: true,
      message: result.data.message || 'Verification email sent',
      devVerifyUrl: result.data.dev_verify_url || null
    };
  }
  return {
    success: false,
    message: result.data?.error || result.error || 'Could not resend verification email'
  };
}

// ============================================================================
// Verify Token
// ============================================================================

async function verifyToken() {
  const token = getToken();
  if (!token) {
    return { success: false, error: 'No token' };
  }
  
  const result = await authApiRequest(getVerifyUrl(), null, 'GET');
  
  if (result.success && result.data.success) {
    return { success: true, user_id: result.data.user_id, email: result.data.email };
  }
  
  // Token expired or invalid
  clearSession();
  return { success: false, error: 'Session expired' };
}

// ============================================================================
// Logout
// ============================================================================

async function logout() {
  showLoading('Logging out...');
  
  // Try to call logout endpoint (optional - won't fail if it doesn't work)
  await authApiRequest(getProfileUrl(), null, 'PUT').catch(() => {});
  
  clearSession();
  hideLoading();
  
  window.location.href = 'login.html';
}

// ============================================================================
// Get Auth Header
// ============================================================================

function getAuthHeader() {
  const token = getToken();
  return token ? { 'Authorization': `Bearer ${token}` } : {};
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
window.requireAuth = requireAuth;
window.redirectIfLoggedIn = redirectIfLoggedIn;
window.isLoggedIn = isLoggedIn;
window.getUser = getUser;
window.getSession = getSession;
window.getToken = getToken;
window.getAuthHeader = getAuthHeader;
window.showAuthMessage = showAuthMessage;
window.hideAuthMessage = hideAuthMessage;
window.validateEmail = validateEmail;
window.validatePassword = validatePassword;
window.updateUserDisplay = updateUserDisplay;
window.verifyToken = verifyToken;
window.verifyEmail = verifyEmail;
window.resendVerification = resendVerification;
