import pandas as pd
import os
from typing import Dict, List, Any

DATA_DIR = '../backend/data'

def load_lookup_data() -> Dict[str, Any]:
    """Load all lookup CSV data into dicts."""
    lookups = {}
    
    # Precautions
    df_prec = pd.read_csv(f'{DATA_DIR}/disease_precaution.csv')
    prec_dict = {}
    for _, row in df_prec.iterrows():
        disease = row['Disease']
        precs = [row[f'Precaution_{i}'] for i in range(1, 5) if pd.notna(row[f'Precaution_{i}'])]
        prec_dict[disease] = precs
    lookups['precautions'] = prec_dict
    
    # Risk factors
    df_risk = pd.read_csv(f'{DATA_DIR}/disease_riskFactors.csv')
    risk_dict = {}
    for _, row in df_risk.iterrows():
        disease = row['DNAME']
        risks = f"{row['RISKFAC']} (Occurrence: {row['OCCUR']})"
        if disease not in risk_dict:
            risk_dict[disease] = []
        risk_dict[disease].append(risks)
    lookups['risk_factors'] = risk_dict
    
    # Medicines
    df_med = pd.read_csv(f'{DATA_DIR}/disease_medicine.csv')
    med_dict = {}
    for _, row in df_med.iterrows():
        disease = row['Disease_ID']  # Assume mapped
        if disease not in med_dict:
            med_dict[disease] = []
        med_dict[disease].append({
            'name': row['Medicine_Name'],
            'desc': row['Medicine_Description']
        })
    lookups['medicines'] = med_dict
    
    return lookups

def get_recommendations(disease: str, lookups: Dict) -> Dict[str, List]:
    \"\"\"Get all recommendations for a disease.\"\"\"
    return {
        'precautions': lookups['precautions'].get(disease, []),
        'risk_factors': lookups['risk_factors'].get(disease, []),
        'medicines': lookups['medicines'].get(disease, [])
    }

