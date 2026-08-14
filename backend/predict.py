import numpy as np
import joblib
import flask
from flask import jsonify, request
from typing import List, Dict, Any, Tuple
from .utils import load_lookup_data, get_recommendations
import shap
import os
import warnings
warnings.filterwarnings('ignore')

MODEL_DIR = '../backend/model'
lookups = load_lookup_data()

# Global loaded models
models = None
le = None
scaler = None
symptom_list = None
weights = None
explainer_xgb = None
diseases_dict = None

def load_models():
    """Load trained models and artifacts."""
    global models, le, scaler, symptom_list, weights, explainer_xgb, diseases_dict
    models = joblib.load(f'{MODEL_DIR}/ensemble_models.pkl')
    le = joblib.load(f'{MODEL_DIR}/label_encoder.pkl')
    scaler = joblib.load(f'{MODEL_DIR}/scaler.pkl')
    symptom_list = joblib.load(f'{MODEL_DIR}/symptom_list.pkl')
    weights = joblib.load(f'{MODEL_DIR}/ensemble_weights.pkl')
    diseases_dict = joblib.load(f'{MODEL_DIR}/diseases_dict.pkl')
    explainer_xgb = shap.TreeExplainer(models['xgb'])
    print("✅ Models loaded successfully")
    return True

def symptom_vector(symptoms: List[str]) -> np.ndarray:
    """Convert symptoms to feature vector."""
    vec = np.zeros(len(symptom_list))
    for sym in symptoms:
        sym_norm = sym.lower().strip().replace(' ', '_').replace('-', '_')
        if sym_norm in symptom_list:
            idx = symptom_list.index(sym_norm)
            vec[idx] = 1
    return scaler.transform([vec])[0]

def predict(symptoms: List[str], patient_info: Dict = None) -> Dict[str, Any]:
    """Main prediction function."""
    vec = symptom_vector(symptoms)
    
    # Ensemble probs
    probs = np.zeros(len(le.classes_))
    for name, w in weights.items():
        model = models[name]
        probs += w * model.predict_proba([vec])[0]
    
    pred_idx = np.argmax(probs)
    disease = le.inverse_transform([pred_idx])[0]
    confidence = probs[pred_idx] * 100
    
    # SHAP explanation (top 5 features)
    shap_vec = explainer_xgb.shap_values([vec])
    feature_importance = np.abs(shap_vec[0]).argsort()[-5:][::-1]
    top_symptoms = [(symptom_list[i], shap_vec[0][i]) for i in feature_importance]
    
    recs = get_recommendations(disease, lookups)
    
    risk_level = 'High' if confidence > 80 else 'Medium' if confidence > 60 else 'Low'
    
    return {
        'predicted_disease': disease,
        'confidence': round(confidence, 2),
        'top_symptoms_influencing': top_symptoms,
        'risk_level': risk_level,
        'precautions': recs['precautions'],
        'risk_factors': recs['risk_factors'],
        'medicines': recs['medicines'],
        'explanation': f'This prediction is based on SHAP analysis showing {top_symptoms[0][0]} as the strongest influencing symptom.'
    }

# Flask endpoints
def predict_endpoint(app):
    @app.route('/api/predict', methods=['POST'])
    def api_predict():
        try:
            data = request.json
            symptoms = data.get('symptoms', [])
            patient_info = data.get('patient_info', {})
            if not symptoms:
                return jsonify({'error': 'No symptoms'}), 400
            result = predict(symptoms, patient_info)
            return jsonify({'success': True, **result})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    
    @app.route('/api/predict/health', methods=['GET'])
    def health():
        return jsonify({
            'status': 'healthy' if models else 'train_first',
            'diseases': len(le.classes_) if le else 0,
            'symptoms': len(symptom_list) if symptom_list else 0
        })
    
    return app

if __name__ == '__main__':
    load_models()

