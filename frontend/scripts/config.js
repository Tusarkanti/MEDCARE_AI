/**
 * Application Configuration
 * Centralized configuration for API endpoints and app settings
 * NO FIREBASE - All data flows through ONE n8n webhook
 */

const APP_CONFIG = {
  appName: 'MedCare AI',
  version: '3.0.0',
  environment: 'production',

  // Main webhook - auth + patient intake + insurance + AI analysis
  webhookUrl: 'https://tusarrr.app.n8n.cloud/webhook/medical-assistant',

  // Chatbot webhook - separate flow for chat conversations
  chatbot: {
    webhookUrl: 'https://tusarrr.app.n8n.cloud/webhook/chat'
  },
  
  // Firebase Configuration - Get from Firebase Console > Project Settings > Your Apps
  // Go to: https://console.firebase.google.com/project/medtech-hackathon-482215/settings/general
  firebase: {
    apiKey: "YOUR_FIREBASE_API_KEY",           // Replace with your actual API key
    authDomain: "medtech-hackathon-482215.firebaseapp.com",
    projectId: "medtech-hackathon-482215",
    storageBucket: "medtech-hackathon-482215.appspot.com",
    messagingSenderId: "YOUR_SENDER_ID",       // Replace with your actual sender ID
    appId: "YOUR_APP_ID"                       // Replace with your actual app ID
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

function getWebhookUrl() {
  return APP_CONFIG.webhookUrl;
}

function isDevelopment() {
  return APP_CONFIG.environment === 'development';
}

function debugLog(...args) {
  if (isDevelopment()) {
    console.log('[MedCare AI]', ...args);
  }
}
