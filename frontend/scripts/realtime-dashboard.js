/**
 * Real-Time Dashboard Script
 * Features:
 * - Time-based vitals records (history tracking)
 * - Vitals history charts
 * - High value flagging and alerts
 * - Firebase sync via n8n webhook
 */

document.addEventListener('DOMContentLoaded', initializeRealtimeDashboard);

let currentPatientData = null;
let vitalsHistory = [];

function getWebhookUrl() {
  return APP_CONFIG?.webhookUrl || 'https://tusarrr.app.n8n.cloud/webhook/medical-assistant';
}

function initializeRealtimeDashboard() {
  console.log('🚀 Initializing dashboard with vitals tracking...');

  loadFromLocalStorage();

  window.addEventListener('dashboard_update', (e) => {
    console.log('📊 Dashboard update event received');
    loadFromLocalStorage();
  });

  window.addEventListener('storage', (e) => {
    if (e.key && e.key.startsWith('medcare_')) {
      console.log('📊 Storage change detected');
      loadFromLocalStorage();
    }
  });
}

function loadFromLocalStorage() {
  const patientId = localStorage.getItem('medcare_mobile_number');
  if (!patientId) {
    showNoDataState();
    return;
  }

  const patientDataStr = localStorage.getItem(`medcare_patient_${patientId}`);
  if (!patientDataStr) {
    showNoDataState();
    return;
  }

  try {
    const data = JSON.parse(patientDataStr);
    if (data && (data.name || data.full_name)) {
      currentPatientData = data;
      
      const historyStr = localStorage.getItem(`medcare_vitals_history_${patientId}`);
      if (historyStr) {
        vitalsHistory = JSON.parse(historyStr);
      } else {
        vitalsHistory = [];
      }
      
      updateDashboardWithPatientData(data);
    } else {
      showNoDataState();
    }
  } catch (error) {
    console.error('Error parsing patient data:', error);
    showNoDataState();
  }
}

function updateDashboardWithPatientData(data) {
  updatePatientInfo(data);
  updateVitals(data);
  updateSymptoms(data);
  updateInsurance(data);
  updateHealthScore(data);
  updateDoctorAdvice(data);
  renderVitalsCharts();
}

function updatePatientInfo(data) {
  const container = document.getElementById('patient-info-content');
  if (!container) return;
  
  if (!data.name && !data.full_name && !data.age) {
    container.innerHTML = `
      <div class="no-data-message">
        <div class="icon">🧠</div>
        <h4>No Intake Data Yet</h4>
        <p>Complete an AI intake to see your information here</p>
        <button class="btn-primary" style="margin-top: 16px;" onclick="window.location.href='ai-intake.html'">Start AI Intake</button>
      </div>
    `;
    return;
  }
  
  const name = data.name || data.full_name || '--';
  
  container.innerHTML = `
    <div class="patient-info-grid">
      <div class="patient-info-item">
        <div class="patient-info-label">Name</div>
        <div class="patient-info-value">${escapeHtml(name)}</div>
      </div>
      <div class="patient-info-item">
        <div class="patient-info-label">Age</div>
        <div class="patient-info-value">${data.age || '--'}</div>
      </div>
      <div class="patient-info-item">
        <div class="patient-info-label">Gender</div>
        <div class="patient-info-value">${data.gender || '--'}</div>
      </div>
      <div class="patient-info-item">
        <div class="patient-info-label">Height</div>
        <div class="patient-info-value">${data.height || '--'}</div>
      </div>
      <div class="patient-info-item">
        <div class="patient-info-label">Weight</div>
        <div class="patient-info-value">${data.weight || '--'}</div>
      </div>
      <div class="patient-info-item">
        <div class="patient-info-label">Status</div>
        <div class="patient-info-value" style="color: ${data.intakeComplete ? '#10b981' : '#f59e0b'}">
          ${data.intakeComplete ? '✓ Complete' : 'In Progress'}
        </div>
      </div>
    </div>
    ${data.updatedAt ? `<div class="last-updated">Last updated: ${formatTimestamp(data.updatedAt)}</div>` : ''}
  `;
}

function updateVitals(data) {
  const hrStatus = getHeartRateStatus(data.heartRate);
  const bpStatus = getBloodPressureStatus(data.bloodPressure);
  const tempStatus = getTemperatureStatus(data.temperature);
  
  updateVitalCard('vital-heartRate', {
    value: data.heartRate || '--',
    status: hrStatus
  });
  
  updateVitalCard('vital-bloodPressure', {
    value: data.bloodPressure || '--/--',
    status: bpStatus
  });
  
  updateVitalCard('vital-temperature', {
    value: data.temperature || '--',
    status: tempStatus
  });
  
  showVitalAlerts(hrStatus, bpStatus, tempStatus);
  
  const lastUpdate = document.getElementById('last-vitals-update');
  if (lastUpdate && data.updatedAt) {
    lastUpdate.textContent = `Last updated: ${formatTimestamp(data.updatedAt)}`;
  }
}

function updateVitalCard(id, vital) {
  const card = document.getElementById(id);
  if (!card) return;
  
  const valueEl = card.querySelector('.vital-realtime-value');
  const statusEl = card.querySelector('.vital-realtime-status');
  
  if (valueEl) {
    valueEl.textContent = vital.value;
    if (vital.status.class === 'high') {
      valueEl.style.color = '#ef4444';
    } else if (vital.status.class === 'low') {
      valueEl.style.color = '#f59e0b';
    } else {
      valueEl.style.color = '#ffffff';
    }
  }
  
  if (statusEl) {
    statusEl.textContent = vital.status.label;
    statusEl.className = `vital-realtime-status status-${vital.status.class}`;
  }
  
  if (vital.status.class === 'high') {
    card.classList.add('vital-alert');
  } else {
    card.classList.remove('vital-alert');
  }
}

function showVitalAlerts(hrStatus, bpStatus, tempStatus) {
  const alertContainer = document.getElementById('vital-alerts-container');
  if (!alertContainer) return;
  
  const alerts = [];
  
  if (hrStatus.class === 'high') {
    alerts.push({ type: 'danger', message: '⚠️ High heart rate detected! Consider resting and monitoring.' });
  } else if (hrStatus.class === 'low') {
    alerts.push({ type: 'warning', message: '⚠️ Low heart rate detected. Monitor for symptoms.' });
  }
  
  if (bpStatus.class === 'high') {
    alerts.push({ type: 'danger', message: '⚠️ High blood pressure detected! Consult a healthcare provider.' });
  } else if (bpStatus.class === 'low') {
    alerts.push({ type: 'warning', message: '⚠️ Low blood pressure detected. Stay hydrated.' });
  }
  
  if (tempStatus.class === 'high') {
    alerts.push({ type: 'danger', message: '⚠️ Fever detected! Rest and monitor your temperature.' });
  }
  
  if (alerts.length === 0) {
    alertContainer.innerHTML = '';
    return;
  }
  
  alertContainer.innerHTML = alerts.map(alert => `
    <div class="vital-alert-banner ${alert.type}">
      ${alert.message}
    </div>
  `).join('');
}

function getHeartRateStatus(value) {
  if (!value || value === '--') return { label: '--', class: 'normal' };
  const numValue = parseInt(value);
  if (isNaN(numValue)) return { label: '--', class: 'normal' };
  if (numValue > 100) return { label: 'High', class: 'high' };
  if (numValue < 60) return { label: 'Low', class: 'low' };
  return { label: 'Normal', class: 'normal' };
}

function getBloodPressureStatus(value) {
  if (!value || value === '--/--') return { label: '--', class: 'normal' };
  const match = value.match(/(\d+)\s*\/\s*(\d+)/);
  if (!match) return { label: '--', class: 'normal' };
  const systolic = parseInt(match[1]);
  if (systolic > 140) return { label: 'High', class: 'high' };
  if (systolic < 90) return { label: 'Low', class: 'low' };
  return { label: 'Normal', class: 'normal' };
}

function getTemperatureStatus(value) {
  if (!value || value === '--') return { label: '--', class: 'normal' };
  const numValue = parseFloat(value);
  if (isNaN(numValue)) return { label: '--', class: 'normal' };
  if (numValue > 90) {
    if (numValue > 100.4) return { label: 'Fever', class: 'high' };
    if (numValue < 97) return { label: 'Low', class: 'low' };
    return { label: 'Normal', class: 'normal' };
  }
  if (numValue > 38) return { label: 'Fever', class: 'high' };
  if (numValue < 36) return { label: 'Low', class: 'low' };
  return { label: 'Normal', class: 'normal' };
}

function updateSymptoms(data) {
  const container = document.getElementById('symptoms-content');
  if (!container) return;
  
  if (!data.symptoms) {
    container.innerHTML = `
      <div class="no-data-message">
        <div class="icon">💬</div>
        <h4>No Symptoms Reported</h4>
        <p>Symptoms will appear here after AI intake</p>
      </div>
    `;
    return;
  }
  
  container.innerHTML = `
    <div class="symptoms-display">
      <div class="symptoms-text">${escapeHtml(data.symptoms)}</div>
      <div class="symptoms-meta">
        ${data.painLevel !== undefined ? `
          <div class="symptoms-meta-item">
            <span>😣</span>
            <span>Pain Level: ${data.painLevel}/10</span>
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

function updateInsurance(data) {
  const providerEl = document.getElementById('insurance-provider');
  const memberIdEl = document.getElementById('insurance-member-id');
  const statusBadge = document.getElementById('insurance-status-badge');
  
  if (data.insurance) {
    const insurance = data.insurance;
    if (providerEl) providerEl.textContent = insurance.provider || 'Unknown Provider';
    if (memberIdEl) memberIdEl.textContent = insurance.memberId ? `Member ID: ${insurance.memberId}` : 'Member ID not available';
    if (statusBadge) {
      const status = insurance.status || 'Active';
      statusBadge.textContent = status;
      statusBadge.className = `insurance-status-badge ${status.toLowerCase()}`;
    }
  } else {
    if (providerEl) providerEl.textContent = 'Not Verified';
    if (memberIdEl) memberIdEl.textContent = 'Upload insurance card to verify';
    if (statusBadge) {
      statusBadge.textContent = 'Pending';
      statusBadge.className = 'insurance-status-badge pending';
    }
  }
}

function updateHealthScore(data) {
  const scoreValue = document.getElementById('health-score-value');
  const scoreTrend = document.getElementById('health-score-trend');
  const scoreMessage = document.getElementById('health-score-message');
  
  const score = calculateHealthScore(data);
  
  if (scoreValue) scoreValue.textContent = score.value;
  if (scoreTrend) {
    scoreTrend.textContent = score.trend;
    scoreTrend.style.color = score.color;
  }
  if (scoreMessage) scoreMessage.textContent = score.message;
  
  const scoreCircle = document.querySelector('.score-circle');
  if (scoreCircle && score.value !== '--') {
    scoreCircle.style.borderColor = score.color;
    scoreCircle.style.boxShadow = `0 0 30px ${score.color}40`;
  }
}

function calculateHealthScore(data) {
  if (!data.intakeComplete) {
    return {
      value: '--',
      trend: 'Pending Assessment',
      color: '#6b7280',
      message: 'Complete an AI intake to receive your personalized health score.'
    };
  }
  
  let score = 100;
  let deductions = [];
  
  if (data.painLevel !== undefined) {
    if (data.painLevel >= 7) {
      score -= 15;
      deductions.push('high pain level');
    } else if (data.painLevel >= 4) {
      score -= 8;
      deductions.push('moderate pain');
    }
  }
  
  const hrStatus = getHeartRateStatus(data.heartRate);
  if (hrStatus.class === 'high') {
    score -= 10;
    deductions.push('elevated heart rate');
  }
  
  const bpStatus = getBloodPressureStatus(data.bloodPressure);
  if (bpStatus.class === 'high') {
    score -= 12;
    deductions.push('high blood pressure');
  }
  
  const tempStatus = getTemperatureStatus(data.temperature);
  if (tempStatus.class === 'high') {
    score -= 10;
    deductions.push('fever');
  }
  
  score = Math.max(0, score);
  
  let trend, color, message;
  
  if (score >= 90) {
    trend = 'Excellent';
    color = '#10b981';
    message = 'Your health metrics look great!';
  } else if (score >= 75) {
    trend = 'Good';
    color = '#3b82f6';
    message = 'Your health is generally good with minor areas to monitor.';
  } else if (score >= 60) {
    trend = 'Fair';
    color = '#f59e0b';
    message = `Some concerns: ${deductions.join(', ')}. Consider consulting a healthcare provider.`;
  } else {
    trend = 'Needs Attention';
    color = '#ef4444';
    message = `Multiple concerns: ${deductions.join(', ')}. Please see a healthcare provider.`;
  }
  
  return { value: score, trend, color, message };
}

function updateDoctorAdvice(data) {
  const container = document.getElementById('doctor-advice-content');
  if (!container) return;
  
  const advice = data.doctorPreConsultation || data.doctorAdvice;
  
  if (!advice) {
    container.innerHTML = `
      <div class="no-data-message" style="padding: 30px;">
        <div class="icon">👨‍⚕️</div>
        <h4>No Advice Generated Yet</h4>
        <p>Complete an AI intake to receive doctor's pre-consultation advice</p>
      </div>
    `;
    return;
  }
  
  displayDoctorPreConsultation(advice);
}

function displayDoctorPreConsultation(advice) {
  const container = document.getElementById('doctor-advice-content');
  if (!container) return;
  
  const riskColors = {
    'Low': { bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.4)', text: '#10b981' },
    'Medium': { bg: 'rgba(245, 158, 11, 0.15)', border: 'rgba(245, 158, 11, 0.4)', text: '#f59e0b' },
    'High': { bg: 'rgba(239, 68, 68, 0.15)', border: 'rgba(239, 68, 68, 0.4)', text: '#ef4444' }
  };
  
  const riskLevel = advice.risk_level || 'Low';
  const urgency = advice.urgency || 'Routine';
  const specialty = advice.recommended_specialty || 'General Practice';
  const summary = advice.summary || '';
  const recommendations = advice.recommendations || [];
  const colors = riskColors[riskLevel] || riskColors['Low'];
  
  let recommendationsHtml = '';
  if (Array.isArray(recommendations) && recommendations.length > 0) {
    recommendationsHtml = `
      <div style="margin-top: 12px;">
        <strong>Recommendations:</strong>
        <ul style="margin: 8px 0; padding-left: 20px;">
          ${recommendations.map(r => `<li style="margin: 4px 0;">${escapeHtml(r)}</li>`).join('')}
        </ul>
      </div>
    `;
  }
  
  container.innerHTML = `
    <div style="margin-bottom: 16px; display: flex; gap: 12px; flex-wrap: wrap;">
      <span style="
        display: inline-block;
        padding: 6px 14px;
        background: ${colors.bg};
        border: 1px solid ${colors.border};
        border-radius: 20px;
        color: ${colors.text};
        font-size: 0.85rem;
        font-weight: 600;
      ">Risk Level: ${riskLevel}</span>
      <span style="
        display: inline-block;
        padding: 6px 14px;
        background: rgba(59, 130, 246, 0.15);
        border: 1px solid rgba(59, 130, 246, 0.4);
        border-radius: 20px;
        color: #3b82f6;
        font-size: 0.85rem;
        font-weight: 600;
      ">Urgency: ${urgency}</span>
      <span style="
        display: inline-block;
        padding: 6px 14px;
        background: rgba(139, 92, 246, 0.15);
        border: 1px solid rgba(139, 92, 246, 0.4);
        border-radius: 20px;
        color: #8b5cf6;
        font-size: 0.85rem;
        font-weight: 600;
      ">Specialty: ${specialty}</span>
    </div>
    <div style="
      color: rgba(255, 255, 255, 0.9);
      line-height: 1.7;
      font-size: 0.9rem;
      max-height: 250px;
      overflow-y: auto;
      padding: 16px;
      background: rgba(0, 0, 0, 0.2);
      border-radius: 12px;
    ">
      ${summary ? `<p style="margin-bottom: 12px;"><strong>Summary:</strong> ${escapeHtml(summary)}</p>` : ''}
      ${recommendationsHtml}
    </div>
  `;
}

function renderVitalsCharts() {
  const chartContainer = document.getElementById('vitals-chart-container');
  if (!chartContainer || vitalsHistory.length === 0) return;
  
  const last7Days = vitalsHistory.slice(-7);
  
  chartContainer.innerHTML = `
    <div class="vitals-chart-header">
      <h4>📈 Vitals History (Last 7 Records)</h4>
    </div>
    <div class="vitals-mini-charts">
      ${renderMiniChart('Heart Rate', last7Days.map(v => parseInt(v.heartRate) || 0), 'bpm', '#ef4444')}
      ${renderMiniChart('Blood Pressure', last7Days.map(v => {
        const match = (v.bloodPressure || '').match(/(\d+)/);
        return match ? parseInt(match[1]) : 0;
      }), 'systolic', '#3b82f6')}
      ${renderMiniChart('Temperature', last7Days.map(v => parseFloat(v.temperature) || 0), '°F', '#f59e0b')}
    </div>
  `;
}

function renderMiniChart(label, values, unit, color) {
  if (values.every(v => v === 0)) {
    return `
      <div class="mini-chart">
        <div class="mini-chart-label">${label}</div>
        <div class="mini-chart-no-data">No data</div>
      </div>
    `;
  }
  
  const max = Math.max(...values.filter(v => v > 0));
  const min = Math.min(...values.filter(v => v > 0));
  const range = max - min || 1;
  
  const bars = values.map((v, i) => {
    if (v === 0) return `<div class="chart-bar empty"></div>`;
    const height = ((v - min) / range) * 60 + 20;
    return `
      <div class="chart-bar" style="height: ${height}px; background: ${color};" title="${v} ${unit}"></div>
    `;
  }).join('');
  
  const latest = values[values.length - 1];
  
  return `
    <div class="mini-chart">
      <div class="mini-chart-label">${label}</div>
      <div class="mini-chart-value" style="color: ${color};">${latest || '--'} <span>${unit}</span></div>
      <div class="mini-chart-bars">${bars}</div>
    </div>
  `;
}

async function submitVitals() {
  const heartRate = document.getElementById('input-heartRate')?.value;
  const bloodPressure = document.getElementById('input-bloodPressure')?.value;
  const temperature = document.getElementById('input-temperature')?.value;
  
  if (!heartRate && !bloodPressure && !temperature) {
    alert('Please enter at least one vital sign');
    return;
  }
  
  const patientId = localStorage.getItem('medcare_mobile_number');
  if (!patientId) {
    alert('Please complete patient intake first');
    return;
  }
  
  const timestamp = new Date().toISOString();
  const vitalRecord = {
    timestamp,
    heartRate: heartRate || null,
    bloodPressure: bloodPressure || null,
    temperature: temperature || null
  };
  
  vitalsHistory.push(vitalRecord);
  localStorage.setItem(`medcare_vitals_history_${patientId}`, JSON.stringify(vitalsHistory));
  
  const patientData = JSON.parse(localStorage.getItem(`medcare_patient_${patientId}`) || '{}');
  if (heartRate) patientData.heartRate = heartRate;
  if (bloodPressure) patientData.bloodPressure = bloodPressure;
  if (temperature) patientData.temperature = temperature;
  patientData.updatedAt = timestamp;
  localStorage.setItem(`medcare_patient_${patientId}`, JSON.stringify(patientData));
  
  try {
    await fetch(getWebhookUrl(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'submit_vitals',
        phone_number: patientId,
        vital_record: vitalRecord,
        latest_vitals: {
          heartRate: heartRate || patientData.heartRate,
          bloodPressure: bloodPressure || patientData.bloodPressure,
          temperature: temperature || patientData.temperature
        },
        timestamp
      })
    });
    console.log('✅ Vitals synced to webhook');
  } catch (error) {
    console.log('Vitals saved locally, sync pending');
  }
  
  currentPatientData = patientData;
  updateDashboardWithPatientData(patientData);
  
  document.getElementById('input-heartRate').value = '';
  document.getElementById('input-bloodPressure').value = '';
  document.getElementById('input-temperature').value = '';
  
  showSuccessMessage('Vitals recorded successfully!');
}

function showSuccessMessage(message) {
  const toast = document.createElement('div');
  toast.className = 'success-toast';
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
    padding: 12px 24px;
    border-radius: 10px;
    font-weight: 500;
    z-index: 1000;
    animation: slideInUp 0.3s ease;
  `;
  document.body.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'slideOutDown 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function showNoDataState() {
  const patientInfo = document.getElementById('patient-info-content');
  if (patientInfo) {
    patientInfo.innerHTML = `
      <div class="no-data-message">
        <div class="icon">🧠</div>
        <h4>No Intake Data Yet</h4>
        <p>Complete an AI intake to see your information here</p>
        <button class="btn-primary" style="margin-top: 16px;" onclick="window.location.href='ai-intake.html'">Start AI Intake</button>
      </div>
    `;
  }
}

function formatTimestamp(timestamp) {
  if (!timestamp) return '--';
  
  let date;
  if (timestamp instanceof Date) {
    date = timestamp;
  } else {
    date = new Date(timestamp);
  }
  
  if (isNaN(date.getTime())) return '--';
  
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)} hours ago`;
  
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

window.submitVitals = submitVitals;
