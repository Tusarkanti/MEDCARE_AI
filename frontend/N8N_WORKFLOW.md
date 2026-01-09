# n8n Workflow Setup for AI Patient Intake

## Overview

This document describes the n8n workflows required for the AI-powered patient intake system.

---

## 1. AI Intake Workflow

**Webhook URL:** `https://tusarrr.app.n8n.cloud/webhook/ai-intake`

### Workflow Structure

```
[Webhook] → [Set Variables] → [OpenAI/Claude] → [Extract Data] → [Save to Firebase] → [Format Response] → [Respond to Webhook]
```

### Data Flow

```
User types answer
      ↓
Frontend sends {answer, patient_id, collected_data}
      ↓
n8n AI processes message
      ↓
n8n SAVES data to Firebase ← CRITICAL STEP
      ↓
n8n returns response to Frontend
      ↓
Frontend reads from Firebase (not local memory)
      ↓
Dashboard auto-updates (Firestore listener)
```

### Webhook Node Configuration

- **HTTP Method:** POST
- **Path:** `/ai-intake`
- **Response Mode:** Last Node

### Request Payload Format

```json
{
  "action": "start_intake | process_response | complete_intake",
  "mode": "new | update",
  "userMessage": "User's natural language response",
  "currentField": "name | age | gender | height | weight | symptoms | painLevel | duration | heartRate | bloodPressure | temperature",
  "collectedData": {
    "name": "John Doe",
    "age": 35,
    "gender": "Male",
    "height": "5'10\"",
    "weight": "170 lbs",
    "symptoms": "Headache and fatigue",
    "painLevel": 6,
    "duration": "3 days",
    "heartRate": "78 BPM",
    "bloodPressure": "120/80 mmHg",
    "temperature": "98.6°F"
  },
  "conversationHistory": [
    { "role": "assistant", "content": "...", "timestamp": "..." },
    { "role": "user", "content": "...", "timestamp": "..." }
  ],
  "existingData": {},
  "sessionId": "session_xxx",
  "patientId": "PAT_xxx",
  "timestamp": "2025-12-27T..."
}
```

### AI System Prompt (for OpenAI/Claude node)

```
You are an AI-powered Patient Intake and Doctor Pre-Consultation Assistant.

You CONTROL the entire flow.
You MUST NOT stop after insurance upload.
You MUST ALWAYS continue until doctor advice is generated.

Your role is to conduct the ENTIRE patient intake using conversation only (NO forms).

You must intelligently ask questions step by step, collect health data, remember past users, and update records in real time.

========================
IDENTITY & MEMORY RULES
========================
- Each user is identified by a unique `patient_id` provided in input.
- If `returning_user = true`, previous patient data will be provided.
- You MUST remember previous data and avoid asking repeated questions.
- Ask ONLY what is missing or what may need updating.
- Never guess values. Always confirm with the user.

========================
OBJECTIVES
========================
1. Collect patient data step by step
2. Merge insurance OCR data when it arrives
3. Assess medical risk
4. Generate doctor advice
5. Always return structured JSON

========================
DATA TO COLLECT
========================

Demographics:
- name
- age
- gender
- height
- weight

Symptoms:
- main_symptom
- symptom_duration
- additional_symptoms
- pain_level (1–10)

Vitals:
- heart_rate (bpm)
- blood_pressure (systolic/diastolic)
- temperature (°C)

Insurance (from OCR or user):
- insurance_provider
- member_id
- policy_number
- expiry_date (YYYY-MM-DD)
(Insurance data may come from OCR. Do NOT re-ask if already extracted.)

========================
CRITICAL RULES
========================
- Ask ONLY ONE question at a time
- Do NOT repeat questions already answered
- Do NOT guess missing values
- If insurance data is received, CONTINUE the intake
- NEVER stop the flow without doctor advice
- ALWAYS return JSON (no text outside JSON)

========================
RISK RULES
========================
- pain_level ≥ 8 → High risk
- heart_rate > 110 → High risk
- temperature > 38.5°C (101.3°F) → Medium/High risk
- chest pain + breathing issue → Critical
- BP ≥ 180/120 → Critical

========================
COMPLETION RULES
========================
IF intake is incomplete:
- status = "collecting"
- next_question MUST be present

IF intake is complete:
- status = "completed"
- doctor_advice MUST be generated
- risk_level MUST be filled
- next_question = null

========================
RETURNING USER BEHAVIOR
========================
If previous data exists:
- Say: "Welcome back. I remember your last visit."
- Summarize key previous values briefly.
- Ask whether the user wants to update anything today.
- Store new values as a NEW visit, not overwrite history.

========================
CURRENT CONTEXT
========================
- Patient ID: {{$json.patientId}}
- Session ID: {{$json.sessionId}}
- Action: {{$json.action}}
- Mode: {{$json.mode}}
- Returning User: {{$json.existingData ? 'true' : 'false'}}
- User Message: {{$json.userMessage}}
- Previous Data: {{JSON.stringify($json.existingData || {})}}
- Current Collected Data: {{JSON.stringify($json.collectedData || {})}}
- Conversation History: {{JSON.stringify($json.conversationHistory || [])}}

========================
OUTPUT FORMAT (STRICT)
========================
Always respond in valid JSON ONLY.

Return exactly this structure:

{
  "patient_id": "{{$json.patientId}}",
  "status": "collecting | completed",
  "message": "Your conversational response to display",
  "next_question": "The specific question you're asking (or null if completed)",
  "collected_data": {
    "demographics": {
      "name": null,
      "age": null,
      "gender": null,
      "height": null,
      "weight": null
    },
    "symptoms": {
      "main_symptom": null,
      "symptom_duration": null,
      "additional_symptoms": null,
      "pain_level": null
    },
    "vitals": {
      "heart_rate": null,
      "blood_pressure": null,
      "temperature": null
    },
    "insurance": {
      "insurance_provider": null,
      "member_id": null,
      "policy_number": null,
      "expiry_date": null,
      "status": "Active | Inactive | Unknown"
    }
  },
  "risk_level": "Low | Medium | High | Critical | null",
  "doctor_advice": "Detailed advice for the patient based on symptoms (or null if not complete)",
  "alerts": [],
  "quickResponses": ["Option 1", "Option 2"],
  "isComplete": false
}

========================
SAFETY RULES
========================
- Do NOT provide diagnosis.
- If symptoms are severe or dangerous:
  - Set risk_level = high
  - Advise immediate medical attention.
- Never provide medication dosage.
- Always include a disclaimer when risk is high.

========================
FINAL BEHAVIOR
========================
- If OCR just finished → CONTINUE intake
- If all data is collected → GENERATE doctor advice
- Never stop silently
- You are NOT a chatbot
- You are a medical intake engine

========================
DOCTOR ADVICE TEMPLATE
========================
When generating doctor_advice, include:
1. Summary of symptoms and vitals
2. Possible conditions (NOT diagnosis)
3. Recommended next steps
4. Urgency level
5. Self-care suggestions if applicable

Example:
"Based on your symptoms (headache for 3 days, pain level 6/10, normal vitals), this may be a tension headache or migraine. I recommend: 1) Rest in a dark, quiet room, 2) Stay hydrated, 3) Over-the-counter pain relief if appropriate. If symptoms persist beyond 5 days or worsen significantly, please schedule an in-person consultation. This is not a diagnosis - please consult a healthcare provider for proper evaluation."

Begin the intake now based on the action and context provided.
```

---

## n8n Firebase Integration (CRITICAL)

### Add Firebase Admin Node to n8n

n8n must save patient data to Firebase **BEFORE** returning the response.

### Firebase Save Node Configuration

Use the **Firebase Admin** node or **HTTP Request** node to Firestore REST API:

**Option 1: Firebase Admin Node**
```
Collection: patients
Document ID: {{$json.patientId}}
Operation: Set (merge: true)
Data: {
  "patientId": "{{$json.patientId}}",
  "name": collected_data.demographics.name,
  "age": collected_data.demographics.age,
  "gender": collected_data.demographics.gender,
  "height": collected_data.demographics.height,
  "weight": collected_data.demographics.weight,
  "symptoms": collected_data.symptoms.main_symptom,
  "painLevel": collected_data.symptoms.pain_level,
  "duration": collected_data.symptoms.symptom_duration,
  "heartRate": collected_data.vitals.heart_rate,
  "bloodPressure": collected_data.vitals.blood_pressure,
  "temperature": collected_data.vitals.temperature,
  "insurance": collected_data.insurance,
  "riskLevel": risk_level,
  "doctorAdvice": doctor_advice,
  "status": status,
  "intakeComplete": status === "completed",
  "updatedAt": new Date().toISOString()
}
```

**Option 2: Firestore REST API (HTTP Request Node)**
```
Method: PATCH
URL: https://firestore.googleapis.com/v1/projects/YOUR_PROJECT_ID/databases/(default)/documents/patients/{{$json.patientId}}?updateMask.fieldPaths=*

Headers:
  Authorization: Bearer {{$credentials.firebaseToken}}
  Content-Type: application/json

Body: (Firestore document format)
```

### n8n Workflow Order (IMPORTANT)

```
1. [Webhook] - Receive request
2. [Set Variables] - Extract patient_id, message
3. [OpenAI/Claude] - Process with AI
4. [Function] - Parse AI response, extract data
5. [Firebase Save] - SAVE TO FIRESTORE ← Must happen BEFORE response
6. [Set Response] - Format final response
7. [Respond to Webhook] - Return to frontend
```

### Firebase Credentials in n8n

1. Go to Firebase Console → Project Settings → Service Accounts
2. Generate new private key (JSON)
3. In n8n, create Firebase Admin credentials with the JSON key
4. Use these credentials in the Firebase node

---

### Expected Response Format

```json
{
  "message": "Hello! I'm your AI health assistant. I'll guide you through a quick health assessment. Let's start with your name - what should I call you?",
  "extractedData": {},
  "nextField": "name",
  "quickResponses": [],
  "isComplete": false,
  "askInsurance": false
}
```

---

## 2. Insurance OCR Workflow

**Webhook URL:** `https://tusarrr.app.n8n.cloud/webhook/insurance-card-ocr`

### Workflow Structure

```
[Webhook] → [Read Binary] → [OpenAI Vision / OCR Service] → [Extract Fields] → [Respond to Webhook]
```

### Webhook Node Configuration

- **HTTP Method:** POST
- **Path:** `/insurance-card-ocr`
- **Response Mode:** Last Node
- **Binary Data:** Enable

### Request Format

- **Content-Type:** multipart/form-data
- **Fields:**
  - `insurance_image`: Image file (JPEG, PNG) or PDF
  - `patientId`: Patient identifier
  - `timestamp`: ISO timestamp

### OpenAI Vision Prompt

```
Analyze this insurance card image and extract the following information:

1. Insurance Provider/Company Name
2. Member ID
3. Group Number
4. Effective Date
5. Expiration Date
6. Plan Type (PPO, HMO, EPO, etc.)

Return the data as JSON:
{
  "provider": "Insurance company name",
  "memberId": "Member ID number",
  "groupNumber": "Group number",
  "effectiveDate": "MM/DD/YYYY",
  "expirationDate": "MM/DD/YYYY",
  "planType": "Plan type"
}

If a field cannot be found, use "Not found" as the value.
```

### Expected Response Format

```json
{
  "provider": "Blue Cross Blue Shield",
  "memberId": "MBR123456789",
  "groupNumber": "GRP987654",
  "effectiveDate": "01/01/2025",
  "expirationDate": "12/31/2025",
  "planType": "PPO",
  "status": "Active"
}
```

---

## 3. Chatbot Workflow

**Webhook URL:** `https://tusarrr.app.n8n.cloud/webhook/chatbot`

### Workflow Structure

```
[Webhook] → [OpenAI/Claude] → [Format Response] → [Respond to Webhook]
```

### Request Format

```json
{
  "message": "What are the symptoms of flu?",
  "sessionId": "session_xxx",
  "patientId": "PAT_xxx",
  "context": {
    "patientData": {},
    "conversationHistory": []
  },
  "timestamp": "2025-12-27T..."
}
```

### AI Prompt

```
You are a helpful medical information assistant. Answer health-related questions accurately and helpfully. 

Important guidelines:
- Provide general health information only
- Always recommend consulting a healthcare professional for specific medical advice
- If symptoms sound serious, advise seeking immediate medical attention
- Be empathetic and supportive

User's question: {{$json.message}}

Respond in a friendly, conversational manner.
```

### Response Format

```json
{
  "reply": "AI's response message",
  "suggestions": ["Related question 1", "Related question 2"]
}
```

---

## Firebase Firestore Structure

### Collection: `patients`

```
patients/
  {patientId}/
    patientId: string
    name: string
    age: number
    gender: string
    height: string
    weight: string
    symptoms: string
    painLevel: number
    duration: string
    heartRate: string
    bloodPressure: string
    temperature: string
    insurance: {
      provider: string
      memberId: string
      groupNumber: string
      effectiveDate: string
      expirationDate: string
      planType: string
      status: string
      verifiedAt: timestamp
    }
    intakeComplete: boolean
    intakeCompletedAt: timestamp
    updatedAt: timestamp
    createdAt: timestamp
    
    intakeHistory/
      {intakeId}/
        ...intakeData
        createdAt: timestamp
```

---

## Setup Checklist

1. [ ] Create n8n account and workspace
2. [ ] Create AI Intake workflow with OpenAI/Claude integration
3. [ ] Create Insurance OCR workflow with vision capabilities
4. [ ] Create Chatbot workflow
5. [ ] Enable CORS for all webhooks
6. [ ] Test all endpoints
7. [ ] Create Firebase project
8. [ ] Enable Firestore database
9. [ ] Set Firestore security rules
10. [ ] Update `firebase-config.js` with credentials
11. [ ] Update `config.js` with correct webhook URLs

---

## Firestore Security Rules

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Patients can read/write their own data
    match /patients/{patientId} {
      allow read, write: if true; // For development
      // For production, use authentication:
      // allow read, write: if request.auth != null && request.auth.uid == patientId;
      
      match /intakeHistory/{intakeId} {
        allow read, write: if true;
      }
    }
  }
}
```

---

## Testing

### Test AI Intake

```bash
curl -X POST https://tusarrr.app.n8n.cloud/webhook/ai-intake \
  -H "Content-Type: application/json" \
  -d '{
    "action": "start_intake",
    "mode": "new",
    "sessionId": "test_session",
    "patientId": "test_patient"
  }'
```

### Test Insurance OCR

```bash
curl -X POST https://tusarrr.app.n8n.cloud/webhook/insurance-card-ocr \
  -F "insurance_image=@/path/to/card.jpg" \
  -F "patientId=test_patient" \
  -F "timestamp=2025-12-27T00:00:00Z"
```
