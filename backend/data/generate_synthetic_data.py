import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
import joblib

# Load original
df = pd.read_csv('disease_symptoms.csv')
print('Original shape:', df.shape)
print('Symptom cols:', [c for c in df.columns if c.startswith('Symptom_')])

symptom_cols = [col for col in df.columns if col.startswith('Symptom_')]
for col in symptom_cols:
    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(1.0).astype(float)
n_symptoms = len(symptom_cols)
le = LabelEncoder()
y_encoded = le.fit_transform(df['Disease'])

synthetic_df = pd.DataFrame()
synthetic_dfs = []

for disease_idx, disease_name in enumerate(le.classes_):
    # Get samples for this disease
    disease_mask = df['Disease'] == disease_name
    disease_df = df[disease_mask]
    n_original = len(disease_df)
    
    # Generate 100 synthetic per disease
    for _ in range(100):
        # Base sample
        base_row = disease_df.iloc[0]
        
        # Add noise: flip 0→1 (20% rare symptoms) or 1→0 (10% miss)
        row = base_row.copy()
        symp_binary = row[symptom_cols].values.astype(float)
        
        # Flip positions
        flip_probs = np.random.random(n_symptoms)
        for i in range(n_symptoms):
            if symp_binary[i] == 0 and flip_probs[i] < 0.2:  # Rare symptom
                symp_binary[i] = 1
            elif symp_binary[i] == 1 and flip_probs[i] < 0.1:  # Miss symptom
                symp_binary[i] = 0
        
        row[symptom_cols] = symp_binary
        synthetic_dfs.append(row)

synthetic_df = pd.concat(synthetic_dfs, ignore_index=True)
print('Synthetic shape:', synthetic_df.shape)

if 'Disease' not in synthetic_df.columns:
    disease_col = []
    for row in synthetic_dfs:
        disease_col.append(row['Disease'].iloc[0])
    synthetic_df.insert(1, 'Disease', disease_col)
    print('Added missing Disease column')

synthetic_df.to_csv('disease_symptoms_synthetic.csv', index=False)
print('✅ Saved backend/data/disease_symptoms_synthetic.csv (1000+ rows)')
print('Diseases:', synthetic_df['Disease'].nunique())

