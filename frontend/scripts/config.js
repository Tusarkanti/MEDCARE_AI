/**
 * Application Configuration
 * Centralized configuration for API endpoints and app settings
 * 
 * Backend-only architecture:
 * - Local backend APIs (localhost)
 * - MongoDB for data storage (admin panel)
 * - Local authentication (JWT)
 */

const APP_CONFIG = {
  appName: 'MedCare AI',
  version: '4.0.0',
  environment: 'production',

  // ==================== LOCAL ML SERVER ====================
  // Toggle local backend model services
  useLocalModels: true,

  localServer: {
    baseUrl: 'http://localhost:5000',
    chatbotEndpoint: '/api/chatbot',
    analyzeEndpoint: '/api/analyze',
    healthEndpoint: '/api/analyze/health',
    vitalSignsEndpoint: '/api/vital-signs/analyze',
    explainabilityHealthEndpoint: '/api/explainability/health',
    shapGlobalEndpoint: '/api/explainability/shap-global',
    limeLocalEndpoint: '/api/explainability/lime-local'
  },

  intakeApi: {
    baseUrl: 'http://localhost:5000',
    submitEndpoint: '/api/intake/submit'
  },
  insuranceApi: {
    baseUrl: 'http://localhost:5000',
    verifyEndpoint: '/api/insurance/verify'
  },
  
  // ==================== MONGODB API (Data Storage) ====================
  // Admin API endpoints for MongoDB database
  // Use this for the admin dashboard to view all patient data
  adminApi: {
    baseUrl: 'http://localhost:5000',
    patientsEndpoint: '/api/admin/patients',
    statsEndpoint: '/api/admin/stats',
    healthEndpoint: '/api/admin/health',
    migrateEndpoint: '/api/admin/migrate-from-localstorage'
  },
  
  // ==================== AUTH API (Local) ====================
  // Local authentication endpoints
  authApi: {
    baseUrl: 'http://localhost:5000',
    registerEndpoint: '/api/auth/register',
    loginEndpoint: '/api/auth/login',
    verifyEndpoint: '/api/auth/verify',
    profileEndpoint: '/api/auth/profile'
  },
  
  // ==================== USER DATA API (Multi-User) ====================
  userApi: {
    baseUrl: 'http://localhost:5000',
    patientsEndpoint: '/api/user/patients',
    vitalsEndpoint: '/api/user/vitals',
    statsEndpoint: '/api/user/stats'
  },
  
  // ==================== FIREBASE (Hosting Only - No Firestore) ====================
  // Firebase is used only for hosting/deployment
  // All data is now stored in MongoDB
  firebase: {
    apiKey: "YOUR_FIREBASE_API_KEY",
    authDomain: "medtech-hackathon-482215.firebaseapp.com",
    projectId: "medtech-hackathon-482215",
    storageBucket: "medtech-hackathon-482215.appspot.com",
    messagingSenderId: "YOUR_SENDER_ID",
    appId: "YOUR_APP_ID"
  },
  
  // Intake Configuration
  intake: {
    requiredFields: [
      'mobile_number',
      'full_name',
      'age', 
      'gender',
      'height',
      'weight',
      'symptoms',
      'pain_level'
    ]
  },
  
  // UI Configuration
  ui: {
    animationDuration: 300,
    typingDelay: 1500,
    autoScrollDelay: 50
  }
};

// ==================== HELPER FUNCTIONS ====================

/**
 * API base URL (override: localStorage medcare_api_base_url = e.g. http://127.0.0.1:5000)
 */
function getApiBaseUrl() {
  try {
    const override = localStorage.getItem('medcare_api_base_url');
    if (override && /^https?:\/\//i.test(override)) {
      return override.replace(/\/$/, '');
    }
  } catch (e) { /* ignore */ }
  return APP_CONFIG.localServer.baseUrl;
}

function getChatbotUrl() {
  return getApiBaseUrl() + APP_CONFIG.localServer.chatbotEndpoint;
}

/**
 * Get the appropriate analyzer URL based on configuration
 */
function getAnalyzerUrl() {
  return APP_CONFIG.localServer.baseUrl + APP_CONFIG.localServer.analyzeEndpoint;
}

/**
 * Get the appropriate health check URL
 */
function getHealthCheckUrl() {
  return getApiBaseUrl() + APP_CONFIG.localServer.healthEndpoint;
}

/**
 * Get vital signs analysis URL
 */
function getVitalSignsUrl() {
  return getApiBaseUrl() + APP_CONFIG.localServer.vitalSignsEndpoint;
}

function getExplainabilityHealthUrl() {
  return getApiBaseUrl() + APP_CONFIG.localServer.explainabilityHealthEndpoint;
}

function getShapGlobalUrl() {
  return getApiBaseUrl() + APP_CONFIG.localServer.shapGlobalEndpoint;
}

function getLimeLocalUrl() {
  return getApiBaseUrl() + APP_CONFIG.localServer.limeLocalEndpoint;
}

/**
 * Get intake submit endpoint
 */
function getIntakeSubmitUrl() {
  return getApiBaseUrl() + APP_CONFIG.intakeApi.submitEndpoint;
}

/**
 * Get insurance verification endpoint
 */
function getInsuranceVerifyUrl() {
  return getApiBaseUrl() + APP_CONFIG.insuranceApi.verifyEndpoint;
}

/**
 * Get admin API base URL (MongoDB)
 */
function getAdminApiUrl() {
  return APP_CONFIG.adminApi.baseUrl;
}

/**
 * Get all patients endpoint
 */
function getAdminPatientsUrl() {
  return getApiBaseUrl() + APP_CONFIG.adminApi.patientsEndpoint;
}

/**
 * Get admin stats endpoint
 */
function getAdminStatsUrl() {
  return getApiBaseUrl() + APP_CONFIG.adminApi.statsEndpoint;
}

/**
 * Get auth API base URL
 */
function getAuthApiUrl() {
  return getApiBaseUrl();
}

/**
 * Get register endpoint
 */
function getRegisterUrl() {
  return getApiBaseUrl() + APP_CONFIG.authApi.registerEndpoint;
}

/**
 * Get login endpoint
 */
function getLoginUrl() {
  return getApiBaseUrl() + APP_CONFIG.authApi.loginEndpoint;
}

/**
 * Get verify endpoint
 */
function getVerifyUrl() {
  return getApiBaseUrl() + APP_CONFIG.authApi.verifyEndpoint;
}

/**
 * Get profile endpoint
 */
function getProfileUrl() {
  return getApiBaseUrl() + APP_CONFIG.authApi.profileEndpoint;
}

/**
 * Get user patients endpoint
 */
function getUserPatientsUrl() {
  return getApiBaseUrl() + APP_CONFIG.userApi.patientsEndpoint;
}

/**
 * Get user vitals endpoint
 */
function getUserVitalsUrl() {
  return getApiBaseUrl() + APP_CONFIG.userApi.vitalsEndpoint;
}

/**
 * Get user stats endpoint
 */
function getUserStatsUrl() {
  return getApiBaseUrl() + APP_CONFIG.userApi.statsEndpoint;
}

/**
 * Check if local models are enabled
 */
function isUsingLocalModels() {
  return APP_CONFIG.useLocalModels;
}

function isDevelopment() {
  return APP_CONFIG.environment === 'development';
}

function debugLog(...args) {
  if (isDevelopment()) {
    console.log('[MedCare AI]', ...args);
  }
}
