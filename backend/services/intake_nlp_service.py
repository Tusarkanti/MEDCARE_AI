"""
IntakeNLPService - Structured medical intake NLP normalization
===============================================================
Parses free-text symptom descriptions, normalizes to canonical terms,
extracts risk factors, and structures intake data for inference.
"""

import re
from typing import List, Dict, Any


class IntakeNLPService:
    """NLP-based intake form normalization service"""
    
    # Symptom normalization mapping (free-text -> canonical)
    SYMPTOM_SYNONYMS = {
        'headache': ['headache', 'head pain', 'head ache', 'migraine', 'head hurts', 'throbbing head'],
        'fever': ['fever', 'high temperature', 'febrile', 'feeling hot', 'chills', 'high fever', 'elevated temp'],
        'cough': ['cough', 'coughing', 'persistent cough', 'dry cough', 'wet cough'],
        'sore_throat': ['sore throat', 'throat pain', 'throat ache', 'scratchy throat', 'throat irritation'],
        'runny_nose': ['runny nose', 'nasal congestion', 'congestion', 'stuffy nose', 'rhinorrhea'],
        'chest_pain': ['chest pain', 'severe chest pain', 'chest tightness', 'pressure in chest', 'chest discomfort'],
        'shortness_of_breath': ['shortness of breath', 'breathing difficulty', 'dyspnea', 'difficulty breathing', 'shortness breath'],
        'nausea': ['nausea', 'feeling sick', 'queasy', 'nauseated'],
        'vomiting': ['vomiting', 'throwing up', 'vomit'],
        'diarrhea': ['diarrhea', 'loose stools', 'frequent bowel movements', 'loose motions'],
        'constipation': ['constipation', 'difficulty defecating', 'hard stools'],
        'abdominal_pain': ['abdominal pain', 'stomach pain', 'belly pain', 'stomachache', 'stomach ache', 'stomach cramps'],
        'fatigue': ['fatigue', 'tiredness', 'exhaustion', 'lack of energy', 'tired', 'weak'],
        'weakness': ['weakness', 'muscle weakness', 'weak legs', 'leg weakness'],
        'joint_pain': ['joint pain', 'arthritis pain', 'joint ache', 'knee pain', 'back pain'],
        'muscle_pain': ['muscle pain', 'muscle ache', 'myalgia', 'body aches', 'muscle soreness'],
        'rash': ['rash', 'skin rash', 'hives', 'skin irritation', 'itchy rash'],
        'itching': ['itching', 'itchy', 'pruritus', 'scratching'],
        'dizziness': ['dizziness', 'dizzy', 'vertigo', 'lightheadedness', 'lightheaded'],
        'anxiety': ['anxiety', 'anxious', 'worry', 'worried', 'nervous'],
        'depression': ['depression', 'sad', 'sadness', 'depressed', 'low mood'],
        'insomnia': ['insomnia', 'sleep problem', 'difficulty sleeping', 'sleeplessness', 'cant sleep'],
        'confusion': ['confusion', 'confused', 'disorientation', 'brain fog'],
        'loss_of_taste': ['loss of taste', 'no taste', 'taste loss'],
        'loss_of_smell': ['loss of smell', 'no smell', 'smell loss', 'anosmia'],
    }
    
    # Risk factor keywords
    RISK_FACTORS = {
        'diabetes': ['diabetes', 'diabetic', 'blood sugar'],
        'hypertension': ['hypertension', 'high blood pressure', 'bp high'],
        'heart_disease': ['heart disease', 'heart condition', 'cardiac', 'coronary'],
        'asthma': ['asthma', 'asthmatic'],
        'copd': ['copd', 'chronic obstructive', 'emphysema', 'bronchitis'],
        'kidney_disease': ['kidney disease', 'renal failure', 'kidney problem'],
        'liver_disease': ['liver disease', 'hepatitis', 'cirrhosis'],
        'cancer': ['cancer', 'malignancy', 'oncology'],
        'obesity': ['obesity', 'obese', 'overweight', 'bmi'],
        'smoking': ['smoking', 'smoker', 'cigarettes'],
        'alcohol': ['alcohol', 'alcoholic', 'drinking'],
        'immunocompromised': ['immunocompromised', 'immune system', 'weak immunity', 'HIV', 'AIDS'],
    }
    
    # Severity mapping
    SEVERITY_LEVELS = {
        'mild': ['mild', 'slight', 'minor', 'a little', 'small'],
        'moderate': ['moderate', 'medium', 'somewhat', 'fairly', 'considerable'],
        'severe': ['severe', 'intense', 'bad', 'terrible', 'very bad', 'extreme', 'extremely'],
        'critical': ['critical', 'life-threatening', 'emergency', 'unbearable']
    }
    
    # Duration patterns (returns days)
    DURATION_PATTERNS = [
        (r'(\d+)\s*(?:hours?|hrs?)', lambda m: int(m.group(1)) / 24),
        (r'(\d+)\s*(?:days?)', lambda m: int(m.group(1))),
        (r'(\d+)\s*(?:weeks?|wks?)', lambda m: int(m.group(1)) * 7),
        (r'(\d+)\s*(?:months?|yrs?)', lambda m: int(m.group(1)) * 30),
        (r'(?:since|for|past)\s+(?:today|1\s*day)', lambda m: 1),
        (r'(?:since|for|past)\s+(?:a\s+)?week', lambda m: 7),
    ]
    
    @classmethod
    def normalize_symptoms(cls, symptom_text: str) -> List[str]:
        """
        Parse free-text symptom description and return normalized symptom list.
        
        Args:
            symptom_text: Free-text symptom description
            
        Returns:
            List of normalized symptom names
        """
        if not symptom_text:
            return []
        
        text_lower = symptom_text.lower().strip()
        normalized = []
        
        # Check each symptom's synonyms
        for canonical, synonyms in cls.SYMPTOM_SYNONYMS.items():
            for synonym in synonyms:
                if synonym in text_lower:
                    normalized.append(canonical)
                    break  # Only add once per canonical symptom
        
        return list(set(normalized))  # Remove duplicates
    
    @classmethod
    def extract_risk_factors(cls, intake_text: str) -> List[str]:
        """
        Extract medical risk factors from intake free-text.
        
        Args:
            intake_text: Medical history or intake description
            
        Returns:
            List of identified risk factors
        """
        if not intake_text:
            return []
        
        text_lower = intake_text.lower().strip()
        extracted = []
        
        for factor_name, keywords in cls.RISK_FACTORS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    extracted.append(factor_name)
                    break
        
        return list(set(extracted))  # Remove duplicates
    
    @classmethod
    def extract_severity(cls, text: str) -> str:
        """
        Extract severity level from text.
        
        Args:
            text: Text describing symptom severity
            
        Returns:
            Severity level: 'critical', 'severe', 'moderate', 'mild', or 'unknown'
        """
        if not text:
            return 'unknown'
        
        text_lower = text.lower().strip()
        
        # Check in order of severity
        for level in ['critical', 'severe', 'moderate', 'mild']:
            for keyword in cls.SEVERITY_LEVELS.get(level, []):
                if keyword in text_lower:
                    return level
        
        return 'unknown'
    
    @classmethod
    def extract_duration(cls, text: str) -> int:
        """
        Extract duration from text and return as days.
        
        Args:
            text: Text describing symptom duration
            
        Returns:
            Duration in days (int), or -1 if not found
        """
        if not text:
            return -1
        
        text_lower = text.lower().strip()
        
        for pattern, converter in cls.DURATION_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                try:
                    return int(converter(match))
                except:
                    continue
        
        return -1
    
    @classmethod
    def structure_intake_form(cls, form_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Structure and normalize intake form data.
        
        Args:
            form_data: Raw intake form data with keys:
                - symptom_description (str)
                - duration_text (str)
                - severity_text (str)
                - medical_history (str)
                - age (int)
                - gender (str)
                
        Returns:
            Structured intake record with normalized fields
        """
        symptom_text = form_data.get('symptom_description', '')
        duration_text = form_data.get('duration_text', '')
        severity_text = form_data.get('severity_text', '')
        medical_history = form_data.get('medical_history', '')
        
        return {
            'symptoms': cls.normalize_symptoms(symptom_text),
            'duration_days': cls.extract_duration(duration_text),
            'severity': cls.extract_severity(severity_text),
            'risk_factors': cls.extract_risk_factors(medical_history),
            'age': form_data.get('age'),
            'gender': form_data.get('gender'),
            'mobile_number': form_data.get('mobile_number'),
            'full_name': form_data.get('full_name'),
            'raw_text': {
                'symptoms': symptom_text,
                'duration': duration_text,
                'severity': severity_text,
                'medical_history': medical_history
            }
        }
    
    @classmethod
    def validate_intake(cls, structured_intake: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate structured intake record.
        
        Args:
            structured_intake: Structured intake data
            
        Returns:
            Validation result with is_valid flag and issues list
        """
        issues = []
        
        # Check required fields
        if not structured_intake.get('symptoms'):
            issues.append('No symptoms provided or recognized')
        
        if not structured_intake.get('age'):
            issues.append('Age is required')
        
        if not structured_intake.get('gender'):
            issues.append('Gender is required')
        
        # Warn if duration unknown
        if structured_intake.get('duration_days', -1) < 0:
            issues.append('Warning: Duration could not be parsed from text')
        
        # Warn if severity unknown
        if structured_intake.get('severity') == 'unknown':
            issues.append('Warning: Severity could not be determined from text')
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'warnings': [issue for issue in issues if 'Warning:' in issue],
            'errors': [issue for issue in issues if 'Warning:' not in issue]
        }
