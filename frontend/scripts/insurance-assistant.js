/**
 * Insurance Verification Assistant
 * Uses backend insurance verification API
 */

document.addEventListener('DOMContentLoaded', initializeInsuranceAssistant);

const InsuranceState = {
  currentStep: 'choose_method',
  cardNumber: null,
  ocrData: null,
  patientMobile: null,
  verifiedInsurance: null
};

let selectedFile = null;

async function initializeInsuranceAssistant() {
  setupChatInput();
  setupSendButton();
  setupFileUpload();
  setupKeyboardShortcuts();
  
  InsuranceState.patientMobile = localStorage.getItem('medcare_mobile_number');
  loadExistingInsurance();
  startVerificationFlow();
}

function loadExistingInsurance() {
  if (!InsuranceState.patientMobile) return;
  
  try {
    const patientDataStr = localStorage.getItem(`medcare_patient_${InsuranceState.patientMobile}`);
    if (patientDataStr) {
      const patientData = JSON.parse(patientDataStr);
      if (patientData.insurance?.status === 'Verified') {
        InsuranceState.verifiedInsurance = patientData.insurance;
        InsuranceState.currentStep = 'verified';
      }
    }
  } catch (error) {
    console.error('Error loading existing insurance:', error);
  }
}

function startVerificationFlow() {
  if (!InsuranceState.patientMobile) {
    addMessage('bot', `
      ⚠️ <strong>Patient ID Required</strong>
      <br><br>
      Please complete the <a href="ai-intake.html" style="color: #e50914;">AI Patient Intake</a> first to get your Patient ID.
    `, true);
    return;
  }

  if (InsuranceState.verifiedInsurance) {
    showVerifiedInsurance(InsuranceState.verifiedInsurance);
    addMessage('bot', `
      Would you like to verify a different insurance card?
      <br><br>
      <strong>Choose an option:</strong>
      <br>• Type your insurance card number below
      <br>• Click 📎 to upload your insurance card photo
    `, true);
  } else {
    addMessage('bot', `
      🏥 <strong>Insurance Verification</strong>
      <br><br>
      Patient ID: <strong>${InsuranceState.patientMobile}</strong>
      <br><br>
      You can verify your insurance using either method:
      <br><br>
      <strong>Option 1:</strong> Type your insurance card number below
      <br><strong>Option 2:</strong> Click 📎 to upload a photo of your card
    `, true);
  }
  
  InsuranceState.currentStep = 'choose_method';
}

async function processUserInput(input) {
  const trimmed = input.trim().toUpperCase();
  
  switch (InsuranceState.currentStep) {
    case 'choose_method':
    case 'waiting_for_number':
      await handleCardNumberInput(trimmed);
      break;
      
    case 'ocr_confirm':
      await handleOCRConfirmation(trimmed);
      break;
      
    case 'verified':
      if (trimmed.length >= 6) {
        await handleCardNumberInput(trimmed);
      } else {
        addMessage('bot', 'Enter a new insurance card number or upload a card photo.', true);
      }
      break;
      
    default:
      await handleCardNumberInput(trimmed);
  }
}

async function handleCardNumberInput(input) {
  const validation = validateCardNumber(input);
  
  if (!validation.valid) {
    addMessage('bot', `❌ ${validation.error}`, true);
    return;
  }
  
  InsuranceState.cardNumber = validation.value;
  await verifyInsurance(InsuranceState.cardNumber, null);
}

function validateCardNumber(input) {
  const cleaned = input.replace(/[^a-zA-Z0-9-]/g, '');
  
  if (cleaned.length < 6) {
    return { valid: false, error: 'Insurance card number must be at least 6 characters.' };
  }
  
  if (cleaned.length > 30) {
    return { valid: false, error: 'Card number too long. Please check and try again.' };
  }
  
  return { valid: true, value: cleaned.toUpperCase() };
}

/**
 * Send insurance verification data to backend API
 */
async function verifyInsurance(cardNumber, imageBase64) {
  addMessage('bot', `🔍 Verifying insurance: <strong>${cardNumber}</strong>...`, true);
  
  const payload = {
    action: 'insurance_verification',
    patient_id: InsuranceState.patientMobile,
    phone_number: InsuranceState.patientMobile,
    insurance_number: cardNumber,
    insurance_image: imageBase64 || null,
    timestamp: new Date().toISOString()
  };
  
  console.log('📤 Sending insurance verification to backend API');
  
  try {
    const response = await fetch(getInsuranceVerifyUrl(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeader()
      },
      body: JSON.stringify(payload)
    });
    
    if (response.ok) {
      const result = await response.json();
      console.log('✅ Insurance verification response:', result);
      
      if (result.insurance?.status === 'Verified' || result.status === 'success') {
        const insuranceData = result.insurance || {
          card_number: cardNumber,
          provider: result.provider || 'Verified Provider',
          status: 'Verified',
          verified_at: new Date().toISOString()
        };
        handleInsuranceVerified(insuranceData);
      } else if (result.insurance?.status === 'Not Found') {
        handleInsuranceNotFound(cardNumber);
      } else {
        handleInsuranceVerified({
          card_number: cardNumber,
          provider: result.provider || 'Insurance Provider',
          status: 'Verified',
          verified_at: new Date().toISOString()
        });
      }
    } else {
      console.error('❌ Insurance API error:', response.status);
      handleInsuranceNotFound(cardNumber);
    }
  } catch (error) {
    console.error('❌ Failed to verify insurance:', error.message);
    handleInsuranceNotFound(cardNumber);
  }
}

function handleInsuranceVerified(insurance) {
  saveInsuranceToLocalStorage(insurance);
  InsuranceState.verifiedInsurance = insurance;
  InsuranceState.currentStep = 'verified';
  showVerifiedInsurance(insurance);
  
  window.dispatchEvent(new CustomEvent('dashboard_update', { 
    detail: { patientId: InsuranceState.patientMobile, updated_sections: ['insurance'] } 
  }));
}

function saveInsuranceToLocalStorage(insurance) {
  if (!InsuranceState.patientMobile) return;
  
  try {
    const patientDataStr = localStorage.getItem(`medcare_patient_${InsuranceState.patientMobile}`);
    let patientData = patientDataStr ? JSON.parse(patientDataStr) : {};
    patientData.insurance = insurance;
    patientData.updatedAt = new Date().toISOString();
    localStorage.setItem(`medcare_patient_${InsuranceState.patientMobile}`, JSON.stringify(patientData));
    console.log('💾 Insurance saved to localStorage');
  } catch (error) {
    console.error('Error saving insurance:', error);
  }
}

function handleInsuranceNotFound(cardNumber) {
  addMessage('bot', `
    ❌ <strong>Verification Issue</strong>
    <br><br>
    Could not verify: <strong>${cardNumber}</strong>
    <br><br>
    Please try:
    <br>• Double-check the card number
    <br>• Upload a clear photo using 📎
  `, true);
  InsuranceState.currentStep = 'choose_method';
}

function showVerifiedInsurance(ins) {
  const statusColor = ins.status === 'Verified' ? '#10b981' : '#ef4444';
  const icon = ins.status === 'Verified' ? '✅' : '⚠️';
  
  addMessage('bot', `
    ${icon} <strong>Insurance ${ins.status}</strong>
    <div class="ocr-result" style="margin-top: 12px;">
      <div class="ocr-result-item">
        <span class="ocr-result-label">Card Number</span>
        <span class="ocr-result-value">${ins.card_number || 'N/A'}</span>
      </div>
      <div class="ocr-result-item">
        <span class="ocr-result-label">Provider</span>
        <span class="ocr-result-value">${ins.provider || 'N/A'}</span>
      </div>
      <div class="ocr-result-item">
        <span class="ocr-result-label">Status</span>
        <span class="ocr-result-value" style="color: ${statusColor}; font-weight: bold;">${ins.status}</span>
      </div>
    </div>
    ${ins.verified_at ? `<div style="margin-top: 8px; font-size: 0.75rem; color: rgba(255,255,255,0.4);">Verified: ${new Date(ins.verified_at).toLocaleString()}</div>` : ''}
  `, true);
}

// ============================================================================
// FILE UPLOAD & OCR
// ============================================================================

async function handleFileUpload() {
  const file = selectedFile;
  if (!file) return;
  
  addMessageWithImage('user', 'Processing insurance card...', file);
  clearSelectedFile();
  
  const typingId = showTyping();
  
  try {
    const base64 = await fileToBase64(file);
    removeTyping(typingId);
    
    addMessage('bot', `
      📋 <strong>Card Image Received</strong>
      <br><br>
      Please enter your insurance card number to complete verification:
    `, true);
    
    InsuranceState.ocrData = { imageBase64: base64 };
    InsuranceState.currentStep = 'waiting_for_number';
  } catch (error) {
    removeTyping(typingId);
    console.error('File processing error:', error);
    addMessage('bot', '❌ Error processing image. Please type your card number manually.', true);
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function handleOCRConfirmation(input) {
  if (input.length >= 6) {
    InsuranceState.cardNumber = input;
    const imageBase64 = InsuranceState.ocrData?.imageBase64 || null;
    await verifyInsurance(input, imageBase64);
  } else {
    addMessage('bot', 'Please enter your insurance card number.', true);
  }
}

// ============================================================================
// UI SETUP
// ============================================================================

function setupChatInput() {
  const input = document.getElementById('insurance-chat-input');
  if (!input) return;

  input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 100) + 'px';
  });

  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
}

function setupSendButton() {
  const btn = document.getElementById('insurance-send-button');
  if (btn) btn.addEventListener('click', sendMessage);
}

function setupFileUpload() {
  const uploadBtn = document.getElementById('upload-btn');
  const fileInput = document.getElementById('insurance-file-input');
  const removePreview = document.getElementById('remove-preview');

  if (uploadBtn && fileInput) {
    uploadBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      if (e.target.files[0]) handleFileSelect(e.target.files[0]);
    });
  }

  if (removePreview) {
    removePreview.addEventListener('click', clearSelectedFile);
  }
}

function setupKeyboardShortcuts() {
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      sendMessage();
    }
  });
}

function handleFileSelect(file) {
  const validTypes = ['image/jpeg', 'image/png', 'image/jpg'];
  if (!validTypes.includes(file.type)) {
    addMessage('bot', '❌ Please upload JPG or PNG only.', true);
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    addMessage('bot', '❌ File too large. Max 5MB.', true);
    return;
  }
  
  selectedFile = file;
  showFilePreview(file);
}

function showFilePreview(file) {
  const container = document.getElementById('image-preview-container');
  const img = document.getElementById('preview-image');
  const name = document.getElementById('preview-name');
  const size = document.getElementById('preview-size');

  if (!container) return;

  name.textContent = file.name;
  size.textContent = (file.size / 1024).toFixed(1) + ' KB';

  const reader = new FileReader();
  reader.onload = (e) => { img.src = e.target.result; };
  reader.readAsDataURL(file);

  container.style.display = 'flex';
}

function clearSelectedFile() {
  selectedFile = null;
  const container = document.getElementById('image-preview-container');
  const input = document.getElementById('insurance-file-input');
  if (container) container.style.display = 'none';
  if (input) input.value = '';
}

async function sendMessage() {
  const input = document.getElementById('insurance-chat-input');
  const btn = document.getElementById('insurance-send-button');
  
  const message = input?.value.trim() || '';
  
  if (!message && !selectedFile) return;

  if (input) input.disabled = true;
  if (btn) { btn.disabled = true; btn.textContent = 'Processing...'; }

  try {
    if (selectedFile) {
      await handleFileUpload();
    } else {
      addMessage('user', message);
      await processUserInput(message);
    }
  } finally {
    if (input) { input.disabled = false; input.value = ''; input.style.height = 'auto'; input.focus(); }
    if (btn) { btn.disabled = false; btn.textContent = 'Verify Insurance'; }
  }
}

// ============================================================================
// MESSAGE HELPERS
// ============================================================================

function addMessage(sender, content, isHtml = false) {
  const chatWindow = document.getElementById('insurance-chat-window');
  if (!chatWindow) return;

  const div = document.createElement('div');
  div.className = `chat-message ${sender}-message`;
  
  div.innerHTML = `
    <div class="message-avatar">${sender === 'user' ? '👤' : '🏥'}</div>
    <div class="message-content">
      <div class="message-text">${isHtml ? content : escapeHtml(content)}</div>
      <div class="message-time">${new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}</div>
    </div>
  `;

  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function addMessageWithImage(sender, text, file) {
  const chatWindow = document.getElementById('insurance-chat-window');
  if (!chatWindow) return;

  const div = document.createElement('div');
  div.className = `chat-message ${sender}-message`;
  
  const reader = new FileReader();
  reader.onload = (e) => {
    const img = div.querySelector('.message-image');
    if (img) img.src = e.target.result;
  };
  reader.readAsDataURL(file);

  div.innerHTML = `
    <div class="message-avatar">👤</div>
    <div class="message-content">
      <div class="message-text">${escapeHtml(text)}<img class="message-image" src="" alt="Card" style="max-width: 200px; border-radius: 10px; margin-top: 8px;"></div>
      <div class="message-time">${new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}</div>
    </div>
  `;

  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function showTyping() {
  const chatWindow = document.getElementById('insurance-chat-window');
  if (!chatWindow) return null;

  const div = document.createElement('div');
  div.className = 'chat-message bot-message typing';
  div.id = 'typing-' + Date.now();
  div.innerHTML = `
    <div class="message-avatar">🏥</div>
    <div class="message-content">
      <div class="message-text"><div class="typing-dots"><span></span><span></span><span></span></div></div>
    </div>
  `;

  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  return div.id;
}

function removeTyping(id) {
  if (id) document.getElementById(id)?.remove();
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
