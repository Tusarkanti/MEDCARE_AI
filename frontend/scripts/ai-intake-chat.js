/**
 * AI Health Intake Assistant
 * Step-by-step patient data collection with strict validation
 * Mobile number (10 digits) = UNIQUE patient ID
 * Data is saved via backend API endpoint
 */

document.addEventListener('DOMContentLoaded', initializeAIIntake);

// ============================================================================
// Intake State Management
// ============================================================================

const IntakeState = {
  REQUIRED_FIELDS: [
    'mobile_number',
    'full_name',
    'age',
    'gender',
    'height',
    'weight',
    'symptoms',
    'pain_level'
  ],

  collectedData: {},
  currentStep: 0,
  mobileNumber: null,
  sessionId: null,
  isComplete: false,
  doctorAdvice: null
};

// ============================================================================
// Field Questions
// ============================================================================

const FIELD_QUESTIONS = {
  mobile_number: "Hello! I'm your MedCare AI Health Assistant. 👋\n\nTo get started, please enter your **10-digit mobile number**:\n(This will be your unique patient ID)",
  full_name: "Thank you! Now, please enter your **full name**:",
  age: "What is your **age** in years?",
  gender: "What is your **gender**?\n(Male / Female / Other)",
  height: "What is your **height**?\n(Please include units: e.g., 170 cm or 5'10\")",
  weight: "What is your **weight**?\n(Please include units: e.g., 70 kg or 150 lbs)",
  symptoms: "Please describe your **current symptoms** in detail:\n(What are you experiencing? When did it start?)",
  pain_level: "On a scale of **0 to 10**, how would you rate your pain?\n(0 = No pain, 10 = Worst possible pain)"
};

const FIELD_QUICK_RESPONSES = {
  gender: ['Male', 'Female', 'Other'],
  pain_level: ['0 - No pain', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10 - Worst pain']
};

// ============================================================================
// Initialization
// ============================================================================

function initializeAIIntake() {
  IntakeState.sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  setupInputHandlers();
  startIntake();
}

// ============================================================================
// UI Setup
// ============================================================================

function setupInputHandlers() {
  const input = document.getElementById('ai-input');
  const sendBtn = document.getElementById('send-btn');
  
  if (!input || !sendBtn) return;
  
  input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
  });
  
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendUserMessage();
    }
  });
  
  sendBtn.addEventListener('click', sendUserMessage);
}

// ============================================================================
// Intake Flow
// ============================================================================

function startIntake() {
  IntakeState.currentStep = 0;
  IntakeState.collectedData = {};
  IntakeState.isComplete = false;
  
  clearChat();
  
  const firstField = IntakeState.REQUIRED_FIELDS[0];
  addAIMessage(FIELD_QUESTIONS[firstField], getQuickResponses(firstField));
  
  updateProgress();
  updateDataPanel();
}

function getQuickResponses(field) {
  const responses = FIELD_QUICK_RESPONSES[field];
  if (!responses) return [];
  
  return responses.map(text => ({
    text: text,
    action: () => quickResponseClick(text)
  }));
}

// ============================================================================
// Message Handling
// ============================================================================

async function sendUserMessage() {
  const input = document.getElementById('ai-input');
  const message = input.value.trim();

  if (!message) return;

  addUserMessage(message);
  input.value = '';
  input.style.height = 'auto';
  document.getElementById('quick-responses').innerHTML = '';

  showTypingIndicator();
  await processUserInput(message);
  hideTypingIndicator();
}

async function processUserInput(message) {
  const currentField = IntakeState.REQUIRED_FIELDS[IntakeState.currentStep];
  const validationResult = validateField(currentField, message);
  
  if (!validationResult.valid) {
    addAIMessage(validationResult.error, getQuickResponses(currentField));
    return;
  }

  IntakeState.collectedData[currentField] = validationResult.value;

  if (currentField === 'mobile_number') {
    IntakeState.mobileNumber = validationResult.value;
    localStorage.setItem('medcare_mobile_number', validationResult.value);
  }

  updateProgress();
  updateDataPanel();

  IntakeState.currentStep++;

  if (IntakeState.currentStep >= IntakeState.REQUIRED_FIELDS.length) {
    await completeIntake();
  } else {
    askNextQuestion();
  }
}

function askNextQuestion() {
  const nextField = IntakeState.REQUIRED_FIELDS[IntakeState.currentStep];
  addAIMessage(FIELD_QUESTIONS[nextField], getQuickResponses(nextField));
}

// ============================================================================
// Field Validation
// ============================================================================

function validateField(field, input) {
  const trimmedInput = input.trim();

  switch (field) {
    case 'mobile_number':
      const digitsOnly = trimmedInput.replace(/\D/g, '');
      if (digitsOnly.length !== 10) {
        return {
          valid: false,
          error: "Please provide a valid **10-digit mobile number** (e.g., 9876543210)."
        };
      }
      return { valid: true, value: digitsOnly };

    case 'full_name':
      if (trimmedInput.length < 2 || trimmedInput.length > 100) {
        return {
          valid: false,
          error: "Please provide your **full name** (2-100 characters)."
        };
      }
      return { valid: true, value: trimmedInput };

    case 'age':
      const age = parseInt(trimmedInput);
      if (isNaN(age) || age < 1 || age > 120) {
        return {
          valid: false,
          error: "Please provide a valid **age** between 1 and 120 years."
        };
      }
      return { valid: true, value: age };

    case 'gender':
      const lowerInput = trimmedInput.toLowerCase();
      if (lowerInput === 'm' || (lowerInput.includes('male') && !lowerInput.includes('female'))) {
        return { valid: true, value: 'Male' };
      }
      if (lowerInput === 'f' || lowerInput.includes('female')) {
        return { valid: true, value: 'Female' };
      }
      if (lowerInput === 'o' || lowerInput.includes('other')) {
        return { valid: true, value: 'Other' };
      }
      return {
        valid: false,
        error: "Please specify **Male**, **Female**, or **Other**."
      };

    case 'height':
      const heightPatterns = [
        /^\d+(?:\.\d+)?\s*(cm|centimeters?)$/i,
        /^\d+(?:\.\d+)?\s*(m|meters?)$/i,
        /^\d+'?\s*\d*"?$/,
        /^\d+(?:\.\d+)?\s*(ft|feet)(?:\s*\d+(?:\.\d+)?\s*(in|inches?)?)?$/i
      ];
      
      if (!heightPatterns.some(p => p.test(trimmedInput))) {
        return {
          valid: false,
          error: "Please provide height with units (e.g., '**170 cm**' or '**5'10\"**')."
        };
      }
      return { valid: true, value: trimmedInput };

    case 'weight':
      const weightPattern = /^\d+(?:\.\d+)?\s*(kg|kilograms?|lbs?|pounds?)?$/i;
      if (!weightPattern.test(trimmedInput)) {
        return {
          valid: false,
          error: "Please provide weight with units (e.g., '**70 kg**' or '**150 lbs**')."
        };
      }
      return { valid: true, value: trimmedInput };

    case 'symptoms':
      if (trimmedInput.length < 3) {
        return {
          valid: false,
          error: "Please describe your **symptoms** in more detail."
        };
      }
      return { valid: true, value: trimmedInput };

    case 'pain_level':
      const painMatch = trimmedInput.match(/\d+/);
      if (!painMatch) {
        return {
          valid: false,
          error: "Please provide a **pain level from 0 to 10**."
        };
      }
      const painLevel = parseInt(painMatch[0]);
      if (painLevel < 0 || painLevel > 10) {
        return {
          valid: false,
          error: "Pain level must be between **0** (no pain) and **10** (worst pain)."
        };
      }
      return { valid: true, value: painLevel };

    default:
      return { valid: true, value: trimmedInput };
  }
}

// ============================================================================
// Intake Completion
// ============================================================================

async function completeIntake() {
  IntakeState.isComplete = true;
  const mobileNumber = IntakeState.mobileNumber;
  const now = new Date().toISOString();

  console.log('🎉 Intake Completed:', {
    action: "intake_completed",
    patient_id: mobileNumber,
    status: "success"
  });

  // Generate doctor advice before API submit so it remains in payload.
  const doctorAdvice = generateDoctorAdvice();

  // Build intake payload for backend API.
  const payload = {
    phone_number: IntakeState.collectedData.mobile_number,
    patient_name: IntakeState.collectedData.full_name,
    age: IntakeState.collectedData.age,
    gender: IntakeState.collectedData.gender,
    height: IntakeState.collectedData.height,
    weight: IntakeState.collectedData.weight,
    symptoms: IntakeState.collectedData.symptoms,
    pain_level: IntakeState.collectedData.pain_level,
    doctor_preconsultation: doctorAdvice,
    visit: {
      visit_id: `VISIT_${now.slice(0, 10).replace(/-/g, '')}_${mobileNumber.slice(-3)}`,
      visit_date: now
    },
    consent: {
      given: true,
      date: now
    },
    source: "AI Intake",
    created_at: now
  };

  // Save to localStorage for dashboard continuity.
  saveToLocalStorage(payload, doctorAdvice);

  // Send to backend intake API
  await sendToBackendApi(payload);

  // Show completion message and doctor advice
  showCompletionMessage();
  showDoctorAdvice(doctorAdvice);

  updateProgress();
  updateDataPanel();
}

/**
 * Save patient data to localStorage for dashboard access
 */
function saveToLocalStorage(payload, doctorAdvice) {
  const patientId = payload.phone_number;
  
  const dashboardData = {
    name: payload.patient_name,
    full_name: payload.patient_name,
    age: payload.age,
    gender: payload.gender,
    height: payload.height,
    weight: payload.weight,
    symptoms: payload.symptoms,
    painLevel: payload.pain_level,
    intakeComplete: true,
    doctorPreConsultation: doctorAdvice,
    doctorAdvice: doctorAdvice,
    updatedAt: new Date().toISOString(),
    source: 'AI Intake'
  };

  localStorage.setItem(`medcare_patient_${patientId}`, JSON.stringify(dashboardData));
  console.log('💾 Patient data saved to localStorage for dashboard');

  // Dispatch event for dashboard to pick up
  window.dispatchEvent(new CustomEvent('dashboard_update', { 
    detail: { patientId, data: dashboardData } 
  }));
}

/**
 * Send structured intake to backend API
 */
async function sendToBackendApi(payload) {
  console.log('📤 Sending intake data to backend API...');
  
  try {
    const response = await fetch(getIntakeSubmitUrl(), {
      method: "POST",
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeader()
      },
      body: JSON.stringify(payload)
    });

    if (response.ok) {
      const result = await response.json().catch(() => ({}));
      console.log('✅ Intake API success:', result);
    } else {
      console.error('❌ Intake API error:', response.status, response.statusText);
    }
  } catch (error) {
    console.error('❌ Failed to send to intake API:', error.message);
    console.log('ℹ️ Data is still saved locally for dashboard continuity.');
  }
}

/**
 * Generate doctor pre-consultation advice based on collected data
 * Enhanced with more accurate symptom analysis and detailed recommendations
 */
function generateDoctorAdvice() {
  const data = IntakeState.collectedData;

  let riskLevel = 'Low';
  let urgency = 'Routine';
  const symptoms = (data.symptoms || '').toLowerCase();
  const painLevel = data.pain_level || 0;
  const age = parseInt(data.age) || 0;

  // Emergency symptoms requiring immediate attention
  const emergencySymptoms = [
    'chest pain', 'heart attack', 'stroke', 'difficulty breathing', 'shortness of breath',
    'severe headache', 'worst headache', 'fainting', 'unconscious', 'seizure',
    'coughing blood', 'vomiting blood', 'sudden vision loss', 'paralysis',
    'severe allergic reaction', 'anaphylaxis', 'suicidal', 'overdose'
  ];

  // High priority symptoms
  const highPrioritySymptoms = [
    'high fever', 'persistent fever', 'severe pain', 'difficulty swallowing',
    'confusion', 'disorientation', 'severe abdominal pain', 'blood in stool',
    'blood in urine', 'sudden weight loss', 'persistent vomiting', 'dehydration',
    'swelling', 'severe dizziness', 'numbness', 'tingling', 'weakness'
  ];

  // Medium priority symptoms
  const mediumPrioritySymptoms = [
    'fever', 'headache', 'migraine', 'back pain', 'joint pain', 'muscle pain',
    'nausea', 'vomiting', 'diarrhea', 'constipation', 'cough', 'cold',
    'sore throat', 'ear pain', 'dizziness', 'fatigue', 'insomnia', 'anxiety',
    'depression', 'rash', 'itching', 'burning urination'
  ];

  // Check for emergency conditions
  if (emergencySymptoms.some(s => symptoms.includes(s)) || painLevel >= 9) {
    riskLevel = 'High';
    urgency = 'Emergency';
  } else if (highPrioritySymptoms.some(s => symptoms.includes(s)) || painLevel >= 7) {
    riskLevel = 'High';
    urgency = 'Urgent - Same Day';
  } else if (mediumPrioritySymptoms.some(s => symptoms.includes(s)) || painLevel >= 5) {
    riskLevel = 'Medium';
    urgency = 'Priority - Within 48 hours';
  }

  // Age-based risk adjustment
  if (age >= 65 || age <= 5) {
    if (riskLevel === 'Low') riskLevel = 'Medium';
    if (urgency === 'Routine') urgency = 'Priority - Within 48 hours';
  }

  // Determine specialty with more accuracy
  let specialty = 'General Practice / Internal Medicine';
  let specialtyReason = '';

  if (symptoms.includes('heart') || symptoms.includes('chest') || symptoms.includes('palpitation')) {
    specialty = 'Cardiology';
    specialtyReason = 'cardiovascular symptoms';
  } else if (symptoms.includes('headache') || symptoms.includes('migraine') || symptoms.includes('seizure') || symptoms.includes('numbness') || symptoms.includes('tingling')) {
    specialty = 'Neurology';
    specialtyReason = 'neurological symptoms';
  } else if (symptoms.includes('stomach') || symptoms.includes('digestive') || symptoms.includes('abdominal') || symptoms.includes('nausea') || symptoms.includes('vomiting') || symptoms.includes('diarrhea')) {
    specialty = 'Gastroenterology';
    specialtyReason = 'digestive symptoms';
  } else if (symptoms.includes('joint') || symptoms.includes('bone') || symptoms.includes('back pain') || symptoms.includes('fracture') || symptoms.includes('sprain')) {
    specialty = 'Orthopedics';
    specialtyReason = 'musculoskeletal symptoms';
  } else if (symptoms.includes('skin') || symptoms.includes('rash') || symptoms.includes('acne') || symptoms.includes('itching')) {
    specialty = 'Dermatology';
    specialtyReason = 'skin-related symptoms';
  } else if (symptoms.includes('breathing') || symptoms.includes('cough') || symptoms.includes('asthma') || symptoms.includes('lung')) {
    specialty = 'Pulmonology';
    specialtyReason = 'respiratory symptoms';
  } else if (symptoms.includes('anxiety') || symptoms.includes('depression') || symptoms.includes('stress') || symptoms.includes('mental') || symptoms.includes('sleep')) {
    specialty = 'Psychiatry / Mental Health';
    specialtyReason = 'mental health concerns';
  } else if (symptoms.includes('eye') || symptoms.includes('vision') || symptoms.includes('blurry')) {
    specialty = 'Ophthalmology';
    specialtyReason = 'vision-related symptoms';
  } else if (symptoms.includes('ear') || symptoms.includes('hearing') || symptoms.includes('throat') || symptoms.includes('nose') || symptoms.includes('sinus')) {
    specialty = 'ENT (Otolaryngology)';
    specialtyReason = 'ear, nose, or throat symptoms';
  } else if (symptoms.includes('urination') || symptoms.includes('kidney') || symptoms.includes('bladder')) {
    specialty = 'Urology';
    specialtyReason = 'urinary symptoms';
  }

  // Build comprehensive summary
  const bmi = calculateBMI(data.height, data.weight);
  let bmiNote = '';
  if (bmi) {
    if (bmi < 18.5) bmiNote = 'BMI indicates underweight.';
    else if (bmi >= 25 && bmi < 30) bmiNote = 'BMI indicates overweight.';
    else if (bmi >= 30) bmiNote = 'BMI indicates obesity - consider discussing weight management.';
  }

  const summary = `Patient ${data.full_name || 'Unknown'}, ${data.age} years old, ${data.gender}. ` +
    `Height: ${data.height}, Weight: ${data.weight}. ${bmiNote} ` +
    `Presenting symptoms: ${data.symptoms}. Pain level: ${painLevel}/10. ` +
    (specialtyReason ? `Symptoms suggest ${specialtyReason}.` : '');

  // Generate detailed recommendations
  const recommendations = [];
  
  if (riskLevel === 'High' && urgency === 'Emergency') {
    recommendations.push('🚨 EMERGENCY: Call 911 or go to the nearest emergency room immediately.');
    recommendations.push('Do not drive yourself - have someone else drive you or call an ambulance.');
  } else if (riskLevel === 'High') {
    recommendations.push('⚠️ URGENT: Seek medical attention today. Visit urgent care or your doctor.');
    recommendations.push('If symptoms worsen, go to the emergency room immediately.');
  } else if (riskLevel === 'Medium') {
    recommendations.push('📅 Schedule an appointment with a healthcare provider within 24-48 hours.');
    recommendations.push('Monitor symptoms closely and seek urgent care if they worsen.');
  } else {
    recommendations.push('🩺 Monitor symptoms for 3-5 days. Schedule a routine appointment if they persist.');
    recommendations.push('Consider telehealth consultation for initial assessment.');
  }

  // Symptom-specific recommendations
  if (symptoms.includes('fever')) {
    recommendations.push('💧 Stay hydrated and rest. Take acetaminophen or ibuprofen for fever if appropriate.');
  }
  if (symptoms.includes('headache') || symptoms.includes('migraine')) {
    recommendations.push('🌙 Rest in a quiet, dark room. Stay hydrated and avoid screen time.');
  }
  if (symptoms.includes('cough') || symptoms.includes('cold')) {
    recommendations.push('🍵 Drink warm fluids, use honey for cough relief, and get plenty of rest.');
  }
  if (symptoms.includes('anxiety') || symptoms.includes('stress') || symptoms.includes('depression')) {
    recommendations.push('🧘 Practice relaxation techniques. Reach out to a mental health professional.');
    recommendations.push('📞 Crisis resources: National Suicide Prevention Lifeline 988, Crisis Text Line: Text HOME to 741741');
  }

  recommendations.push('📝 Keep a symptom diary noting severity, triggers, and timing for your healthcare provider.');
  recommendations.push('💊 List all current medications and supplements to share with your doctor.');

  const adviceData = {
    summary,
    risk_level: riskLevel,
    recommended_specialty: specialty,
    specialty_reason: specialtyReason,
    urgency,
    recommendations,
    bmi: bmi ? bmi.toFixed(1) : null,
    generated_at: new Date().toISOString()
  };

  console.log('👨‍⚕️ Doctor Pre-Consultation Advice Generated:', adviceData);

  IntakeState.doctorAdvice = adviceData;
  return adviceData;
}

/**
 * Calculate BMI from height and weight
 */
function calculateBMI(heightStr, weightStr) {
  if (!heightStr || !weightStr) return null;
  
  let heightInMeters = 0;
  let weightInKg = 0;
  
  // Parse height
  const cmMatch = heightStr.match(/(\d+(?:\.\d+)?)\s*(cm|centimeter)/i);
  const mMatch = heightStr.match(/(\d+(?:\.\d+)?)\s*(m|meter)/i);
  const ftInMatch = heightStr.match(/(\d+)'?\s*(\d+)?"/i);
  
  if (cmMatch) {
    heightInMeters = parseFloat(cmMatch[1]) / 100;
  } else if (mMatch) {
    heightInMeters = parseFloat(mMatch[1]);
  } else if (ftInMatch) {
    const feet = parseFloat(ftInMatch[1]);
    const inches = parseFloat(ftInMatch[2] || 0);
    heightInMeters = (feet * 12 + inches) * 0.0254;
  }
  
  // Parse weight
  const kgMatch = weightStr.match(/(\d+(?:\.\d+)?)\s*(kg|kilogram)/i);
  const lbsMatch = weightStr.match(/(\d+(?:\.\d+)?)\s*(lb|lbs|pound)/i);
  
  if (kgMatch) {
    weightInKg = parseFloat(kgMatch[1]);
  } else if (lbsMatch) {
    weightInKg = parseFloat(lbsMatch[1]) * 0.453592;
  } else {
    // Try to parse just the number and assume kg
    const numMatch = weightStr.match(/(\d+(?:\.\d+)?)/);
    if (numMatch) {
      weightInKg = parseFloat(numMatch[1]);
    }
  }
  
  if (heightInMeters > 0 && weightInKg > 0) {
    return weightInKg / (heightInMeters * heightInMeters);
  }
  
  return null;
}

function showCompletionMessage() {
  const data = IntakeState.collectedData;
  
  const jsonOutput = JSON.stringify({
    patient_id: IntakeState.mobileNumber,
    mobile_number: data.mobile_number,
    full_name: data.full_name,
    age: data.age,
    gender: data.gender,
    height: data.height,
    weight: data.weight,
    symptoms: data.symptoms,
    pain_level: data.pain_level,
    intake_completed_at: new Date().toISOString(),
    status: 'completed'
  }, null, 2);

  addAIMessage(
    `🎉 **Intake Complete!**\n\nThank you for providing your information, ${data.full_name}!\n\n**Summary:**\n\`\`\`json\n${jsonOutput}\n\`\`\`\n\nYour data has been saved. A healthcare provider will review your information.`,
    [
      { text: '📥 Download JSON', action: () => downloadJSON() },
      { text: '📊 View Dashboard', action: () => window.location.href = 'index.html' },
      { text: '🔄 Start New Intake', action: () => resetIntake() }
    ]
  );
}

function showDoctorAdvice(advice) {
  const riskColors = {
    'Low': { bg: 'rgba(16, 185, 129, 0.15)', border: '#10b981', text: '#10b981' },
    'Medium': { bg: 'rgba(245, 158, 11, 0.15)', border: '#f59e0b', text: '#f59e0b' },
    'High': { bg: 'rgba(239, 68, 68, 0.15)', border: '#ef4444', text: '#ef4444' }
  };
  
  const colors = riskColors[advice.risk_level] || riskColors['Low'];
  const chatWindow = document.getElementById('ai-chat-window');
  
  const adviceDiv = document.createElement('div');
  adviceDiv.className = 'doctor-advice-panel';
  adviceDiv.style.cssText = `
    margin: 20px 0;
    padding: 24px;
    background: linear-gradient(145deg, rgba(20, 20, 22, 0.95) 0%, rgba(25, 25, 28, 0.9) 100%);
    border: 2px solid ${colors.border};
    border-radius: 16px;
    animation: slideIn 0.4s ease;
  `;
  
  adviceDiv.innerHTML = `
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
      <span style="font-size: 2rem;">👨‍⚕️</span>
      <div>
        <h3 style="color: #ffffff; margin: 0; font-size: 1.2rem;">Doctor's Pre-Consultation Advice</h3>
        <span style="
          display: inline-block;
          padding: 4px 12px;
          background: ${colors.bg};
          border: 1px solid ${colors.border};
          border-radius: 20px;
          color: ${colors.text};
          font-size: 0.8rem;
          font-weight: 600;
          margin-top: 4px;
        ">Risk Level: ${advice.risk_level} | Urgency: ${advice.urgency}</span>
      </div>
    </div>
    <div style="
      color: rgba(255, 255, 255, 0.9);
      line-height: 1.8;
      font-size: 0.95rem;
      padding: 16px;
      background: rgba(0, 0, 0, 0.3);
      border-radius: 12px;
    ">
      <p><strong>Summary:</strong> ${advice.summary}</p>
      <p><strong>Recommended Specialty:</strong> ${advice.recommended_specialty}</p>
      <p><strong>Recommendations:</strong></p>
      <ul style="margin: 8px 0; padding-left: 20px;">
        ${advice.recommendations.map(r => `<li>${r}</li>`).join('')}
      </ul>
    </div>
    <p style="
      margin-top: 16px;
      font-size: 0.8rem;
      color: rgba(255, 255, 255, 0.5);
      text-align: center;
    ">⚠️ This is AI-generated pre-consultation advice, not a medical diagnosis.</p>
  `;
  
  chatWindow.appendChild(adviceDiv);
  scrollToBottom();
}

// ============================================================================
// UI Helpers
// ============================================================================

function addAIMessage(text, quickResponses = []) {
  const chatWindow = document.getElementById('ai-chat-window');
  if (!chatWindow) return;

  const messageDiv = document.createElement('div');
  messageDiv.className = 'ai-message bot-message';

  messageDiv.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <div class="message-text">${formatMessageText(text)}</div>
      <div class="message-time">${getCurrentTime()}</div>
    </div>
  `;

  chatWindow.appendChild(messageDiv);
  scrollToBottom();

  if (quickResponses.length > 0) {
    const quickResponsesContainer = document.getElementById('quick-responses');
    if (quickResponsesContainer) {
      quickResponsesContainer.innerHTML = quickResponses.map(qr => 
        `<button class="quick-response-btn" onclick="quickResponseClick('${qr.text.replace(/'/g, "\\'")}')">${qr.text}</button>`
      ).join('');
    }
  }
}

function addUserMessage(text) {
  const chatWindow = document.getElementById('ai-chat-window');
  if (!chatWindow) return;

  const messageDiv = document.createElement('div');
  messageDiv.className = 'ai-message user-message';

  messageDiv.innerHTML = `
    <div class="message-avatar">👤</div>
    <div class="message-content">
      <div class="message-text">${escapeHtml(text)}</div>
      <div class="message-time">${getCurrentTime()}</div>
    </div>
  `;

  chatWindow.appendChild(messageDiv);
  scrollToBottom();
}

function showTypingIndicator() {
  const chatWindow = document.getElementById('ai-chat-window');
  hideTypingIndicator();
  
  const typingDiv = document.createElement('div');
  typingDiv.id = 'typing-indicator';
  typingDiv.className = 'ai-message bot-message';
  
  typingDiv.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-content">
      <div class="typing-indicator">
        <span></span>
        <span></span>
        <span></span>
      </div>
    </div>
  `;
  
  chatWindow.appendChild(typingDiv);
  scrollToBottom();
}

function hideTypingIndicator() {
  const indicator = document.getElementById('typing-indicator');
  if (indicator) indicator.remove();
}

function clearChat() {
  const chatWindow = document.getElementById('ai-chat-window');
  if (chatWindow) chatWindow.innerHTML = '';
  
  const quickResponses = document.getElementById('quick-responses');
  if (quickResponses) quickResponses.innerHTML = '';
}

function scrollToBottom() {
  const chatWindow = document.getElementById('ai-chat-window');
  if (chatWindow) {
    setTimeout(() => {
      chatWindow.scrollTop = chatWindow.scrollHeight;
    }, 50);
  }
}

function formatMessageText(text) {
  let formatted = escapeHtml(text);
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
  formatted = formatted.replace(/\n/g, '<br>');
  formatted = formatted.replace(/```json([\s\S]*?)```/g, '<pre style="background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; overflow-x: auto; font-size: 0.85rem;">$1</pre>');
  return formatted;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function getCurrentTime() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function quickResponseClick(text) {
  const input = document.getElementById('ai-input');
  input.value = text;
  sendUserMessage();
}

// ============================================================================
// Progress & Data Panel
// ============================================================================

function updateProgress() {
  const totalFields = IntakeState.REQUIRED_FIELDS.length;
  let collectedCount = 0;
  
  IntakeState.REQUIRED_FIELDS.forEach(field => {
    if (IntakeState.collectedData[field] !== undefined && IntakeState.collectedData[field] !== null) {
      collectedCount++;
    }
  });

  const percentage = IntakeState.isComplete ? 100 : Math.round((collectedCount / totalFields) * 100);

  const progressBar = document.getElementById('progress-bar-fill');
  const progressText = document.getElementById('progress-percentage');

  if (progressBar) progressBar.style.width = percentage + '%';
  if (progressText) progressText.textContent = percentage + '%';
}

function updateDataPanel() {
  const data = IntakeState.collectedData;
  
  const fieldMap = {
    'mobile_number': 'mobile_number',
    'full_name': 'name',
    'age': 'age',
    'gender': 'gender',
    'height': 'height',
    'weight': 'weight',
    'symptoms': 'symptoms',
    'pain_level': 'painLevel'
  };

  Object.entries(fieldMap).forEach(([dataField, panelField]) => {
    const item = document.querySelector(`.data-item[data-field="${panelField}"]`);
    if (item) {
      const valueEl = item.querySelector('.data-value');
      const value = data[dataField];
      
      if (value !== undefined && value !== null) {
        const displayValue = String(value);
        valueEl.textContent = displayValue.length > 30 ? displayValue.substring(0, 27) + '...' : displayValue;
        item.classList.add('collected');
      } else {
        valueEl.textContent = '—';
        item.classList.remove('collected');
      }
    }
  });
}

// ============================================================================
// Export & Reset
// ============================================================================

function downloadJSON() {
  const data = {
    patient_id: IntakeState.mobileNumber,
    ...IntakeState.collectedData,
    doctor_advice: IntakeState.doctorAdvice,
    exported_at: new Date().toISOString()
  };

  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  
  const a = document.createElement('a');
  a.href = url;
  a.download = `patient-intake-${IntakeState.mobileNumber}-${Date.now()}.json`;
  a.click();
  
  URL.revokeObjectURL(url);
}

function resetIntake() {
  if (confirm('Are you sure you want to reset? All collected data will be cleared.')) {
    IntakeState.collectedData = {};
    IntakeState.currentStep = 0;
    IntakeState.isComplete = false;
    IntakeState.mobileNumber = null;
    IntakeState.doctorAdvice = null;
    
    clearChat();
    updateProgress();
    updateDataPanel();
    startIntake();
  }
}

function exportIntakeData() {
  downloadJSON();
}

// ============================================================================
// Global Exports
// ============================================================================

window.resetIntake = resetIntake;
window.exportIntakeData = exportIntakeData;
window.quickResponseClick = quickResponseClick;
