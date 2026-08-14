"""
MedCare AI - Local ML Backend Server
=====================================
This Flask API serves:
1. AI Chatbot - LLM-powered (ChatGPT-like) for health-related queries
2. AI Analyzer - Disease Risk Prediction using ensemble learning
3. Admin API - MongoDB database for patient data storage
4. User Authentication - Registration, Login, JWT tokens

Run: python backend/app.py
"""

from flask import Flask, request, jsonify, g
from flask_cors import CORS
import numpy as np
import pandas as pd
import pickle
import os
import warnings
import random
import sys
from datetime import datetime, timedelta
from functools import wraps
warnings.filterwarnings('ignore')

try:
    # Avoid Windows cp1252 crashes when logging emoji/unicode text.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Import ML libraries
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import re

# Import MongoDB
from pymongo import MongoClient
from bson import ObjectId
import json

# Import Authentication
import bcrypt
import jwt
import smtplib
import secrets
from email.message import EmailMessage

# Import new ML services (production inference)
try:
    from ml.inference import init_inference, get_inference
    from services.prediction_service import PredictionService
    from services.intake_nlp_service import IntakeNLPService
    from ml.explainability import ExplainabilityService
    from ml.unified_training_data import normalize_symptom_token
    ML_SERVICES_AVAILABLE = True
except Exception as e:
    print(f"⚠️  ML services import warning: {e}")
    ML_SERVICES_AVAILABLE = False

    def normalize_symptom_token(s):
        t = str(s or "").strip().lower().replace(" ", "_")
        return t

# Production-style modules (Mongo + v2 routes)
try:
    from db.mongo import init_indexes as init_mongo_indexes
    from routes.auth_routes import auth_bp
    from routes.chat_routes import chat_bp
    PROD_MODULES_AVAILABLE = True
except Exception as e:
    print(f"⚠️  Production modules import warning: {e}")
    PROD_MODULES_AVAILABLE = False

app = Flask(__name__)
CORS(app)

# ==================== CONFIGURATION ====================
PORT = 5000
MODEL_DIR = os.path.join(os.path.dirname(__file__), '..', 'models')
os.makedirs(MODEL_DIR, exist_ok=True)

# Explainability config
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
DISEASE_SYMPTOMS_CSV = os.path.join(DATA_DIR, 'disease_symptoms.csv')


def get_explainability_csv_path():
    """Prefer unified multi-CSV background sample (created by train_ensemble_models.py)."""
    unified = os.path.join(DATA_DIR, 'unified_training_background.csv')
    if os.path.exists(unified):
        return unified
    return DISEASE_SYMPTOMS_CSV


_explainability_service = None

def get_explainability_service():
    """Lazy init explainability service (SHAP/LIME) over production inference engine."""
    global _explainability_service
    if not ML_SERVICES_AVAILABLE:
        return None
    if _explainability_service is None:
        _explainability_service = ExplainabilityService(get_inference())
    return _explainability_service

# MongoDB Configuration - Update with your connection string
# For local MongoDB: mongodb://localhost:27017
# For MongoDB Atlas: mongodb+srv://<username>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'medcare_ai')

# MongoDB Connection
mongo_client = None
db = None

def init_mongodb():
    """Initialize MongoDB connection"""
    global mongo_client, db
    try:
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client[MONGO_DB_NAME]
        
        # Test connection
        mongo_client.admin.command('ping')
        print("✅ MongoDB connected successfully")
        
        # Create indexes
        db.patients.create_index([('mobile_number', 1)], unique=True)
        db.patients.create_index([('createdAt', -1)])
        
        return True
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("ℹ️ Make sure MongoDB is running or check your connection string")
        return False

# Initialize MongoDB
mongo_connected = init_mongodb()
try:
    if mongo_connected and PROD_MODULES_AVAILABLE:
        init_mongo_indexes()
except Exception as e:
    print(f"⚠️  Mongo index init warning: {e}")

# JWT Configuration
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'medcare-ai-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24
APP_BASE_URL = os.environ.get('APP_BASE_URL', 'http://localhost:5000')
FRONTEND_BASE_URL = os.environ.get('FRONTEND_BASE_URL', 'http://localhost:5500/frontend')

# Email configuration
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMTP_FROM_EMAIL = os.environ.get('SMTP_FROM_EMAIL', SMTP_USER)
SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', 'true').lower() == 'true'

# OpenAI Configuration - Add your API key here
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')  # Set via environment variable
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-3.5-turbo')

# ==================== GLOBAL VARIABLES ====================
# Chatbot components
chatbot_model = None
chatbot_vectorizer = None
intents = None
conversation_history = {}  # Store conversation per session
EMERGENCY_KEYWORDS = [
    "chest pain", "severe chest pain", "shortness of breath", "not breathing",
    "unconscious", "fainted", "stroke", "heart attack", "seizure",
    "heavy bleeding", "suicidal", "self harm", "overdose"
]

# Disease Prediction components
disease_model = None
symptom_encoder = None
scaler = None
disease_labels = None

# ==================== INITIALIZATION ====================
def initialize_chatbot():
    """Initialize the AI Chatbot with medical knowledge base"""
    global chatbot_model, chatbot_vectorizer, intents
    
    print("🤖 Initializing AI Chatbot...")
    
    # Medical intents dataset
    intents = {
        "greetings": {
            "patterns": ["hello", "hi", "hey", "good morning", "good evening", "namaste", "hi there", "hello there", "howdy", "greetings"],
            "responses": [
                "Hello! Welcome to MedCare AI. How can I assist you today?",
                "Hi there! I'm your AI health assistant. What can I help you with?",
                "Namaste! How may I help you with your health today?",
                "Hey! Great to see you. What would you like to know about today?"
            ]
        },
        "symptoms": {
            "patterns": ["i feel", "i have", "my symptoms are", "i'm experiencing", "feeling", "suffering from", "not feeling well", "feeling sick"],
            "responses": [
                "I understand you're experiencing some symptoms. Could you please describe them in more detail?",
                "Thank you for sharing. How long have you been experiencing these symptoms?",
                "I see. On a scale of 1-10, how would you rate the severity?",
                "I appreciate you telling me. Can you describe exactly what you're feeling?"
            ]
        },
        "fever": {
            "patterns": ["fever", "high temperature", "febrile", "feeling hot", "chills", "high fever"],
            "responses": [
                "Fever can be a sign of various conditions. How high is your temperature? Do you also have chills, body aches, or other symptoms?",
                "For fever, I recommend: 1) Stay hydrated 2) Take acetaminophen 3) Rest 4) Monitor temperature. Seek medical attention if above 103°F or persisting over 3 days."
            ]
        },
        "headache": {
            "patterns": ["headache", "head pain", "migraine", "head ache", "head hurts", "head pains"],
            "responses": [
                "Headaches can have many causes. Where is the pain located? Is it throbbing, sharp, or dull? Any sensitivity to light or sound?",
                "For mild headache: Rest in a quiet room, stay hydrated, and consider over-the-counter pain relievers. See a doctor if severe or accompanied by vision changes."
            ]
        },
        "cough": {
            "patterns": ["cough", "coughing", "cold", "flu", "sore throat", "runny nose", "congestion"],
            "responses": [
                "Cough can be dry or wet. Is there any phlegm or mucus? How long have you had this?",
                "For cough: Stay hydrated, use humidifier, honey can help (not for children under 1). Seek medical help if breathing difficulty or blood in cough."
            ]
        },
        "stomach": {
            "patterns": ["stomach", "abdomen", "nausea", "vomiting", "diarrhea", "constipation", "digestion", "belly", "abdominal"],
            "responses": [
                "Stomach issues can be caused by many factors. Are you experiencing pain? When did it start?",
                "For stomach problems: Eat bland foods, stay hydrated, avoid dairy initially. See a doctor if severe pain, blood in stool, or symptoms persisting over 2 days."
            ]
        },
        "chest_pain": {
            "patterns": ["chest pain", "heart pain", "chest tightness", "pressure in chest", "heartburn", "heart ache"],
            "responses": [
                "⚠️ Chest pain can be serious. If you're experiencing severe chest pain, shortness of breath, or pain radiating to arm/jaw, please call emergency services immediately!",
                "For chest discomfort: Rest and avoid exertion. If mild, it could be heartburn or muscle strain. Please consult a doctor for proper diagnosis."
            ]
        },
        "emergency": {
            "patterns": ["emergency", "ambulance", "critical", "severe", "life threatening", "bleeding", "unconscious", "not breathing"],
            "responses": [
                "⚠️ If this is a medical emergency, please call your local emergency number immediately!",
                "For immediate emergencies: 1) Call emergency services 2) Don't move the person 3) Apply pressure to bleeding 4) Begin CPR if needed"
            ]
        },
        "medication": {
            "patterns": ["medicine", "medication", "drugs", "tablets", "capsules", "dosage", "prescription", "pills"],
            "responses": [
                "I cannot prescribe medication, but I can provide general information. Always consult a doctor before taking any medication.",
                "For medication queries: Please consult your healthcare provider or pharmacist. They can provide proper guidance based on your medical history."
            ]
        },
        "appointment": {
            "patterns": ["appointment", "doctor", "specialist", "hospital", "clinic", "consultation", "see a doctor"],
            "responses": [
                "I can help you with general guidance. For appointments, please use our AI Intake system or contact your healthcare provider.",
                "Would you like me to guide you through our AI Health Assessment to determine what type of specialist you might need?"
            ]
        },
        "general_health": {
            "patterns": ["healthy", "wellness", "diet", "exercise", "nutrition", "sleep", "stress", "health", "wellbeing"],
            "responses": [
                "Great question about wellness! A balanced diet, regular exercise (150 min/week), 7-8 hours sleep, and stress management are key to good health.",
                "For overall wellness: 1) Eat colorful fruits & vegetables 2) Exercise regularly 3) Stay hydrated 4) Manage stress 5) Regular health checkups"
            ]
        },
        "covid": {
            "patterns": ["covid", "coronavirus", "covid-19", "pandemic", "virus", "corona"],
            "responses": [
                "For COVID-19 concerns: Monitor for fever, cough, breathing difficulty. Get tested if symptomatic. Stay updated with local health guidelines.",
                "COVID-19 prevention: 1) Vaccination 2) Wear mask in crowded places 3) Wash hands frequently 4) Maintain distance 5) Stay home if sick"
            ]
        },
        "diabetes": {
            "patterns": ["diabetes", "sugar", "blood glucose", "insulin", "hypoglycemia", "blood sugar", "diabetic"],
            "responses": [
                "Diabetes management involves: 1) Regular blood sugar monitoring 2) Balanced diet 3) Exercise 4) Medication as prescribed 5) Regular checkups",
                "Signs of diabetes: Frequent urination, excessive thirst, unexplained weight loss, fatigue. Please consult a doctor for proper testing."
            ]
        },
        "blood_pressure": {
            "patterns": ["blood pressure", "hypertension", "bp", "heart rate", "hypertensive", "high blood pressure", "low blood pressure"],
            "responses": [
                "Normal blood pressure is around 120/80 mmHg. High BP often has no symptoms but increases heart disease risk. Regular monitoring is important.",
                "For blood pressure: Reduce salt intake, exercise regularly, manage stress, limit alcohol, maintain healthy weight. Consult doctor for diagnosis."
            ]
        },
        "nutrition": {
            "patterns": ["nutrition", "healthy eating", "balanced diet", "food", "meal plan", "what to eat", "eating healthy", "vitamins"],
            "responses": [
                "A balanced diet includes: 1) Fruits & vegetables (half your plate) 2) Whole grains 3) Lean proteins 4) Healthy fats 5) Limit processed foods",
                "For nutrition: Eat a variety of colors, stay hydrated, control portion sizes, and limit sugar and sodium intake."
            ]
        },
        "exercise": {
            "patterns": ["exercise", "workout", "fitness", "gym", "running", "walking", "yoga", "sports", "physical activity"],
            "responses": [
                "Adults should aim for at least 150 minutes of moderate aerobic activity or 75 minutes of vigorous activity per week.",
                "Exercise tips: 1) Start slowly 2) Mix cardio and strength 3) Stay consistent 4) Warm up before 5) Cool down after 6) Listen to your body"
            ]
        },
        "mental_health": {
            "patterns": ["mental health", "anxiety", "depression", "stress", "mood", "emotional", "therapy", "counseling"],
            "responses": [
                "Mental health is just as important as physical health. Consider talking to a therapist or counselor if you're struggling.",
                "For stress management: 1) Practice deep breathing 2) Exercise regularly 3) Connect with others 4) Get adequate sleep 5) Consider meditation"
            ]
        },
        "sleep": {
            "patterns": ["sleep", "insomnia", "tired", "rest", "sleeping", "can't sleep", "sleep problems", "fatigue"],
            "responses": [
                "Adults need 7-9 hours of sleep per night. Good sleep hygiene includes: consistent schedule, dark room, cool temperature, no screens before bed.",
                "For better sleep: 1) Stick to a schedule 2) Avoid caffeine late 3) Exercise regularly 4) Limit screens 5) Keep room cool"
            ]
        },
        "weight": {
            "patterns": ["weight", "lose weight", "gain weight", "obesity", "overweight", "bmi", "slimming"],
            "responses": [
                "Healthy weight management involves: balanced diet, regular exercise, and lifestyle changes. Avoid crash diets.",
                "For weight goals: Create a calorie deficit for weight loss, focus on whole foods, stay active, and be patient - healthy changes take time."
            ]
        },
        "immunity": {
            "patterns": ["immune system", "immunity", "boost immune", "strengthen immunity", "fighting infection"],
            "responses": [
                "To boost immunity: 1) Eat fruits & vegetables 2) Exercise regularly 3) Get adequate sleep 4) Manage stress 5) Don't smoke 6) Limit alcohol",
                "Your immune system is your body's defense. Stay healthy with: vitamin C, zinc, proper hydration, and good hygiene practices."
            ]
        },
        "heart_health": {
            "patterns": ["heart", "cardiac", "heart disease", "cholesterol", "heart attack", "cardiovascular"],
            "responses": [
                "Heart health tips: 1) Exercise regularly 2) Eat heart-healthy foods 3) Control blood pressure 4) Manage stress 5) Don't smoke 6) Limit alcohol",
                "Warning signs of heart problems: chest pain, shortness of breath, fatigue, irregular heartbeat. Consult a doctor if you experience these."
            ]
        },
        "cancer": {
            "patterns": ["cancer", "tumor", "malignant", "carcinoma", "oncology", "cancer symptoms"],
            "responses": [
                "Cancer prevention: 1) Don't smoke 2) Maintain healthy weight 3) Exercise regularly 4) Eat fruits & vegetables 5) Limit processed meat 6) Get screened",
                "Common cancer warning signs: unexplained weight loss, persistent fatigue, unusual bleeding, lumps, persistent pain. Early detection is key - consult your doctor."
            ]
        },
        "thanks": {
            "patterns": ["thank", "thanks", "appreciate", "grateful", "thank you", "thx", "ty"],
            "responses": [
                "You're welcome! Is there anything else I can help you with?",
                "Happy to help! Take care of your health!",
                "My pleasure! Feel free to ask more questions anytime."
            ]
        },
        "goodbye": {
            "patterns": ["bye", "goodbye", "see you", "later", "take care", "farewell", "good night"],
            "responses": [
                "Goodbye! Take care of your health!",
                "Bye! Remember, your health is your wealth!",
                "Take care! Don't hesitate to return if you have more questions.",
                "See you next time! Stay healthy!"
            ]
        },
        "how_are_you": {
            "patterns": ["how are you", "how do you do", "how's it going", "how are you doing", "you doing ok"],
            "responses": [
                "I'm doing great, thank you for asking! I'm here and ready to help you with any health questions. How can I assist you today?",
                "I'm just a bot, but I'm functioning perfectly! 😄 How may I help you with your health today?"
            ]
        },
        "who_are_you": {
            "patterns": ["who are you", "what are you", "your name", "tell me about yourself", "what is this"],
            "responses": [
                "I'm MedCare AI, your virtual health assistant! I'm here to help you with health information, wellness advice, and general medical guidance.",
                "I'm an AI-powered health chatbot designed to assist you with health-related questions and provide wellness information. Think of me as your health companion!"
            ]
        },
        "jokes": {
            "patterns": ["joke", "funny", "make me laugh", "humor", "tell me something funny"],
            "responses": [
                "Here's a health joke: Why did the doctor carry a red pen? In case she needed to draw blood! 😄",
                "Why did the meditation student bring a ladder to class? Because he wanted to reach a higher level of mindfulness! 🧘",
                "Here's one: What do you call a doctor who fixes bad websites? A HTML-ician! 😄"
            ]
        },
        "motivation": {
            "patterns": ["motivate", "motivation", "inspire", "encourage", "positive", "affirmation", "quote"],
            "responses": [
                "Here's a thought: 'The greatest wealth is health.' - Virgil. Take care of yourself! 💪",
                "Remember: Small steps every day lead to big changes. You're doing great! 🌟",
                "Health tip: Your body is the only place you have to live. Treat it well! ❤️"
            ]
        },
        "default": {
            "patterns": [],
            "responses": [
                "I understand. Could you please provide more details about your concern?",
                "I'd like to help you better. Can you elaborate on what you're experiencing?",
                "Thank you for sharing. What specific symptoms or health concerns would you like to discuss?",
                "That's an interesting question! Let me help you find the best information. Could you be more specific?",
                "I'm here to help with health and wellness questions. What would you like to know more about?"
            ]
        }
    }
    
    # Simple keyword-based classifier
    print("✅ AI Chatbot initialized with medical knowledge base")
    return True


def normalize_symptom_name(symptom):
    """Normalize free-text symptoms into model-compatible feature names."""
    if not isinstance(symptom, str):
        return ""
    normalized = symptom.strip().lower().replace("-", " ").replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized)
    aliases = {
        "temperature": "fever",
        "high temperature": "fever",
        "feverish": "fever",
        "dry cough": "cough",
        "wet cough": "cough",
        "head pain": "headache",
        "tiredness": "fatigue",
        "weakness": "fatigue",
        "breathlessness": "shortness_of_breath",
        "shortness breath": "shortness_of_breath",
        "sore throat pain": "sore_throat",
        "running nose": "runny_nose",
        "body ache": "body_aches",
        "muscle pain": "body_aches",
        "stomach pain": "abdominal_pain",
        "belly pain": "abdominal_pain",
        "joint ache": "joint_pain",
        "skin irritation": "skin_rash",
        "lost taste": "loss_of_taste",
        "lost smell": "loss_of_smell",
    }
    mapped = aliases.get(normalized, normalized)
    return mapped.replace(" ", "_")


def extract_symptoms_from_text(text):
    """Extract known symptoms from chatbot free text (uses production ML feature names when loaded)."""
    if not text:
        return []
    text_l = (text or "").lower().replace("-", " ")
    extracted = []
    candidates = []
    if ML_SERVICES_AVAILABLE:
        try:
            inf = get_inference()
            if inf.is_loaded and getattr(inf, "symptom_list", None):
                candidates = list(inf.symptom_list)
        except Exception:
            candidates = []
    if not candidates:
        candidates = list(symptom_encoder or [])
    skip_prefixes = ("meta_", "ext_", "g_", "r_", "u_", "sev_", "season_")
    for symptom in candidates:
        if not isinstance(symptom, str):
            continue
        if symptom.startswith(skip_prefixes):
            continue
        readable = symptom.replace("_", " ")
        if readable in text_l or symptom in text_l:
            extracted.append(symptom)
            continue
        if "_" in symptom and symptom.replace("_", "") in text_l.replace(" ", ""):
            extracted.append(symptom)
    return sorted(list(set(extracted)))


def _ml_chat_hint(extracted_symptoms):
    """Run ensemble predictor on extracted tokens; return (hint_text, payload) or (None, None)."""
    if not ML_SERVICES_AVAILABLE or not extracted_symptoms:
        return None, None
    try:
        ps = PredictionService()
        result = ps.predict_from_symptoms(extracted_symptoms[:40], top_k=3)
        if not result.get("success"):
            return None, None
        preds = result.get("predictions") or []
        if not preds:
            return None, None
        lines = [f"- **{p.get('disease', '')}** (~{p.get('confidence', 0)}% match)" for p in preds[:3]]
        hint = (
            "\n\n---\n**Assistive model** (from symptoms in your message — not a diagnosis):\n"
            + "\n".join(lines)
        )
        return hint, preds
    except Exception:
        return None, None


def get_emergency_alert(user_message):
    """Return emergency guidance if message contains red-flag keywords."""
    text_l = (user_message or "").lower()
    matched = [kw for kw in EMERGENCY_KEYWORDS if kw in text_l]
    if not matched:
        return None
    return {
        "is_emergency": True,
        "matched_keywords": matched[:5],
        "message": (
            "This may be a medical emergency. Call your local emergency services now. "
            "If available, ask someone nearby for help and avoid delaying urgent care."
        )
    }


def initialize_disease_predictor():
    """Initialize the Disease Risk Prediction Model"""
    global disease_model, symptom_encoder, scaler, disease_labels
    
    print("🏥 Initializing AI Disease Predictor...")
    
    # Create comprehensive symptom-disease mapping
    # This simulates training on medical data
    symptoms_list = [
        'fever', 'cough', 'headache', 'fatigue', 'nausea', 'vomiting',
        'diarrhea', 'constipation', 'chest_pain', 'shortness_of_breath',
        'sore_throat', 'runny_nose', 'body_aches', 'chills', 'sweating',
        'loss_of_taste', 'loss_of_smell', 'eye_pain', 'ear_pain',
        'abdominal_pain', 'back_pain', 'joint_pain', 'skin_rash',
        'dizziness', 'confusion', 'sleeping_difficulty', 'weight_changes'
    ]
    
    disease_labels = [
        'Common Cold', 'Flu (Influenza)', 'COVID-19', 'Gastroenteritis',
        'Migraine', 'Hypertension', 'Diabetes Type 2', 'Asthma',
        'Allergic Rhinitis', 'Anxiety Disorder', 'Depression', 
        'Arthritis', 'Thyroid Disorder', 'Healthy'
    ]
    
    # Create synthetic training data (in production, use real medical datasets)
    np.random.seed(42)
    n_samples = 1000
    
    # Feature matrix
    X = np.random.randint(0, 2, size=(n_samples, len(symptoms_list)))
    
    # Generate disease labels based on symptoms (simulated patterns)
    y = []
    for i in range(n_samples):
        # Common Cold
        if X[i][0] == 1 and X[i][1] == 1 and X[i][6] == 1:
            y.append(0)
        # Flu
        elif X[i][0] == 1 and X[i][1] == 1 and X[i][12] == 1:
            y.append(1)
        # COVID-19
        elif X[i][0] == 1 and X[i][16] == 1 and X[i][17] == 1:
            y.append(2)
        # Gastroenteritis
        elif X[i][4] == 1 and X[i][5] == 1 and X[i][6] == 1:
            y.append(3)
        # Migraine
        elif X[i][2] == 1 and X[i][21] == 1:
            y.append(4)
        # Hypertension
        elif X[i][21] == 1 and X[i][22] == 1:
            y.append(5)
        # Diabetes
        elif X[i][3] == 1 and X[i][21] == 1 and X[i][22] == 1:
            y.append(6)
        # Asthma
        elif X[i][1] == 1 and X[i][9] == 1:
            y.append(7)
        # Allergies
        elif X[i][1] == 1 and X[i][10] == 1:
            y.append(8)
        # Anxiety
        elif X[i][3] == 1 and X[i][24] == 1 and X[i][25] == 1:
            y.append(9)
        # Depression
        elif X[i][3] == 1 and X[i][25] == 1 and X[i][26] == 1:
            y.append(10)
        # Arthritis
        elif X[i][21] == 1 and X[i][22] == 1 and X[i][12] == 1:
            y.append(11)
        # Thyroid
        elif X[i][3] == 1 and X[i][25] == 1:
            y.append(12)
        # Healthy
        else:
            y.append(13)
    
    # Train ensemble model
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Scale features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Train Random Forest
    rf_model = RandomForestClassifier(n_estimators=100, random_state=42)
    rf_model.fit(X_train_scaled, y_train)
    
    # Train Gradient Boosting
    gb_model = GradientBoostingClassifier(n_estimators=100, random_state=42)
    gb_model.fit(X_train_scaled, y_train)
    
    # Train Logistic Regression
    lr_model = LogisticRegression(max_iter=1000, random_state=42)
    lr_model.fit(X_train_scaled, y_train)
    
    # Ensemble predictions (weighted average)
    rf_proba = rf_model.predict_proba(X_test_scaled)
    gb_proba = gb_model.predict_proba(X_test_scaled)
    lr_proba = lr_model.predict_proba(X_test_scaled)
    
    # Weighted ensemble (RF: 0.4, GB: 0.4, LR: 0.2)
    ensemble_proba = 0.4 * rf_proba + 0.4 * gb_proba + 0.2 * lr_proba
    ensemble_pred = np.argmax(ensemble_proba, axis=1)
    
    # Evaluate
    accuracy = accuracy_score(y_test, ensemble_pred)
    print(f"📊 Ensemble Model Accuracy: {accuracy:.2%}")
    
    # Store models
    disease_model = {
        'rf': rf_model,
        'gb': gb_model,
        'lr': lr_model,
        'accuracy': accuracy
    }
    
    symptom_encoder = symptoms_list
    scaler = scaler
    
    print("✅ AI Disease Predictor initialized")
    return True


# ==================== CHATBOT ENDPOINTS ====================

# Try to import OpenAI for LLM-powered chatbot
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("⚠️ OpenAI not installed. Install with: pip install openai")

def get_openai_response(user_message, session_id):
    """Get response from OpenAI GPT model"""
    global conversation_history
    
    # Get or initialize conversation history for this session
    if session_id not in conversation_history:
        conversation_history[session_id] = [
            {"role": "system", "content": """You are MedCare AI, a helpful and knowledgeable healthcare AI assistant. 
You provide general health information, wellness advice, and can help users understand their symptoms.
IMPORTANT: Always remind users that you are not a doctor and they should consult healthcare professionals for medical advice.
Never prescribe medication or provide specific medical diagnoses. Be empathetic, clear, and informative.
If someone mentions medical emergencies, immediately advise them to call emergency services."""}
        ]
    
    # Add user message to history
    conversation_history[session_id].append({"role": "user", "content": user_message})
    
    # Keep conversation history manageable (last 10 messages)
    if len(conversation_history[session_id]) > 11:
        conversation_history[session_id] = [conversation_history[session_id][0]] + conversation_history[session_id][-10:]
    
    try:
        # Set API key from environment or config
        if OPENAI_API_KEY:
            openai.api_key = OPENAI_API_KEY
            
        # Make API call
        response = openai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=conversation_history[session_id],
            max_tokens=500,
            temperature=0.7
        )
        
        # Get response
        ai_response = response.choices[0].message.content
        
        # Add AI response to history
        conversation_history[session_id].append({"role": "assistant", "content": ai_response})
        
        return ai_response
        
    except Exception as e:
        print(f"OpenAI API Error: {e}")
        return None


@app.route('/api/chatbot', methods=['POST'])
def chatbot_message():
    """Process chatbot message and return AI response - LLM powered"""
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        session_id = data.get('session_id', 'default')
        
        if not user_message:
            return jsonify({'error': 'No message provided'}), 400

        emergency_alert = get_emergency_alert(user_message)
        extracted_symptoms = extract_symptoms_from_text(user_message)

        # Fast emergency override for safety-critical prompts.
        if emergency_alert:
            return jsonify({
                'success': True,
                'response': emergency_alert['message'],
                'source': 'safety-triage',
                'triage': emergency_alert,
                'suggested_symptoms': extracted_symptoms
            })
        
        # Check if OpenAI is available and configured
        if OPENAI_AVAILABLE and OPENAI_API_KEY:
            # Try OpenAI first
            response = get_openai_response(user_message, session_id)
            if response:
                ml_extra, ml_preds = _ml_chat_hint(extracted_symptoms)
                payload = {
                    'success': True,
                    'response': response + (ml_extra or ''),
                    'source': 'openai',
                    'model': OPENAI_MODEL,
                    'suggested_symptoms': extracted_symptoms,
                }
                if ml_preds is not None:
                    payload['ml_predictions'] = ml_preds
                return jsonify(payload)
        
        # Fallback to rule-based chatbot
        matched_intent = 'default'
        max_matches = 0
        
        for intent_name, intent_data in intents.items():
            if intent_name == 'default':
                continue
            
            matches = 0
            for pattern in intent_data['patterns']:
                if pattern.lower() in user_message.lower():
                    matches += 1
            
            if matches > max_matches:
                max_matches = matches
                matched_intent = intent_name
        
        # Get response
        responses = intents[matched_intent]['responses']
        response = random.choice(responses)
        ml_extra, ml_preds = _ml_chat_hint(extracted_symptoms)
        payload = {
            'success': True,
            'response': response + (ml_extra or ''),
            'intent': matched_intent,
            'source': 'rule-based',
            'suggested_symptoms': extracted_symptoms,
        }
        if ml_preds is not None:
            payload['ml_predictions'] = ml_preds
        return jsonify(payload)
    
    except Exception as e:
        print(f"Chatbot error: {e}")
        return jsonify({
            'success': False,
            'response': "I apologize, but I encountered an error. Please try again.",
            'error': str(e)
        }), 500


@app.route('/api/chatbot/clear', methods=['POST'])
def clear_chat_history():
    """Clear conversation history for a session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id', 'default')
        
        if session_id in conversation_history:
            del conversation_history[session_id]
        
        return jsonify({
            'success': True,
            'message': 'Chat history cleared'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/chatbot/health', methods=['GET'])
def chatbot_health():
    """Check chatbot status"""
    return jsonify({
        'status': 'healthy',
        'service': 'MedCare AI Chatbot',
        'version': '2.0.0',
        'openai_available': OPENAI_AVAILABLE,
        'openai_configured': bool(OPENAI_API_KEY),
        'active_model': OPENAI_MODEL if OPENAI_API_KEY else 'rule-based'
    })


# ==================== DISEASE PREDICTION ENDPOINTS ====================
@app.route('/api/analyze', methods=['POST'])
def analyze_health():
    """Analyze symptoms and predict disease risk using production ML pipeline"""
    try:
        data = request.get_json()
        symptoms = data.get('symptoms', [])
        patient_info = data.get('patient_info', {})
        
        if not symptoms:
            return jsonify({'success': False, 'error': 'No symptoms provided'}), 400
        
        # Try using new production service
        if ML_SERVICES_AVAILABLE:
            try:
                prediction_service = PredictionService()
                result = prediction_service.predict_from_symptoms(
                    symptoms, 
                    patient_info=patient_info,
                    top_k=3
                )
                
                # Normalize response format
                if result['success']:
                    return jsonify({
                        'success': True,
                        'predictions': result['predictions'],
                        'risk_level': result.get('risk_level', 'unknown'),
                        'model_confidence': result['predictions'][0]['confidence'] if result['predictions'] else 0,
                        'symptoms_analyzed': result['symptoms_analyzed']['recognized'],
                        'recognized_symptoms': result['symptoms_analyzed']['recognized_list'],
                        'unrecognized_symptoms': result['symptoms_analyzed']['unrecognized_list'],
                        'urgency_flags': [],
                        'models_used': result.get('models_used', ['rf', 'lr', 'svm'])
                    })
                else:
                    # Fall back to legacy if new service fails
                    raise ValueError(result['error'])
            except Exception as e:
                print(f"⚠️  Production service error, falling back: {e}")
                # Fall through to legacy implementation
        
        # Legacy implementation fallback
        normalized_symptoms = []
        unknown_symptoms = []

        # Convert symptoms to feature vector (using legacy logic)
        symptom_vector = np.zeros(len(symptom_encoder) if symptom_encoder else 1)
        for symptom in symptoms:
            symptom_lower = normalize_symptom_name(symptom)
            if symptom_encoder and symptom_lower in symptom_encoder:
                normalized_symptoms.append(symptom_lower)
                idx = symptom_encoder.index(symptom_lower)
                symptom_vector[idx] = 1
            else:
                unknown_symptoms.append(symptom)
        
        # Make prediction with fallback
        if disease_model and scaler:
            symptom_scaled = scaler.transform([symptom_vector])
            rf_proba = disease_model['rf'].predict_proba(symptom_scaled)[0]
            gb_proba = disease_model['gb'].predict_proba(symptom_scaled)[0]
            lr_proba = disease_model['lr'].predict_proba(symptom_scaled)[0]
            
            ensemble_proba = 0.4 * rf_proba + 0.4 * gb_proba + 0.2 * lr_proba
            top_indices = np.argsort(ensemble_proba)[::-1][:3]
            
            predictions = []
            for idx in top_indices:
                predictions.append({
                    'disease': disease_labels[idx] if disease_labels else f'Disease_{idx}',
                    'confidence': round(float(ensemble_proba[idx]) * 100, 2),
                    'probability': round(float(ensemble_proba[idx]) * 100, 2)
                })
        else:
            predictions = [
                {'disease': 'Unable to determine', 'confidence': 0, 'probability': 0}
            ]

        return jsonify({
            'success': True,
            'predictions': predictions,
            'risk_level': 'unknown',
            'model_confidence': predictions[0].get('confidence', 0) if predictions else 0,
            'symptoms_analyzed': len(symptoms),
            'recognized_symptoms': sorted(list(set(normalized_symptoms))),
            'unrecognized_symptoms': sorted(list(set(unknown_symptoms))),
            'urgency_flags': [],
            'mode': 'fallback'
        })
    
    except Exception as e:
        print(f"Analysis error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/analyze/disease-info', methods=['GET'])
def get_disease_info():
    """Get information about supported diseases"""
    disease_info = {
        'Common Cold': {
            'description': 'Viral infection of the upper respiratory tract',
            'symptoms': ['Runny nose', 'Sore throat', 'Cough', 'Sneezing'],
            'severity': 'Mild',
            'self_care': 'Rest, hydration, OTC cold remedies'
        },
        'Flu (Influenza)': {
            'description': 'Viral respiratory infection',
            'symptoms': ['Fever', 'Body aches', 'Fatigue', 'Cough'],
            'severity': 'Moderate',
            'self_care': 'Rest, fluids, antiviral within 48 hours'
        },
        'COVID-19': {
            'description': 'Coronavirus disease',
            'symptoms': ['Fever', 'Cough', 'Loss of taste/smell', 'Shortness of breath'],
            'severity': 'Moderate to Severe',
            'self_care': 'Isolation, rest, monitor oxygen, seek medical care if severe'
        },
        'Gastroenteritis': {
            'description': 'Stomach flu - inflammation of intestines',
            'symptoms': ['Vomiting', 'Diarrhea', 'Nausea', 'Abdominal pain'],
            'severity': 'Mild to Moderate',
            'self_care': 'Hydration, bland diet, rest'
        },
        'Migraine': {
            'description': 'Severe recurring headache',
            'symptoms': ['Headache', 'Nausea', 'Light sensitivity', 'Visual disturbances'],
            'severity': 'Mild to Moderate',
            'self_care': 'Rest in dark room, pain relievers, identify triggers'
        },
        'Hypertension': {
            'description': 'High blood pressure',
            'symptoms': ['Often asymptomatic', 'Headache', 'Shortness of breath', 'Nosebleeds'],
            'severity': 'Chronic - Serious if untreated',
            'self_care': 'Low sodium diet, exercise, medication as prescribed'
        },
        'Diabetes Type 2': {
            'description': 'Chronic metabolic disorder',
            'symptoms': ['Frequent urination', 'Thirst', 'Fatigue', 'Slow healing'],
            'severity': 'Chronic - Serious',
            'self_care': 'Diet control, exercise, medication, regular monitoring'
        }
    }
    
    return jsonify(disease_info)


def get_disease_recommendation(disease):
    """Get recommendation for a disease"""
    recommendations = {
        'Common Cold': 'Rest at home, stay hydrated, OTC medications. Consult doctor if symptoms worsen.',
        'Flu (Influenza)': 'Rest, fluids, consider antiviral medication within 48 hours. Seek care if high fever.',
        'COVID-19': 'Self-isolate immediately. Monitor oxygen levels. Seek emergency care for breathing difficulty.',
        'Gastroenteritis': 'Stay hydrated with electrolytes, bland diet. Seek care if severe dehydration.',
        'Migraine': 'Rest in dark quiet room, OTC pain relievers. Consult neurologist for chronic cases.',
        'Hypertension': 'Schedule doctor appointment. Monitor BP regularly, reduce salt, exercise.',
        'Diabetes Type 2': 'Consult endocrinologist. Regular glucose monitoring, diet modification, exercise.',
        'Asthma': 'Use rescue inhaler as prescribed. Avoid triggers. See pulmonologist.',
        'Allergic Rhinitis': 'OTC antihistamines, nasal sprays. Avoid allergens.',
        'Anxiety Disorder': 'Consider therapy, relaxation techniques. Consult psychiatrist if severe.',
        'Depression': 'Seek mental health professional. Therapy and/or medication can help.',
        'Arthritis': 'Consult rheumatologist. Exercise, weight management, pain management.',
        'Thyroid Disorder': 'Endocrinologist consultation required. Blood tests for diagnosis.',
        'Healthy': 'Maintain healthy lifestyle. Regular checkups recommended.'
    }
    return recommendations.get(disease, 'Consult a healthcare professional.')


def calculate_risk_level(predictions, patient_info):
    """Calculate overall risk level based on predictions and patient info"""
    top_probability = predictions[0]['probability'] if predictions else 0
    top_disease = predictions[0]['disease'] if predictions else 'Unknown'
    
    # High risk conditions
    high_risk_diseases = ['COVID-19', 'Hypertension', 'Diabetes Type 2', 'Asthma']
    
    # Check age factor
    age = patient_info.get('age', 0)
    age_factor = 0
    if age > 60:
        age_factor = 15
    elif age > 45:
        age_factor = 10
    
    # Calculate risk
    base_risk = top_probability
    total_risk = min(base_risk + age_factor, 100)
    
    if top_disease in high_risk_diseases and top_probability > 40:
        return 'High'
    elif total_risk > 50:
        return 'Medium'
    else:
        return 'Low'


@app.route('/api/analyze/health', methods=['GET'])
def analyzer_health():
    """Check analyzer status"""
    return jsonify({
        'status': 'healthy',
        'model': 'MedCare AI Disease Predictor',
        'version': '1.0.0',
        'accuracy': disease_model['accuracy'] if disease_model else 0,
        'supported_diseases': len(disease_labels) if disease_labels else 0
    })


# ==================== EXPLAINABILITY API (SHAP + LIME) ====================

@app.route('/api/explainability/health', methods=['GET'])
def explainability_health():
    svc = get_explainability_service()
    if not svc:
        return jsonify({
            'status': 'unavailable',
            'ml_services_available': ML_SERVICES_AVAILABLE,
        }), 503
    inf = get_inference()
    return jsonify({
        'status': 'healthy' if inf.is_loaded else 'degraded',
        'model_loaded': bool(inf.is_loaded),
        'error': inf.error_msg,
        'csv_available': bool(os.path.exists(get_explainability_csv_path())),
        'endpoints': {
            'shap_global': '/api/explainability/shap-global',
            'lime_local': '/api/explainability/lime-local'
        }
    })


@app.route('/api/explainability/shap-global', methods=['GET'])
def shap_global():
    """Global feature importance using SHAP (tree models preferred)."""
    svc = get_explainability_service()
    if not svc:
        return jsonify({'success': False, 'error': 'Explainability service unavailable'}), 503
    csv_path = get_explainability_csv_path()
    if not os.path.exists(csv_path):
        return jsonify({'success': False, 'error': 'Missing explainability CSV (run train_ensemble_models.py or add disease_symptoms.csv)'}), 500

    try:
        top_n = int(request.args.get('top_n', 20))
        result = svc.shap_global_summary(csv_path, top_n=top_n)
        code = 200 if result.get('success') else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/explainability/lime-local', methods=['POST'])
def lime_local():
    """Local explanation for a single symptom vector using LIME."""
    svc = get_explainability_service()
    if not svc:
        return jsonify({'success': False, 'error': 'Explainability service unavailable'}), 503
    csv_path = get_explainability_csv_path()
    if not os.path.exists(csv_path):
        return jsonify({'success': False, 'error': 'Missing explainability CSV (run train_ensemble_models.py or add disease_symptoms.csv)'}), 500

    try:
        data = request.get_json() or {}
        symptoms = data.get('symptoms', []) or []
        top_k_features = int(data.get('top_k_features', 10))

        if not isinstance(symptoms, list) or len(symptoms) == 0:
            return jsonify({'success': False, 'error': 'Provide symptoms: [..]'}), 400

        # Build raw symptom vector aligned with production inference symptoms
        inf = get_inference()
        vec = np.zeros(len(inf.get_all_symptoms()), dtype=float)
        recognized, unrecognized = [], []
        for s in symptoms:
            idx = inf.get_symptom_index(s)
            if idx is None:
                idx = inf.get_symptom_index(normalize_symptom_token(s))
            if idx is None:
                unrecognized.append(s)
            else:
                vec[idx] = 1.0
                recognized.append(s)

        result = svc.explain_lime_local(vec, csv_path, top_k_features=top_k_features)
        if result.get('success'):
            result['symptoms_analyzed'] = {
                'recognized': sorted(list(set(recognized))),
                'unrecognized': sorted(list(set(unrecognized)))
            }
        code = 200 if result.get('success') else 400
        return jsonify(result), code
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== ADMIN API ENDPOINTS (MongoDB) ====================

@app.route('/api/admin/patients', methods=['GET'])
def get_all_patients():
    """Get all patients from MongoDB"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        patients = list(db.patients.find({}).sort('createdAt', -1))
        
        # Convert ObjectId to string for JSON serialization
        for patient in patients:
            patient['_id'] = str(patient.get('_id', ''))
        
        return jsonify({
            'success': True,
            'patients': patients,
            'count': len(patients)
        })
    except Exception as e:
        print(f"Error fetching patients: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/patients/<patient_id>', methods=['GET'])
def get_patient(patient_id):
    """Get a single patient by ID"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        patient = db.patients.find_one({'_id': ObjectId(patient_id)})
        
        if not patient:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        patient['_id'] = str(patient.get('_id', ''))
        
        return jsonify({
            'success': True,
            'patient': patient
        })
    except Exception as e:
        print(f"Error fetching patient: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/patients', methods=['POST'])
def create_patient():
    """Create a new patient in MongoDB"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        data = request.get_json()
        
        # Check if patient with mobile_number already exists
        existing = db.patients.find_one({'mobile_number': data.get('mobile_number')})
        if existing:
            # Update existing patient
            data['updatedAt'] = datetime.utcnow()
            db.patients.update_one(
                {'mobile_number': data.get('mobile_number')},
                {'$set': data}
            )
            return jsonify({
                'success': True,
                'message': 'Patient updated successfully',
                'mobile_number': data.get('mobile_number')
            })
        
        # Create new patient
        data['createdAt'] = datetime.utcnow()
        data['updatedAt'] = datetime.utcnow()
        
        result = db.patients.insert_one(data)
        
        return jsonify({
            'success': True,
            'message': 'Patient created successfully',
            'patient_id': str(result.inserted_id)
        })
    except Exception as e:
        print(f"Error creating patient: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/patients/<patient_id>', methods=['PUT'])
def update_patient(patient_id):
    """Update a patient in MongoDB"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        data = request.get_json()
        data['updatedAt'] = datetime.utcnow()
        
        result = db.patients.update_one(
            {'_id': ObjectId(patient_id)},
            {'$set': data}
        )
        
        if result.matched_count == 0:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        return jsonify({
            'success': True,
            'message': 'Patient updated successfully'
        })
    except Exception as e:
        print(f"Error updating patient: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/patients/<patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    """Delete a patient from MongoDB"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        result = db.patients.delete_one({'_id': ObjectId(patient_id)})
        
        if result.deleted_count == 0:
            return jsonify({'success': False, 'error': 'Patient not found'}), 404
        
        return jsonify({
            'success': True,
            'message': 'Patient deleted successfully'
        })
    except Exception as e:
        print(f"Error deleting patient: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    """Get admin statistics"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        total = db.patients.count_documents({})
        
        # Count by status
        complete = db.patients.count_documents({'intakeComplete': True})
        pending = total - complete
        
        return jsonify({
            'success': True,
            'stats': {
                'total_patients': total,
                'complete_intakes': complete,
                'pending_intakes': pending
            }
        })
    except Exception as e:
        print(f"Error fetching stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/health', methods=['GET'])
def admin_health():
    """Check admin API health"""
    return jsonify({
        'status': 'healthy',
        'mongodb_connected': mongo_connected,
        'version': '1.0.0'
    })


# ==================== VITAL SIGNS ENDPOINTS ====================

@app.route('/api/vital-signs/analyze', methods=['POST'])
def analyze_vital_signs():
    """Analyze vital signs from camera-based PPG signal data"""
    try:
        data = request.get_json()
        
        # Extract PPG signal data
        red_signal = data.get('red_signal', [])
        green_signal = data.get('green_signal', [])
        blue_signal = data.get('blue_signal', [])
        timestamps_ms = data.get('timestamps_ms')
        fps = float(data.get('fps', 30))
        
        if not red_signal or len(red_signal) < 30:
            return jsonify({
                'success': False,
                'error': 'Insufficient signal data. Need at least 30 samples.'
            }), 400

        # New signal-processing pipeline (scipy-based if available)
        from services.vital_signs_processing import analyze_rgb_signals
        result = analyze_rgb_signals(
            red_signal=red_signal,
            green_signal=green_signal,
            blue_signal=blue_signal,
            fps=fps,
            timestamps_ms=timestamps_ms,
        )

        heart_rate = result.heart_rate_bpm
        systolic, diastolic = result.systolic_mmHg, result.diastolic_mmHg
        spo2 = result.spo2_percent
        resp_rate = result.respiratory_rate_bpm

        # Temperature remains a simplified heuristic (camera-only)
        temperature = estimate_temp_from_signal(np.array(red_signal), np.array(green_signal), blue_signal)
        
        return jsonify({
            'success': True,
            'vital_signs': {
                'heart_rate': heart_rate,
                'blood_pressure': {
                    'systolic': systolic,
                    'diastolic': diastolic
                },
                'spo2': spo2,
                'temperature_fahrenheit': temperature,
                'respiratory_rate': resp_rate,
                'signal_quality': round(float(result.signal_quality) * 100, 1)
            },
            'status': 'analyzed',
            'meta': result.meta
        })
        
    except Exception as e:
        print(f"Vital signs analysis error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def estimate_hr_from_ppg(ppg_signal):
    """Estimate heart rate from PPG signal using peak detection"""
    # Simple peak detection
    samples = ppg_signal[-150:]  # Last ~5 seconds
    
    # Find peaks
    peaks = []
    for i in range(2, len(samples) - 2):
        if (samples[i] > samples[i-1] and samples[i] > samples[i-2] and
            samples[i] > samples[i+1] and samples[i] > samples[i+2]):
            peaks.append(i)
    
    if len(peaks) < 2:
        return np.random.randint(65, 85)
    
    # Calculate average interval
    intervals = [peaks[i] - peaks[i-1] for i in range(1, len(peaks))]
    avg_interval = np.mean(intervals)
    
    # Convert to BPM (assuming ~30 fps)
    bpm = int(round((30 / avg_interval) * 60))
    
    return max(50, min(150, bpm))


def estimate_bp_from_ppg(ppg_signal, heart_rate):
    """Estimate blood pressure from PPG signal"""
    # Calculate signal variability
    mean_val = np.mean(ppg_signal[-60:])
    std_val = np.std(ppg_signal[-60:])
    
    # Base values
    systolic = 120
    diastolic = 80
    
    # Adjust based on heart rate
    if heart_rate > 80:
        systolic += int(round((heart_rate - 80) * 0.3))
    elif heart_rate < 60:
        systolic -= int(round((60 - heart_rate) * 0.2))
    
    # Adjust based on signal variability
    variability_factor = std_val / 10
    systolic = int(round(systolic + variability_factor))
    diastolic = int(round(diastolic + variability_factor * 0.5))
    
    systolic = max(90, min(180, systolic))
    diastolic = max(60, min(120, diastolic))
    
    return systolic, diastolic


def estimate_spo2_from_ppg(red_signal, green_signal):
    """Estimate SpO2 from PPG red/green ratio"""
    red_mean = np.mean(red_signal[-30:])
    green_mean = np.mean(green_signal[-30:])
    
    ratio = red_mean / green_mean if green_mean > 0 else 1.5
    
    # Convert to SpO2 estimate
    base_spO2 = 98
    variation = (ratio - 1.5) * 5
    
    spo2 = max(95, min(100, int(round(base_spO2 + variation))))
    
    return spo2


def estimate_temp_from_signal(red_signal, green_signal, blue_signal):
    """Estimate body temperature from RGB signal"""
    if blue_signal:
        avg_red = np.mean(red_signal[-30:])
        avg_green = np.mean(green_signal[-30:])
        
        thermal_ratio = avg_red / avg_green if avg_green > 0 else 1.05
        
        base_temp = 98.6
        temp_variation = (thermal_ratio - 1.05) * 10
        
        temperature = base_temp + temp_variation + np.random.uniform(-0.2, 0.2)
        temperature = max(95.0, min(104.0, temperature))
        
        return round(temperature, 1)
    else:
        # Fallback
        return round(98.6 + np.random.uniform(-1, 1), 1)


def estimate_resp_rate(ppg_signal):
    """Estimate respiratory rate from PPG signal"""
    # Simplified respiratory rate estimation
    # In real implementation, this would use more complex signal processing
    
    return np.random.randint(12, 16)


@app.route('/api/vital-signs/health', methods=['GET'])
def vital_signs_health():
    """Check vital signs API health"""
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'endpoints': {
            'analyze': '/api/vital-signs/analyze'
        }
    })


# ==================== INTAKE & INSURANCE ENDPOINTS ====================
def extract_auth_user():
    """Extract user information from JWT Authorization header."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    token = auth_header.split(' ', 1)[1].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return {'user_id': payload.get('user_id'), 'email': payload.get('email')}
    except Exception:
        return None


@app.route('/api/intake/submit', methods=['POST'])
def submit_intake():
    """Structured intake endpoint with NLP normalization"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500

    try:
        auth_user = extract_auth_user()
        if not auth_user or not auth_user.get('user_id'):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401

        data = request.get_json() or {}
        required_fields = ['mobile_number', 'full_name', 'age', 'gender', 'symptoms']
        missing_fields = [f for f in required_fields if not data.get(f)]
        if missing_fields:
            return jsonify({'success': False, 'error': f'Missing fields: {", ".join(missing_fields)}'}), 400

        # Use IntakeNLPService to normalize symptoms and extract risk factors
        normalized_symptoms = []
        extracted_risk_factors = []
        
        if IntakeNLPService:
            try:
                # Normalize symptoms
                symptom_text = data.get('symptoms', '')
                normalized_symptoms = IntakeNLPService.normalize_symptoms(symptom_text)
                
                # Extract risk factors from medical history
                medical_history = data.get('medical_history', '')
                extracted_risk_factors = IntakeNLPService.extract_risk_factors(medical_history)
                
                # Extract severity
                severity_text = data.get('severity', '')
                extracted_severity = IntakeNLPService.extract_severity(severity_text)
            except Exception as e:
                print(f"⚠️  NLP normalization warning: {e}")
                normalized_symptoms = [data.get('symptoms', '')]
                extracted_severity = 'unknown'

        doc = {
            'user_id': auth_user['user_id'],
            'mobile_number': str(data.get('mobile_number')).strip(),
            'name': data.get('full_name', '').strip(),
            'full_name': data.get('full_name', '').strip(),
            'age': int(data.get('age', 0)),
            'gender': data.get('gender', '').strip(),
            'height': data.get('height'),
            'weight': data.get('weight'),
            'symptoms_raw': data.get('symptoms', ''),
            'symptoms_normalized': normalized_symptoms,  # NLP-normalized symptoms
            'duration': data.get('duration', ''),
            'severity': data.get('severity', extracted_severity) if data.get('severity') else extracted_severity,
            'existing_conditions': data.get('existing_conditions', []),
            'risk_factors': extracted_risk_factors or data.get('risk_factors', []),  # NLP-extracted risk factors
            'medical_history': data.get('medical_history', ''),
            'painLevel': data.get('pain_level'),
            'doctorPreConsultation': data.get('doctor_preconsultation'),
            'intakeComplete': True,
            'source': 'backend_api',
            'nlp_processed': IntakeNLPService is not None,
            'updatedAt': datetime.utcnow(),
            'createdAt': datetime.utcnow()
        }

        existing = db.patients.find_one({'mobile_number': doc['mobile_number'], 'user_id': auth_user['user_id']})
        if existing:
            doc['createdAt'] = existing.get('createdAt', datetime.utcnow())
            db.patients.update_one({'_id': existing['_id']}, {'$set': doc})
            patient_id = str(existing['_id'])
        else:
            result = db.patients.insert_one(doc)
            patient_id = str(result.inserted_id)

        return jsonify({
            'success': True,
            'message': 'Intake submitted',
            'patient_id': patient_id,
            'normalized': {
                'symptoms': normalized_symptoms,
                'risk_factors': extracted_risk_factors
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/insurance/verify', methods=['POST'])
def verify_insurance():
    """Backend insurance verification endpoint."""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500

    try:
        auth_user = extract_auth_user()
        if not auth_user or not auth_user.get('user_id'):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401

        data = request.get_json() or {}
        mobile_number = str(data.get('patient_id') or data.get('mobile_number') or '').strip()
        card_number = str(data.get('insurance_number') or '').strip().upper()
        provider = data.get('provider', 'Insurance Provider')
        if not mobile_number or len(card_number) < 6:
            return jsonify({'success': False, 'error': 'Valid patient ID and insurance number are required'}), 400

        # Deterministic local verification rule; replace with payer API integration for production.
        status = 'Verified' if len(card_number) >= 6 else 'Not Found'
        insurance = {
            'card_number': card_number,
            'provider': provider,
            'status': status,
            'verified_at': datetime.utcnow().isoformat()
        }

        db.patients.update_one(
            {'mobile_number': mobile_number, 'user_id': auth_user['user_id']},
            {'$set': {'insurance': insurance, 'updatedAt': datetime.utcnow()}},
            upsert=False
        )

        return jsonify({'success': True, 'insurance': insurance})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== MIGRATION ENDPOINTS ====================

@app.route('/api/admin/migrate-from-localstorage', methods=['POST'])
def migrate_from_localstorage():
    """Migrate data from localStorage to MongoDB"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        data = request.get_json()
        patients_data = data.get('patients', [])
        
        migrated = 0
        skipped = 0
        
        for patient in patients_data:
            mobile_number = patient.get('mobile_number')
            if not mobile_number:
                skipped += 1
                continue
            
            # Check if exists
            existing = db.patients.find_one({'mobile_number': mobile_number})
            
            patient['createdAt'] = datetime.utcnow()
            patient['updatedAt'] = datetime.utcnow()
            
            if existing:
                # Update
                db.patients.update_one(
                    {'mobile_number': mobile_number},
                    {'$set': patient}
                )
            else:
                # Insert
                db.patients.insert_one(patient)
            
            migrated += 1
        
        return jsonify({
            'success': True,
            'migrated': migrated,
            'skipped': skipped,
            'message': f'Successfully migrated {migrated} patients'
        })
    except Exception as e:
        print(f"Error migrating data: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== USER AUTHENTICATION ENDPOINTS ====================

def generate_user_id():
    """Generate a unique user ID"""
    import uuid
    return str(uuid.uuid4())


def generate_email_verification_token():
    """Generate secure token for email verification links."""
    return secrets.token_urlsafe(32)


def send_verification_email(email, name, token):
    """Send verification email using SMTP if configured."""
    verify_url = f"{FRONTEND_BASE_URL}/verify-email.html?token={token}"
    subject = "Verify your MedCare AI account"
    body = (
        f"Hi {name},\n\n"
        "Welcome to MedCare AI.\n\n"
        "Please verify your email by opening this link:\n"
        f"{verify_url}\n\n"
        "This link expires in 10 minutes.\n\n"
        "If you didn't create this account, please ignore this email."
    )

    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and SMTP_FROM_EMAIL):
        print("SMTP not configured. Verification link (dev mode):", verify_url)
        return {
            'sent': False,
            'dev_mode': True,
            'verify_url': verify_url
        }

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SMTP_FROM_EMAIL
    msg['To'] = email
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return {'sent': True, 'dev_mode': False}
    except Exception as e:
        print(f"Email send failed: {e}")
        return {
            'sent': False,
            'dev_mode': True,
            'verify_url': verify_url
        }

def generate_token(user_id, email):
    """Generate JWT token"""
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def decode_token(token):
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    """Decorator to require valid JWT token"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'success': False, 'error': 'Token is missing'}), 401
        
        payload = decode_token(token)
        if not payload:
            return jsonify({'success': False, 'error': 'Token is invalid or expired'}), 401
        
        # Add user info to request
        g.user_id = payload.get('user_id')
        g.email = payload.get('email')
        
        return f(*args, **kwargs)
    
    return decorated


@app.route('/api/auth/register', methods=['POST'])
def register_user():
    """Register a new user"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        data = request.get_json()
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        
        # Validation
        if not email or not password or not name:
            return jsonify({'success': False, 'error': 'Email, password, and name are required'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        # Check if email already exists
        existing_user = db.users.find_one({'email': email})
        if existing_user:
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        
        # Hash password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # Create user
        user_id = generate_user_id()
        verification_token = generate_email_verification_token()
        verification_expires_at = datetime.utcnow() + timedelta(minutes=10)

        user_data = {
            'user_id': user_id,
            'email': email,
            'name': name,
            'password_hash': password_hash,
            'email_verified': False,
            'verification_token': verification_token,
            'verification_expires_at': verification_expires_at,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = db.users.insert_one(user_data)
        
        email_result = send_verification_email(email, name, verification_token)

        # In local/dev environments without SMTP, auto-verify users so auth works end-to-end.
        if email_result.get('dev_mode', False):
            db.users.update_one(
                {'_id': result.inserted_id},
                {'$set': {'email_verified': True, 'updated_at': datetime.utcnow()},
                 '$unset': {'verification_token': "", 'verification_expires_at': ""}}
            )

        return jsonify({
            'success': True,
            'message': 'User registered successfully.',
            'user_id': user_id,
            'email': email,
            'name': name,
            'email_verification_required': not email_result.get('dev_mode', False),
            'email_sent': email_result.get('sent', False),
            'dev_mode': email_result.get('dev_mode', False),
            'dev_verify_url': email_result.get('verify_url')
        })
        
    except Exception as e:
        print(f"Error registering user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login_user():
    """Login user"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        data = request.get_json()
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400
        
        # Find user
        user = db.users.find_one({'email': email})
        if not user:
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Verify password
        if not bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        if not user.get('email_verified', False):
            # Local/dev fallback: if SMTP isn't configured, allow login by auto-verifying.
            if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and SMTP_FROM_EMAIL):
                db.users.update_one(
                    {'_id': user['_id']},
                    {'$set': {'email_verified': True, 'updated_at': datetime.utcnow()},
                     '$unset': {'verification_token': "", 'verification_expires_at': ""}}
                )
                user['email_verified'] = True
            else:
                return jsonify({
                    'success': False,
                    'needs_verification': True,
                    'error': 'Email not verified. Please verify your email before login.'
                }), 403

        # Generate token
        token = generate_token(user['user_id'], user['email'])
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user_id': user['user_id'],
            'email': user['email'],
            'name': user['name'],
            'token': token
        })
        
    except Exception as e:
        print(f"Error logging in: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/verify', methods=['GET'])
@token_required
def verify_token():
    """Verify token is valid"""
    return jsonify({
        'success': True,
        'user_id': g.user_id,
        'email': g.email
    })


@app.route('/api/auth/verify-email', methods=['POST'])
def verify_email():
    """Verify user email via secure verification token."""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500

    try:
        data = request.get_json() or {}
        token = data.get('token', '').strip()
        if not token:
            return jsonify({'success': False, 'error': 'Verification token is required'}), 400

        user = db.users.find_one({'verification_token': token})
        if not user:
            return jsonify({'success': False, 'error': 'Invalid verification token'}), 400

        if user.get('email_verified'):
            auth_token = generate_token(user['user_id'], user['email'])
            return jsonify({
                'success': True,
                'message': 'Email already verified',
                'token': auth_token,
                'user_id': user['user_id'],
                'email': user['email'],
                'name': user.get('name')
            })

        expires_at = user.get('verification_expires_at')
        if not expires_at or datetime.utcnow() > expires_at:
            return jsonify({
                'success': False,
                'expired': True,
                'error': 'Verification token expired'
            }), 400

        db.users.update_one(
            {'_id': user['_id']},
            {'$set': {'email_verified': True, 'updated_at': datetime.utcnow()},
             '$unset': {'verification_token': "", 'verification_expires_at': ""}}
        )

        auth_token = generate_token(user['user_id'], user['email'])
        return jsonify({
            'success': True,
            'message': 'Email verified successfully',
            'token': auth_token,
            'user_id': user['user_id'],
            'email': user['email'],
            'name': user.get('name')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification email for unverified accounts."""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500

    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400

        user = db.users.find_one({'email': email})
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        if user.get('email_verified'):
            return jsonify({'success': False, 'error': 'Email already verified'}), 400

        verification_token = generate_email_verification_token()
        verification_expires_at = datetime.utcnow() + timedelta(minutes=10)
        db.users.update_one(
            {'_id': user['_id']},
            {'$set': {
                'verification_token': verification_token,
                'verification_expires_at': verification_expires_at,
                'updated_at': datetime.utcnow()
            }}
        )

        email_result = send_verification_email(email, user.get('name', 'User'), verification_token)
        return jsonify({
            'success': True,
            'message': 'Verification email sent',
            'email_sent': email_result.get('sent', False),
            'dev_mode': email_result.get('dev_mode', False),
            'dev_verify_url': email_result.get('verify_url')
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/profile', methods=['GET'])
@token_required
def get_profile():
    """Get user profile"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        user = db.users.find_one({'user_id': g.user_id})
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user_id': user['user_id'],
            'email': user['email'],
            'name': user['name'],
            'created_at': user.get('created_at', '').isoformat() if user.get('created_at') else None
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/profile', methods=['PUT'])
@token_required
def update_profile():
    """Update user profile"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        
        db.users.update_one(
            {'user_id': g.user_id},
            {'$set': {'name': name, 'updated_at': datetime.utcnow()}}
        )
        
        return jsonify({
            'success': True,
            'message': 'Profile updated successfully'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== USER DATA ENDPOINTS (Multi-User) ====================

@app.route('/api/user/patients', methods=['GET'])
@token_required
def get_user_patients():
    """Get all patients for the logged-in user"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        # Filter by user_id
        patients = list(db.patients.find({'user_id': g.user_id}).sort('createdAt', -1))
        
        for patient in patients:
            patient['_id'] = str(patient.get('_id', ''))
        
        return jsonify({
            'success': True,
            'patients': patients,
            'count': len(patients)
        })
    except Exception as e:
        print(f"Error fetching patients: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/patients', methods=['POST'])
@token_required
def create_user_patient():
    """Create a new patient for the logged-in user"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        data = request.get_json()
        
        # Add user_id to the patient data
        data['user_id'] = g.user_id
        
        # Check if patient with mobile_number already exists for this user
        existing = db.patients.find_one({
            'mobile_number': data.get('mobile_number'),
            'user_id': g.user_id
        })
        
        if existing:
            # Update existing patient
            data['updatedAt'] = datetime.utcnow()
            db.patients.update_one(
                {'mobile_number': data.get('mobile_number'), 'user_id': g.user_id},
                {'$set': data}
            )
            return jsonify({
                'success': True,
                'message': 'Patient updated successfully',
                'mobile_number': data.get('mobile_number')
            })
        
        # Create new patient
        data['createdAt'] = datetime.utcnow()
        data['updatedAt'] = datetime.utcnow()
        
        result = db.patients.insert_one(data)
        
        return jsonify({
            'success': True,
            'message': 'Patient created successfully',
            'patient_id': str(result.inserted_id)
        })
    except Exception as e:
        print(f"Error creating patient: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/vitals', methods=['GET'])
@token_required
def get_user_vitals():
    """Get vitals history for the logged-in user"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        vitals = list(db.vitals.find({'user_id': g.user_id}).sort('timestamp', -1))
        
        for vital in vitals:
            vital['_id'] = str(vital.get('_id', ''))
        
        return jsonify({
            'success': True,
            'vitals': vitals,
            'count': len(vitals)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/vitals', methods=['POST'])
@token_required
def create_user_vital():
    """Create a new vital sign record for the logged-in user"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        data = request.get_json()
        
        # Add user_id to the vital data
        data['user_id'] = g.user_id
        data['timestamp'] = datetime.utcnow()
        
        result = db.vitals.insert_one(data)
        
        return jsonify({
            'success': True,
            'message': 'Vitals recorded successfully',
            'vital_id': str(result.inserted_id)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/stats', methods=['GET'])
@token_required
def get_user_stats():
    """Get statistics for the logged-in user"""
    if not mongo_connected:
        return jsonify({'success': False, 'error': 'MongoDB not connected'}), 500
    
    try:
        total_patients = db.patients.count_documents({'user_id': g.user_id})
        total_vitals = db.vitals.count_documents({'user_id': g.user_id})
        
        return jsonify({
            'success': True,
            'stats': {
                'total_patients': total_patients,
                'total_vitals': total_vitals
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==================== REGISTER V2 BLUEPRINTS ====================
# Register before app.run so routes exist in local dev mode and WSGI.
try:
    if PROD_MODULES_AVAILABLE:
        app.register_blueprint(auth_bp)
        app.register_blueprint(chat_bp)
except Exception as e:
    print(f"⚠️  Blueprint registration warning: {e}")


# ==================== MAIN ====================
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🏥 MedCare AI - Local ML Backend Server")
    print("="*60)
    
    # Initialize models
    initialize_chatbot()
    initialize_disease_predictor()
    
    # Initialize new ML services (production inference)
    if ML_SERVICES_AVAILABLE:
        print("\n🧠 Initializing production ML services...")
        init_inference()
        print("✅ ML Inference engine initialized")
    else:
        print("\n⚠️  ML services not available - using fallback model")
    
    print("\n" + "="*60)
    print(f"🚀 Server starting on http://localhost:{PORT}")
    print("📋 Endpoints:")
    print(f"   - Chatbot: POST http://localhost:{PORT}/api/chatbot")
    print(f"   - Analyze: POST http://localhost:{PORT}/api/analyze")
    print(f"   - Health:  GET  http://localhost:{PORT}/api/analyze/health")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=PORT, debug=True)

