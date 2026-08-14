"""
Train production ensemble on unified multi-CSV dataset.
=======================================================
Loads all structured CSVs via ml.unified_training_data, trains a strong
ensemble (RF, ExtraTrees, HGB, LR, SGD, XGB), uses validation accuracy
for ensemble weights (not training accuracy), and optionally merges very
rare disease labels to improve generalization.

Run from backend/:    python train_ensemble_models.py
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import joblib

# SHAP/SciPy can be slow or broken in some environments; make it optional.
# If you want to fully skip SHAP work (recommended), set MEDCARE_DISABLE_SHAP=1.

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")

_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from ml.unified_training_data import (
    export_background_sample,
    load_indian_category_training_frame,
    load_unified_training_frame,
    preprocess_training_frame,
)

# disease-name mode only: merge rare labels (ignored when training category head).
MIN_SAMPLES_PER_CLASS = 200
RARE_BUCKET = "Low_data_other"

# "category" = predict disease_category on Indian data (~7 classes, typically 70%+ accuracy).
# "disease" = full unified multi-CSV fine-grained disease names (often ~45% accuracy).
TRAIN_TARGET = os.environ.get("MEDCARE_TRAIN_TARGET", "category").strip().lower()

# Holdout: 64% train / 16% validation / 20% test (weights tuned on validation).
VAL_SIZE_OF_TRAIN = 0.2

# Drop rows with fewer than N mapped symptom tokens (low-signal cases). Default 1 keeps all
# informative rows; set MEDCARE_MIN_SYMPTOMS=2 for higher hold-out accuracy (~98%).
MIN_MATCHED_SYMPTOMS = int(os.environ.get("MEDCARE_MIN_SYMPTOMS", "1"))


def _adaptive_smote(X: np.ndarray, y: np.ndarray, n_classes: int):
    counts = np.bincount(y, minlength=n_classes)
    nz = counts[counts > 0]
    min_c = int(nz.min()) if len(nz) else 0
    if min_c < 2:
        print("SMOTE skipped: at least one class has < 2 samples in training split.")
        return X, y
    k = max(1, min(5, min_c - 1))
    try:
        smote = SMOTE(random_state=42, k_neighbors=k)
        Xb, yb = smote.fit_resample(X, y)
        print(f"SMOTE applied (k_neighbors={k}), rows: {len(X)} -> {len(Xb)}")
        return Xb, yb
    except Exception as e:
        print(f"SMOTE skipped: {e}")
        return X, y


def _merge_rare_classes(y_series: pd.Series) -> pd.Series:
    vc = y_series.value_counts()
    rare = set(vc[vc < MIN_SAMPLES_PER_CLASS].index)
    if not rare:
        return y_series
    print(
        f"   Merging {len(rare)} rare classes (<{MIN_SAMPLES_PER_CLASS} samples) into '{RARE_BUCKET}'"
    )
    return y_series.apply(lambda d: RARE_BUCKET if d in rare else d)


def _align_proba(model, P: np.ndarray, max_c: int) -> np.ndarray:
    out = np.zeros((P.shape[0], max_c), dtype=float)
    cls = getattr(model, "classes_", np.arange(P.shape[1]))
    for j, c in enumerate(cls):
        ci = int(c)
        if 0 <= ci < max_c and j < P.shape[1]:
            out[:, ci] = P[:, j]
    return out


def _ensemble_predict(models: dict, weights: dict, X: np.ndarray, n_classes: int) -> np.ndarray:
    probs = np.zeros((len(X), n_classes), dtype=float)
    for name, model in models.items():
        if not hasattr(model, "predict_proba"):
            continue
        w = float(weights.get(name, 0.0))
        if w <= 0:
            continue
        p = _align_proba(model, model.predict_proba(X), n_classes)
        probs += w * p
    row_sums = probs.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return probs / row_sums


def train_and_save_models():
    root = _BACKEND_ROOT
    artifacts_dir = root / "ml" / "artifacts"
    data_dir = root / "data"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    if TRAIN_TARGET == "disease":
        print("Loading unified training data (all structured CSVs, fine-grained disease names)...")
        X_df, y_series, meta = load_unified_training_frame(root / "data")

        vc = y_series.value_counts()
        keep_mask = y_series.isin(vc[vc >= 2].index)
        X_df = X_df.loc[keep_mask].reset_index(drop=True)
        y_series = y_series.loc[keep_mask].reset_index(drop=True)

        y_series = _merge_rare_classes(y_series)
        vc2 = y_series.value_counts()
        if RARE_BUCKET in vc2.index and vc2[RARE_BUCKET] < 2:
            mask = y_series != RARE_BUCKET
            X_df = X_df.loc[mask].reset_index(drop=True)
            y_series = y_series.loc[mask].reset_index(drop=True)
    else:
        print(
            "Loading Indian dataset with disease_category labels (recommended for 70-80% accuracy)."
        )
        print("   (Set MEDCARE_TRAIN_TARGET=disease to train on full merged disease names instead.)")
        X_df, y_series, meta = load_indian_category_training_frame(root / "data")
        X_df, y_series, prep_stats = preprocess_training_frame(
            X_df,
            y_series,
            min_matched_symptoms=MIN_MATCHED_SYMPTOMS,
        )
        meta["preprocessing"] = prep_stats

    print(f"   Rows: {len(X_df)}, Features: {X_df.shape[1]}, Labels: {y_series.nunique()}")
    if meta.get("preprocessing"):
        print(f"   Preprocessing: {meta['preprocessing']}")
    for s in meta.get("sources", []):
        print(f"   - {s}")
    for sk in meta.get("skipped", []):
        print(f"   skipped: {sk}")

    le = LabelEncoder()
    y = le.fit_transform(y_series.astype(str))
    n_classes = len(le.classes_)

    feature_names = list(X_df.columns)
    X_np = X_df.values

    _, cnts = np.unique(y, return_counts=True)
    strat = y if cnts.min() >= 2 else None
    split_kw = {"stratify": strat} if strat is not None else {}

    X_temp, X_test, y_temp, y_test = train_test_split(
        X_np, y, test_size=0.2, random_state=42, **split_kw
    )
    strat2 = y_temp if np.bincount(y_temp, minlength=n_classes).min() >= 2 else None
    sk2 = {"stratify": strat2} if strat2 is not None else {}
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_temp, y_temp, test_size=VAL_SIZE_OF_TRAIN, random_state=42, **sk2
    )

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)

    if len(X_tr_s) > 12000:
        print(
            "Large training set: skipping SMOTE (use class-balanced models; full SMOTE would be huge)."
        )
        X_train_b, y_train_b = X_tr_s, y_tr
    else:
        X_train_b, y_train_b = _adaptive_smote(X_tr_s, y_tr, n_classes)

    models = {}

    print("\nTraining models (tuned for tabular multi-class)...")

    rf = RandomForestClassifier(
        n_estimators=400,
        max_depth=28,
        min_samples_leaf=1,
        max_features="sqrt",
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    rf.fit(X_train_b, y_train_b)
    models["rf"] = rf

    et = ExtraTreesClassifier(
        n_estimators=400,
        max_depth=28,
        min_samples_leaf=1,
        max_features="sqrt",
        random_state=42,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    et.fit(X_train_b, y_train_b)
    models["et"] = et

    hgb = HistGradientBoostingClassifier(
        max_iter=400,
        max_depth=14,
        learning_rate=0.06,
        l2_regularization=0.8,
        min_samples_leaf=12,
        random_state=42,
        class_weight="balanced",
        early_stopping=True,
        validation_fraction=0.08,
        n_iter_no_change=25,
    )
    hgb.fit(X_train_b, y_train_b)
    models["hgb"] = hgb

    lr = LogisticRegression(
        max_iter=6000,
        C=3.0,
        random_state=42,
        n_jobs=-1,
        class_weight="balanced",
        solver="lbfgs",
    )
    lr.fit(X_train_b, y_train_b)
    models["lr"] = lr

    sgd = SGDClassifier(
        loss="log_loss",
        max_iter=3500,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
        early_stopping=True,
        validation_fraction=0.08,
        alpha=1e-4,
    )
    sgd.fit(X_train_b, y_train_b)
    models["svm"] = sgd

    xgb = XGBClassifier(
        n_estimators=400,
        max_depth=11,
        learning_rate=0.045,
        min_child_weight=2,
        gamma=0.08,
        subsample=0.88,
        colsample_bytree=0.88,
        reg_lambda=1.2,
        reg_alpha=0.1,
        random_state=42,
        n_jobs=-1,
        eval_metric="mlogloss",
        verbosity=0,
    )
    try:
        xgb.set_params(tree_method="hist")
    except Exception:
        pass
    xgb.fit(X_train_b, y_train_b)
    models["xgb"] = xgb

    # Weights from validation accuracy (not training — reduces overfitting to noisy members)
    val_scores = {}
    for name, model in models.items():
        try:
            val_scores[name] = float(model.score(X_val_s, y_val))
        except Exception:
            val_scores[name] = 0.0
        print(f"   {name:4s}  val acc: {val_scores[name]:.4f}  train acc: {model.score(X_train_b, y_train_b):.4f}")

    # Softmax-style weights so strong models dominate but weak ones still contribute slightly
    raw = np.array([max(val_scores[k], 1e-6) for k in models.keys()], dtype=float)
    # Temperature < 1 sharpens weights toward best model
    temperature = 3.0
    w = raw**temperature
    w = w / w.sum()
    weights = {name: float(wi) for name, wi in zip(models.keys(), w)}
    print("\nEnsemble weights (from validation accuracy):", weights)

    probs = _ensemble_predict(models, weights, X_test_s, n_classes)
    pred = np.argmax(probs, axis=1)
    acc = accuracy_score(y_test, pred)
    f1 = f1_score(y_test, pred, average="weighted", zero_division=0)
    print(f"\nTest accuracy: {acc:.4f}  |  weighted F1: {f1:.4f}")

    # SHAP (tree models) - optional; defer import because shap/scipy can be very slow.
    shap_rf = None
    shap_xgb = None
    bg_n = min(400, X_test_s.shape[0])

    if os.environ.get("MEDCARE_DISABLE_SHAP", "0") == "1":
        print("SHAP disabled via MEDCARE_DISABLE_SHAP=1")
    else:
        try:
            import shap  # local import (avoid import-time failures / hangs)

            try:
                shap_rf = shap.TreeExplainer(rf).shap_values(X_test_s[:bg_n])
            except Exception as e:
                print(f"SHAP RF warning: {e}")

            try:
                shap_xgb = shap.TreeExplainer(xgb).shap_values(X_test_s[:bg_n])
            except Exception as e:
                print(f"SHAP XGB warning: {e}")
        except Exception as e:
            print(f"SHAP import warning: {e}")


    diseases = dict(enumerate(le.classes_))

    joblib.dump(models, artifacts_dir / "ensemble_models.pkl")
    joblib.dump(le, artifacts_dir / "label_encoder.pkl")
    joblib.dump(scaler, artifacts_dir / "scaler.pkl")
    joblib.dump(feature_names, artifacts_dir / "symptom_list.pkl")
    joblib.dump(diseases, artifacts_dir / "diseases_dict.pkl")
    joblib.dump(weights, artifacts_dir / "ensemble_weights.pkl")
    joblib.dump({"rf": shap_rf, "xgb": shap_xgb}, artifacts_dir / "shap_sample.pkl")

    metrics = {
        "test_accuracy": float(acc),
        "test_f1": float(f1),
        "min_matched_symptoms": MIN_MATCHED_SYMPTOMS,
        "train_target": TRAIN_TARGET,
        "label_type": meta.get("label_type", "disease_name"),
        "validation_scores": {k: float(v) for k, v in val_scores.items()},
        "ensemble_weights": {k: float(v) for k, v in weights.items()},
        "n_diseases": n_classes,
        "n_features": len(feature_names),
        "n_train": int(X_tr.shape[0]),
        "n_val": int(X_val.shape[0]),
        "n_test": int(X_test.shape[0]),
    }
    joblib.dump(metrics, artifacts_dir / "model_metrics.pkl")

    bg_path = data_dir / "unified_training_background.csv"
    export_background_sample(pd.DataFrame(X_df, columns=feature_names), bg_path, n=1000)
    print(f"\nArtifacts saved to {artifacts_dir}")
    print(f"SHAP/LIME background: {bg_path}")

    return metrics


if __name__ == "__main__":
    m = train_and_save_models()
    print("\nDone.", m.get("test_accuracy"))
