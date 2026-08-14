"""
MLInference - Load and run trained ensemble models
===================================================
Loads pre-trained RF/LR/SVM/XGB models from artifacts.
Handles feature scaling, ensemble voting, and confidence scoring.
"""

import joblib
import numpy as np
import warnings
import os
from pathlib import Path

warnings.filterwarnings('ignore')


class MLInference:
    """Production inference engine for disease prediction ensemble"""
    
    def __init__(self, artifacts_dir='backend/ml/artifacts'):
        """
        Initialize inference engine with pre-trained artifacts.
        
        Args:
            artifacts_dir: Path to saved model artifacts
        """
        self.artifacts_dir = artifacts_dir
        self.models = {}
        self.label_encoder = None
        self.scaler = None
        self.symptom_list = []
        self.weights = {}
        self.diseases_dict = {}
        self.is_loaded = False
        self.error_msg = None
        
    def load_artifacts(self):
        """Load pre-trained models and supporting artifacts"""
        try:
            # Build artifact paths - handle relative paths
            if not os.path.isabs(self.artifacts_dir):
                # Make relative path relative to this file's directory (backend/ml/)
                current_dir = os.path.dirname(os.path.abspath(__file__))
                self.artifacts_dir = os.path.join(current_dir, 'artifacts')
            ensemble_path = os.path.join(self.artifacts_dir, 'ensemble_models.pkl')
            encoder_path = os.path.join(self.artifacts_dir, 'label_encoder.pkl')
            scaler_path = os.path.join(self.artifacts_dir, 'scaler.pkl')
            symptoms_path = os.path.join(self.artifacts_dir, 'symptom_list.pkl')
            weights_path = os.path.join(self.artifacts_dir, 'ensemble_weights.pkl')
            diseases_path = os.path.join(self.artifacts_dir, 'diseases_dict.pkl')
            
            # Check if artifacts exist
            missing = []
            for path, name in [
                (ensemble_path, 'ensemble_models.pkl'),
                (encoder_path, 'label_encoder.pkl'),
                (scaler_path, 'scaler.pkl'),
                (symptoms_path, 'symptom_list.pkl'),
                (weights_path, 'ensemble_weights.pkl'),
                (diseases_path, 'diseases_dict.pkl')
            ]:
                if not os.path.exists(path):
                    missing.append(name)
            
            if missing:
                self.error_msg = f"Missing artifacts: {', '.join(missing)}. Run train_model.py first."
                print(f"WARN: {self.error_msg}")
                return False
            
            # Load artifacts
            self.models = joblib.load(ensemble_path)
            self.label_encoder = joblib.load(encoder_path)
            self.scaler = joblib.load(scaler_path)
            self.symptom_list = joblib.load(symptoms_path)
            self.weights = joblib.load(weights_path)
            self.diseases_dict = joblib.load(diseases_path)
            
            self.is_loaded = True
            
            # Log loaded models
            model_names = list(self.models.keys())
            print(f"ML Inference Engine loaded: {', '.join(model_names)}")
            print(f"{len(self.diseases_dict)} diseases, {len(self.symptom_list)} features")
            print(f"Ensemble weights: {self.weights}")
            
            return True
            
        except Exception as e:
            self.is_loaded = False
            self.error_msg = f"Failed to load artifacts: {str(e)}"
            print(f"ERROR: {self.error_msg}")
            return False
    
    def predict(self, symptom_vector, top_k=3):
        """
        Run ensemble prediction on symptom vector.
        
        Args:
            symptom_vector: Binary vector of symptoms [0/1, 0/1, ...]
            top_k: Return top K predictions
            
        Returns:
            dict with predictions, probabilities, and metadata
        """
        if not self.is_loaded:
            return {
                'success': False,
                'error': self.error_msg or 'Model not loaded',
                'predictions': []
            }
        
        try:
            # Convert to numpy array if needed
            symptom_vector = np.array(symptom_vector, dtype=float).reshape(1, -1)
            
            # Validate input shape
            if symptom_vector.shape[1] != len(self.symptom_list):
                return {
                    'success': False,
                    'error': f'Expected {len(self.symptom_list)} symptoms, got {symptom_vector.shape[1]}',
                    'predictions': []
                }
            
            # Scale features
            symptom_scaled = self.scaler.transform(symptom_vector)
            
            # Ensemble prediction: weighted average of probabilities
            ensemble_proba = np.zeros((1, len(self.diseases_dict)))
            
            n_cls = len(self.diseases_dict)
            for model_name, model in self.models.items():
                if hasattr(model, 'predict_proba'):
                    raw = model.predict_proba(symptom_scaled)[0]
                    aligned = np.zeros(n_cls, dtype=float)
                    classes = getattr(model, "classes_", np.arange(len(raw)))
                    for j, c in enumerate(classes):
                        ci = int(c)
                        if 0 <= ci < n_cls and j < len(raw):
                            aligned[ci] = raw[j]
                    weight = self.weights.get(model_name, 0.25)
                    ensemble_proba[0] += weight * aligned
                    # print(f"  {model_name}: {weight:.2f} weight")
            
            # Normalize ensemble probabilities
            ensemble_proba = ensemble_proba[0] / ensemble_proba[0].sum()
            
            # Get top-k predictions
            top_indices = np.argsort(ensemble_proba)[::-1][:top_k]
            
            predictions = []
            for idx in top_indices:
                disease_idx = int(idx)
                disease_name = self.diseases_dict.get(disease_idx, f'Disease_{disease_idx}')
                confidence = float(ensemble_proba[disease_idx])
                
                predictions.append({
                    'disease': disease_name,
                    'confidence': round(confidence * 100, 2),
                    'probability': round(confidence, 4)
                })
            
            return {
                'success': True,
                'predictions': predictions,
                'top_confidence': round(float(ensemble_proba[top_indices[0]]) * 100, 2),
                'ensemble_weights': self.weights,
                'models_used': list(self.models.keys())
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Prediction failed: {str(e)}',
                'predictions': []
            }
    
    def get_symptom_index(self, symptom_name):
        """Map symptom name to feature vector index"""
        try:
            return self.symptom_list.index(symptom_name)
        except ValueError:
            pass
        try:
            from ml.unified_training_data import normalize_symptom_token

            key = normalize_symptom_token(symptom_name)
            return self.symptom_list.index(key)
        except ValueError:
            return None
    
    def get_all_symptoms(self):
        """Return list of all recognized symptoms"""
        return self.symptom_list.copy()
    
    def get_all_diseases(self):
        """Return list of all diseases"""
        return list(self.diseases_dict.values())


# Global singleton inference engine
_inference_engine = None


def init_inference(artifacts_dir='backend/ml/artifacts'):
    """Initialize global inference engine"""
    global _inference_engine
    _inference_engine = MLInference(artifacts_dir)
    _inference_engine.load_artifacts()
    return _inference_engine


def get_inference():
    """Get global inference engine (initialize if needed)"""
    global _inference_engine
    if _inference_engine is None:
        init_inference()
    return _inference_engine
