"""
PredictionService - Disease prediction service layer
====================================================
Coordinates between data preprocessing and ML inference.
Handles symptom normalization, patient context, and response formatting.
"""

import numpy as np
from ml.inference import get_inference


class PredictionService:
    """Service layer for disease prediction"""
    
    def __init__(self):
        self.inference = get_inference()
    
    def predict_from_symptoms(self, symptom_list, patient_info=None, top_k=3):
        """
        Predict disease from list of symptoms.
        
        Args:
            symptom_list: List of symptom names/descriptions
            patient_info: Dict with age, gender, risk_factors, etc.
            top_k: Number of top predictions to return
            
        Returns:
            dict with structured prediction result
        """
        if not self.inference.is_loaded:
            return {
                'success': False,
                'error': 'ML model not loaded',
                'predictions': []
            }
        
        try:
            # Create symptom vector from recognized symptoms
            symptom_vector = np.zeros(len(self.inference.get_all_symptoms()))
            recognized_symptoms = []
            unrecognized_symptoms = []
            
            for symptom in symptom_list:
                idx = self.inference.get_symptom_index(symptom)
                if idx is not None:
                    symptom_vector[idx] = 1
                    recognized_symptoms.append(symptom)
                else:
                    unrecognized_symptoms.append(symptom)
            
            # Run inference
            result = self.inference.predict(symptom_vector, top_k=top_k)
            
            # Add patient context if available
            if result['success'] and patient_info:
                risk_level = self._calculate_risk_level(result['predictions'], patient_info)
                result['risk_level'] = risk_level
                result['patient_context'] = {
                    'age': patient_info.get('age'),
                    'gender': patient_info.get('gender'),
                    'risk_factors': patient_info.get('risk_factors', [])
                }
            
            # Add symptom analysis
            result['symptoms_analyzed'] = {
                'total': len(symptom_list),
                'recognized': len(recognized_symptoms),
                'unrecognized': len(unrecognized_symptoms),
                'recognized_list': sorted(list(set(recognized_symptoms))),
                'unrecognized_list': sorted(list(set(unrecognized_symptoms)))
            }
            
            return result
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Prediction service error: {str(e)}',
                'predictions': []
            }
    
    def _calculate_risk_level(self, predictions, patient_info):
        """Calculate overall risk level based on predictions and patient context"""
        if not predictions:
            return 'unknown'
        
        top_confidence = predictions[0]['confidence']
        age = patient_info.get('age', 0)
        risk_factors = patient_info.get('risk_factors', [])
        
        # Simple risk scoring
        risk_score = top_confidence / 100
        
        # Age risk factor (higher risk for very young or very old)
        if age < 5 or age > 75:
            risk_score += 0.1
        elif age < 18 or age > 65:
            risk_score += 0.05
        
        # Risk factors multiplier
        risk_score += len(risk_factors) * 0.05
        
        # Classify risk level
        if risk_score > 0.7:
            return 'high'
        elif risk_score > 0.5:
            return 'moderate'
        elif risk_score > 0.3:
            return 'low'
        else:
            return 'minimal'
    
    def get_disease_recommendations(self, disease_name):
        """Get recommendations for a specific disease"""
        recommendations = {
            'Fever': [
                'Stay hydrated with water, herbal tea, or warm broth',
                'Rest and avoid strenuous activities',
                'Monitor temperature regularly',
                'Use acetaminophen or ibuprofen if needed',
                'Consult a doctor if fever exceeds 103°F or persists > 3 days'
            ],
            'Cough': [
                'Stay hydrated',
                'Use a humidifier to ease congestion',
                'Honey can help soothe throat (not for children < 1 year)',
                'Avoid irritants like smoke or strong perfumes',
                'Seek medical help if cough is severe or persistent'
            ],
            'Headache': [
                'Rest in a quiet, dark room',
                'Stay hydrated',
                'Use cold compress on forehead',
                'Over-the-counter pain relievers may help',
                'Consult doctor if severe or accompanied by vision changes'
            ],
            'Chest Pain': [
                '⚠️ SEEK IMMEDIATE MEDICAL CARE if severe',
                'Rest and avoid exertion',
                'Elevate upper body if possible',
                'Monitor vital signs',
                'Call emergency services if pain worsens'
            ]
        }
        
        return recommendations.get(disease_name, ['Consult a healthcare professional'])
    
    def validate_symptoms(self, symptom_list):
        """Validate and report on symptom list"""
        all_symptoms = self.inference.get_all_symptoms()
        recognized = []
        unrecognized = []
        
        for symptom in symptom_list:
            if self.inference.get_symptom_index(symptom) is not None:
                recognized.append(symptom)
            else:
                unrecognized.append(symptom)
        
        return {
            'total': len(symptom_list),
            'recognized_count': len(recognized),
            'unrecognized_count': len(unrecognized),
            'recognized': recognized,
            'unrecognized': unrecognized,
            'recognition_rate': round(len(recognized) / len(symptom_list) * 100, 2) if symptom_list else 0
        }
