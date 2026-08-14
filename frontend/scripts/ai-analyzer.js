/**
 * AI Health Analyzer - JavaScript
 * Handles disease risk prediction using local ML model
 * 
 * Features:
 * - Symptom selection with checkboxes
 * - Integration with local Flask ML server
 * - Disease risk prediction with ensemble model
 * - Risk level calculation and recommendations
 */

// Available symptoms for selection
const SYMPTOMS = [
    { id: 'fever', label: 'Fever', icon: '🌡️' },
    { id: 'cough', label: 'Cough', icon: '😷' },
    { id: 'headache', label: 'Headache', icon: '🤕' },
    { id: 'fatigue', label: 'Fatigue', icon: '😴' },
    { id: 'nausea', label: 'Nausea', icon: '🤢' },
    { id: 'vomiting', label: 'Vomiting', icon: '🤮' },
    { id: 'diarrhea', label: 'Diarrhea', icon: '💩' },
    { id: 'chest_pain', label: 'Chest Pain', icon: '💔' },
    { id: 'shortness_of_breath', label: 'Shortness of Breath', icon: '😮‍💨' },
    { id: 'sore_throat', label: 'Sore Throat', icon: '🗣️' },
    { id: 'runny_nose', label: 'Runny Nose', icon: '👃' },
    { id: 'body_aches', label: 'Body Aches', icon: '💪' },
    { id: 'chills', label: 'Chills', icon: '🥶' },
    { id: 'loss_of_taste', label: 'Loss of Taste', icon: '👅' },
    { id: 'loss_of_smell', label: 'Loss of Smell', icon: '👃' },
    { id: 'dizziness', label: 'Dizziness', icon: '😵' },
    { id: 'abdominal_pain', label: 'Abdominal Pain', icon: '🫃' },
    { id: 'back_pain', label: 'Back Pain', icon: '🔙' },
    { id: 'joint_pain', label: 'Joint Pain', icon: '🦴' },
    { id: 'skin_rash', label: 'Skin Rash', icon: '🩹' }
];

// Selected symptoms
let selectedSymptoms = [];

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', () => {
    initializeAnalyzer();
});

async function initializeAnalyzer() {
    console.log('🔬 Initializing AI Health Analyzer...');
    
    // Render symptoms
    renderSymptoms();
    
    // Check model status
    await checkModelStatus();
    
    console.log('✅ AI Health Analyzer initialized');
}

/**
 * Render symptom checkboxes
 */
function renderSymptoms() {
    const grid = document.getElementById('symptoms-grid');
    if (!grid) return;
    
    grid.innerHTML = SYMPTOMS.map(symptom => `
        <label class="symptom-checkbox" data-symptom="${symptom.id}">
            <input type="checkbox" value="${symptom.id}">
            <span class="checkmark"></span>
            <span>${symptom.icon} ${symptom.label}</span>
        </label>
    `).join('');
    
    // Add click handlers
    grid.querySelectorAll('.symptom-checkbox').forEach(checkbox => {
        checkbox.addEventListener('click', (e) => {
            if (e.target.tagName !== 'INPUT') {
                const input = checkbox.querySelector('input');
                input.checked = !input.checked;
            }
            toggleSymptom(checkbox);
        });
    });
    updateSymptomCounter();
}

/**
 * Toggle symptom selection
 */
function toggleSymptom(checkbox) {
    const symptomId = checkbox.dataset.symptom;
    const input = checkbox.querySelector('input');
    
    if (input.checked) {
        checkbox.classList.add('selected');
        if (!selectedSymptoms.includes(symptomId)) {
            selectedSymptoms.push(symptomId);
        }
    } else {
        checkbox.classList.remove('selected');
        selectedSymptoms = selectedSymptoms.filter(s => s !== symptomId);
    }

    updateSymptomCounter();
    console.log('Selected symptoms:', selectedSymptoms);
}

function updateSymptomCounter() {
    const counter = document.getElementById('selected-count');
    if (!counter) return;
    counter.textContent = `${selectedSymptoms.length} selected`;
}

/**
 * Check if local ML model is available
 */
async function checkModelStatus() {
    const statusEl = document.getElementById('model-status');
    if (!statusEl) return;
    
    try {
        const healthUrl = getHealthCheckUrl();
        console.log('Checking model status at:', healthUrl);
        
        const response = await fetch(healthUrl, { method: 'GET' });
        
        if (response.ok) {
            const data = await response.json();
            statusEl.className = 'model-status online';
            statusEl.innerHTML = `
                <span class="status-dot online"></span>
                <span>🟢 ML Model Online - ${data.supported_diseases || 14} diseases supported</span>
            `;
            console.log('✅ Model is online');
        } else {
            throw new Error('Model returned error');
        }
    } catch (error) {
        console.log('⚠️ Local model unavailable:', error.message);
        statusEl.className = 'model-status offline';
        statusEl.innerHTML = `
            <span class="status-dot offline"></span>
            <span>🔴 Local Model Offline - Using fallback mode</span>
        `;
    }
}

/**
 * Analyze health based on selected symptoms
 */
async function analyzeHealth() {
    const btn = document.getElementById('analyze-btn');
    const resultsContainer = document.getElementById('results-container');
    
    // Validate inputs
    const age = parseInt(document.getElementById('patient-age')?.value) || 0;
    const gender = document.getElementById('patient-gender')?.value || '';
    
    if (selectedSymptoms.length === 0) {
        alert('Please select at least one symptom');
        return;
    }
    
    if (!age || age < 1 || age > 120) {
        alert('Please enter a valid age');
        return;
    }
    
    // Show loading
    btn.classList.add('loading');
    btn.disabled = true;
    
    try {
        // Prepare request data
        const patientInfo = {
            age: age,
            gender: gender
        };
        
        // Try local model first
        const useLocal = typeof isUsingLocalModels === 'function' && isUsingLocalModels();
        
        let predictions;
        if (useLocal) {
            predictions = await analyzeWithLocalModel(patientInfo);
        } else {
            // Fallback to simple prediction
            predictions = getFallbackPredictions(patientInfo);
        }
        
        // Display results
        displayResults(predictions, patientInfo);

        // Try to fetch a local (LIME) explanation for the same input
        // Non-blocking: explanation is optional UI enhancement.
        if (useLocal) {
            fetchAndRenderLimeExplanation(selectedSymptoms).catch(() => {});
        }
        
    } catch (error) {
        console.error('Analysis error:', error);
        
        // Try fallback
        const patientInfo = { age, gender };
        const predictions = getFallbackPredictions(patientInfo);
        displayResults(predictions, patientInfo);
    } finally {
        btn.classList.remove('loading');
        btn.disabled = false;
    }
}

/**
 * Analyze with local ML model
 */
async function analyzeWithLocalModel(patientInfo) {
    const analyzerUrl = getAnalyzerUrl();
    console.log('Sending to analyzer:', analyzerUrl);
    
    const response = await fetch(analyzerUrl, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            symptoms: selectedSymptoms,
            patient_info: patientInfo
        })
    });
    
    if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (!data.success) {
        throw new Error(data.error || 'Analysis failed');
    }
    
    return {
        predictions: data.predictions,
        risk_level: data.risk_level,
        confidence: data.model_confidence
    };
}

/**
 * Fallback prediction when local model unavailable
 */
function getFallbackPredictions(patientInfo) {
    // Simple rule-based predictions
    const predictions = [];
    
    // Count symptoms
    const hasFever = selectedSymptoms.includes('fever');
    const hasCough = selectedSymptoms.includes('cough');
    const hasHeadache = selectedSymptoms.includes('headache');
    const hasFatigue = selectedSymptoms.includes('fatigue');
    const hasNausea = selectedSymptoms.includes('nausea');
    const hasVomiting = selectedSymptoms.includes('vomiting');
    const hasDiarrhea = selectedSymptoms.includes('diarrhea');
    const hasChestPain = selectedSymptoms.includes('chest_pain');
    const hasShortnessOfBreath = selectedSymptoms.includes('shortness_of_breath');
    const hasBodyAches = selectedSymptoms.includes('body_aches');
    const hasChills = selectedSymptoms.includes('chills');
    const hasLossOfTaste = selectedSymptoms.includes('loss_of_taste');
    const hasLossOfSmell = selectedSymptoms.includes('loss_of_smell');
    const hasRunnyNose = selectedSymptoms.includes('runny_nose');
    
    // COVID-19 pattern
    if ((hasFever || hasCough) && (hasLossOfTaste || hasLossOfSmell || hasChills || hasBodyAches)) {
        predictions.push({
            disease: 'COVID-19',
            probability: 75,
            recommendation: 'Self-isolate immediately. Monitor oxygen levels. Seek emergency care for breathing difficulty.'
        });
    }
    
    // Flu pattern
    if (hasFever && (hasCough || hasBodyAches || hasChills)) {
        predictions.push({
            disease: 'Flu (Influenza)',
            probability: 65,
            recommendation: 'Rest, fluids, consider antiviral medication within 48 hours. Seek care if high fever.'
        });
    }
    
    // Common Cold
    if (hasCough && hasRunnyNose) {
        predictions.push({
            disease: 'Common Cold',
            probability: 55,
            recommendation: 'Rest at home, stay hydrated, OTC cold remedies. Consult doctor if symptoms worsen.'
        });
    }
    
    // Gastroenteritis
    if (hasNausea || hasVomiting || hasDiarrhea) {
        predictions.push({
            disease: 'Gastroenteritis',
            probability: 50,
            recommendation: 'Stay hydrated with electrolytes, bland diet. Seek care if severe dehydration.'
        });
    }
    
    // Migraine
    if (hasHeadache && (hasNausea || hasFatigue)) {
        predictions.push({
            disease: 'Migraine',
            probability: 45,
            recommendation: 'Rest in dark quiet room, OTC pain relievers. Consult neurologist for chronic cases.'
        });
    }
    
    // Hypertension warning
    if (hasChestPain || hasShortnessOfBreath) {
        predictions.push({
            disease: 'Hypertension',
            probability: 40,
            recommendation: 'Schedule doctor appointment. Monitor BP regularly, reduce salt, exercise.'
        });
    }
    
    // If no specific pattern, give general health advice
    if (predictions.length === 0) {
        predictions.push({
            disease: 'General Malaise',
            probability: 60,
            recommendation: 'Rest, stay hydrated, and monitor symptoms. Consult a doctor if they persist.'
        });
    }
    
    // Calculate risk level
    const riskLevel = calculateRiskLevel(predictions, patientInfo);
    
    return {
        predictions: predictions.slice(0, 3),
        risk_level: riskLevel,
        confidence: predictions[0]?.probability || 50,
        recognized_symptoms: selectedSymptoms,
        unrecognized_symptoms: [],
        urgency_flags: []
    };
}

/**
 * Calculate risk level based on predictions and patient info
 */
function calculateRiskLevel(predictions, patientInfo) {
    if (!predictions || predictions.length === 0) return 'Low';
    
    const topProbability = predictions[0].probability;
    const topDisease = predictions[0].disease;
    
    // High risk diseases
    const highRiskDiseases = ['COVID-19', 'Hypertension', 'Asthma'];
    
    // Age factor
    const age = patientInfo.age;
    let ageFactor = 0;
    if (age > 60) ageFactor = 15;
    else if (age > 45) ageFactor = 10;
    
    const totalRisk = Math.min(topProbability + ageFactor, 100);
    
    if (highRiskDiseases.includes(topDisease) && topProbability > 40) {
        return 'High';
    } else if (totalRisk > 50) {
        return 'Medium';
    } else {
        return 'Low';
    }
}

async function fetchAndRenderLimeExplanation(symptoms) {
    const container = document.getElementById('explainability-container');
    if (!container) return;
    container.innerHTML = `
        <div style="margin-top: 14px; padding: 14px; border-radius: 12px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">
                <h4 style="margin:0; color: rgba(255,255,255,0.85);">🧠 Why this prediction? (LIME)</h4>
                <span style="color: rgba(255,255,255,0.45); font-size:0.85rem;">Loading...</span>
            </div>
        </div>
    `;

    const resp = await fetch(getLimeLocalUrl(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symptoms, top_k_features: 8 })
    });
    if (!resp.ok) throw new Error('Explainability unavailable');
    const data = await resp.json();
    if (!data.success) throw new Error(data.error || 'Explainability failed');

    const items = (data.contributions || []).map(c => {
        const w = Number(c.weight || 0);
        const sign = w >= 0 ? '+' : '−';
        const abs = Math.abs(w).toFixed(3);
        return `
          <div style="display:flex; justify-content:space-between; gap:12px; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.06);">
            <div style="color: rgba(255,255,255,0.75); font-size: 0.9rem;">${escapeHtml(String(c.feature || ''))}</div>
            <div style="font-variant-numeric: tabular-nums; color: ${w >= 0 ? '#10b981' : '#ef4444'}; font-weight: 600;">${sign}${abs}</div>
          </div>
        `;
    }).join('');

    container.innerHTML = `
      <div style="margin-top: 14px; padding: 14px; border-radius: 12px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom: 10px;">
          <h4 style="margin:0; color: rgba(255,255,255,0.85);">🧠 Why this prediction? (LIME)</h4>
          <span style="color: rgba(255,255,255,0.45); font-size:0.85rem;">
            Class: ${escapeHtml(String(data.top_class_name || ''))} (${Math.round((Number(data.top_class_probability) || 0) * 100)}%)
          </span>
        </div>
        <div>${items || '<div style="color: rgba(255,255,255,0.55);">No explanation returned.</div>'}</div>
        <div style="margin-top: 10px; color: rgba(255,255,255,0.45); font-size: 0.82rem; line-height: 1.5;">
          LIME shows which features pushed the model toward/away from the predicted class for this specific input.
        </div>
      </div>
    `;
}

async function fetchAndRenderShapGlobal() {
    const container = document.getElementById('shap-global-container');
    if (!container) return;
    container.innerHTML = `<div style="color: rgba(255,255,255,0.55);">Loading global importance...</div>`;
    const resp = await fetch(getShapGlobalUrl() + '?top_n=12');
    const data = await resp.json();
    if (!resp.ok || !data.success) {
        container.innerHTML = `<div style="color: rgba(239,68,68,0.9);">Global SHAP unavailable: ${escapeHtml(String(data.error || resp.status))}</div>`;
        return;
    }
    const rows = (data.top_features || []).map(x => {
        const v = Number(x.importance || 0);
        const pct = Math.min(100, Math.round(v * 100));
        return `
          <div style="margin: 8px 0;">
            <div style="display:flex; justify-content:space-between; color: rgba(255,255,255,0.75); font-size:0.9rem;">
              <span>${escapeHtml(String(x.feature || ''))}</span>
              <span style="font-variant-numeric: tabular-nums; color: rgba(255,255,255,0.55);">${v.toFixed(4)}</span>
            </div>
            <div style="height: 6px; background: rgba(255,255,255,0.08); border-radius: 4px; overflow:hidden;">
              <div style="height:100%; width:${pct}%; background: linear-gradient(90deg, rgba(229,9,20,0.9), rgba(255,71,87,0.9));"></div>
            </div>
          </div>
        `;
    }).join('');
    container.innerHTML = `
      <div style="color: rgba(255,255,255,0.5); font-size:0.82rem; margin-bottom: 8px;">
        Model: ${escapeHtml(String(data.model_used || ''))} · Background: ${data.n_background}
      </div>
      ${rows || '<div style="color: rgba(255,255,255,0.55);">No data.</div>'}
    `;
}

/**
 * Display analysis results
 */
function displayResults(results, patientInfo) {
    const container = document.getElementById('results-container');
    if (!container) return;
    
    const {
        predictions,
        risk_level,
        confidence,
        recognized_symptoms = [],
        unrecognized_symptoms = [],
        urgency_flags = []
    } = results;
    
    // Risk level display
    const riskIcons = {
        'High': '⚠️',
        'Medium': '⚡',
        'Low': '✅'
    };
    
    const riskColors = {
        'High': 'high',
        'Medium': 'medium',
        'Low': 'low'
    };
    
    // Build predictions HTML
    const predictionsHtml = predictions.map((pred, index) => `
        <div class="prediction-item ${index === 0 ? 'top' : ''}">
            <div class="disease-name">${pred.disease}</div>
            <div class="probability-bar">
                <div class="probability-fill" style="width: ${pred.probability}%"></div>
            </div>
            <div class="probability-value">${pred.probability}%</div>
        </div>
    `).join('');
    
    // Get top recommendation
    const topRecommendation = predictions[0]?.recommendation || 'Consult a healthcare professional.';
    
    container.innerHTML = `
        <div class="risk-level ${riskColors[risk_level]}">
            <div class="risk-icon">${riskIcons[risk_level]}</div>
            <div class="risk-label">${risk_level} Risk</div>
            <div class="risk-confidence">Model Confidence: ${confidence}%</div>
        </div>
        
        <div class="predictions-list">
            <h4 style="color: rgba(255,255,255,0.8); margin-bottom: 12px;">Top Predictions</h4>
            ${predictionsHtml}
        </div>
        
        <div class="recommendation-box">
            <h4>💊 Recommendation</h4>
            <p>${topRecommendation}</p>
        </div>

        ${urgency_flags.length ? `
        <div class="recommendation-box" style="margin-top: 14px; background: rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.35);">
            <h4 style="color: #f59e0b;">⚠️ Urgency Signals</h4>
            <p>${urgency_flags.map(flag => flag.replaceAll('_', ' ')).join(', ')}</p>
        </div>
        ` : ''}

        <div style="margin-top: 16px; padding: 14px; background: rgba(255,255,255,0.03); border-radius: 10px;">
            <h4 style="color: rgba(255,255,255,0.85); margin-bottom: 8px;">🧩 Symptom Mapping</h4>
            <p style="color: rgba(255,255,255,0.72); font-size: 0.88rem; line-height: 1.6;">
                <strong>Recognized:</strong> ${recognized_symptoms.length ? recognized_symptoms.join(', ') : 'None'}<br>
                <strong>Unrecognized:</strong> ${unrecognized_symptoms.length ? unrecognized_symptoms.join(', ') : 'None'}
            </p>
        </div>
        
        <div style="margin-top: 20px; padding: 16px; background: rgba(0,0,0,0.2); border-radius: 12px;">
            <h4 style="color: rgba(255,255,255,0.8); margin-bottom: 12px;">Patient Info</h4>
            <p style="color: rgba(255,255,255,0.7); font-size: 0.9rem;">
                <strong>Age:</strong> ${patientInfo.age} years<br>
                <strong>Gender:</strong> ${patientInfo.gender || 'Not specified'}<br>
                <strong>Symptoms:</strong> ${selectedSymptoms.length} selected
            </p>
        </div>

        <div id="explainability-container"></div>

        <div style="margin-top: 14px; padding: 14px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 12px;">
            <div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">
                <h4 style="margin:0; color: rgba(255,255,255,0.85);">🌍 Global importance (SHAP)</h4>
                <button onclick="fetchAndRenderShapGlobal()" style="
                    background: rgba(229,9,20,0.15);
                    border: 1px solid rgba(229,9,20,0.35);
                    color: #e50914;
                    padding: 8px 12px;
                    border-radius: 10px;
                    cursor: pointer;
                    font-weight: 600;
                    font-size: 0.85rem;
                ">Load</button>
            </div>
            <div id="shap-global-container" style="margin-top: 10px; color: rgba(255,255,255,0.55); font-size: 0.9rem;">
                Click “Load” to view the most important symptoms overall for the model.
            </div>
        </div>
    `;
}

// Make functions available globally
window.analyzeHealth = analyzeHealth;
window.fetchAndRenderShapGlobal = fetchAndRenderShapGlobal;

// Safe HTML helper (reused in explanations)
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
}

