# MedCare AI - Final Single-Webhook Architecture

## ✅ PRODUCTION READY

**All frontend data flows through ONE webhook:**
```
https://tusarrr.app.n8n.cloud/webhook/medical-assistant
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                     │
│                                                                     │
│   AI Intake ─────┐                                                  │
│                  │                                                  │
│   Insurance ─────┼───► POST JSON ─────────────────┐                │
│                  │    Content-Type: application/json                │
│   Chatbot ───────┘                                 │                │
│                                                    │                │
│   localStorage ◄──── Dashboard reads here          │                │
└────────────────────────────────────────────────────┼────────────────┘
                                                     │
                                                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    n8n SINGLE WORKFLOW                               │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  Webhook Node: /webhook/patient-intake                       │   │
│   │  Method: POST | CORS: Enabled                                │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  IF: Has insurance_number OR insurance_image?                │   │
│   │  ├── YES → Insurance Verification Logic                      │   │
│   │  └── NO  → Skip Insurance                                    │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  AI Analysis: Generate risk_level, urgency, specialty        │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  Merge: patient + insurance + AI → ONE JSON                  │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  Firebase Admin: Save to patients/{phone_number}             │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │  Respond: { "status": "success" }                            │   │
│   │  Headers: Access-Control-Allow-Origin: *                     │   │
│   └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FIREBASE FIRESTORE                          │
│                                                                     │
│   Collection: patients                                              │
│   Document: {phone_number}                                          │
│                                                                     │
│   Fields:                                                           │
│   ├── phone_number                                                  │
│   ├── patient_name                                                  │
│   ├── age, gender, height, weight                                   │
│   ├── symptoms, pain_level                                          │
│   ├── doctor_preconsultation: { risk_level, urgency, ... }         │
│   ├── insurance: { card_number, provider, status } (if provided)   │
│   └── created_at, source                                            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 📤 Unified Payload Format

All frontend pages send this structure:

```json
{
  "action": "patient_intake | insurance_verification | chatbot",
  "patient_id": "9876543210",
  "phone_number": "9876543210",
  
  // Patient data (from AI intake)
  "patient_name": "John Doe",
  "age": 35,
  "gender": "Male",
  "height": "175 cm",
  "weight": "70 kg",
  "symptoms": "Headache for 2 days",
  "pain_level": 6,
  
  // Insurance data (optional)
  "insurance_number": "INS123456",
  "insurance_image": "base64...",
  
  // Doctor advice (generated client-side)
  "doctor_preconsultation": {
    "risk_level": "Medium",
    "urgency": "Priority",
    "recommended_specialty": "General Practice",
    "recommendations": ["..."]
  },
  
  "timestamp": "2025-12-28T..."
}
```

---

## 📁 File Structure

```
frontend/scripts/
├── config.js              # SINGLE webhookUrl
├── ai-intake-chat.js      # Uses getWebhookUrl()
├── insurance-assistant.js # Uses getWebhookUrl()
├── chatbot.js             # Uses getWebhookUrl()
├── realtime-dashboard.js  # Reads localStorage
├── health.js              # Reads localStorage
├── app.js                 # Uses getWebhookUrl()
└── system-orchestrator.js # State management
```

---

## ⚠️ n8n Workflow Requirements

### 1. Webhook Node
- Path: `patient-intake`
- Method: POST
- Response Mode: "Respond to Webhook" node

### 2. IF Node (Insurance Check)
```javascript
// Condition: Execute insurance logic if provided
{{ $json.insurance_number || $json.insurance_image }}
```

### 3. Respond to Webhook Node
**Response Body:**
```json
{
  "status": "success",
  "message": "Data saved to Firebase"
}
```

**Response Headers:**
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST, OPTIONS
Access-Control-Allow-Headers: Content-Type
```

---

## ✅ Verification Checklist

### Browser Console
- [ ] `📤 Sending data to n8n webhook...`
- [ ] `✅ Webhook success: { status: "success" }`
- [ ] No CORS errors
- [ ] No duplicate requests

### Network Tab
- [ ] ONE POST to `/webhook/patient-intake`
- [ ] Status: 200
- [ ] Content-Type: application/json

### n8n
- [ ] ONE execution per intake
- [ ] No duplicate workflows
- [ ] Firebase save successful

### Firebase
- [ ] Document exists: `patients/{phone}`
- [ ] All fields present
- [ ] Insurance data (if submitted)

---

## 🎯 Key Rules

| Rule | Status |
|------|--------|
| ONE webhook endpoint | ✅ `/webhook/patient-intake` |
| No Firebase SDK in frontend | ✅ Removed |
| No duplicate webhook calls | ✅ Single POST |
| Insurance via IF in n8n | ✅ Conditional |
| CORS headers | ⚠️ Configure in n8n |
