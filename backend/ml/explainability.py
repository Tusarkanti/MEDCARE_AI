"""
Explainability utilities (SHAP global + LIME local)
===================================================
Provides explainability for the production ensemble in `ml.inference.MLInference`.

Design goals:
- Avoid heavy compute by caching explainers/background data
- Work even when training artifacts are missing (return structured errors)
- Keep outputs JSON-friendly for frontend consumption
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _load_background_matrix(
    csv_path: str,
    feature_names: List[str],
    max_rows: int = 500,
) -> np.ndarray:
    """
    Load a background dataset aligned to `feature_names`.
    Uses numeric conversion on columns in the CSV; missing columns become 0.
    """
    df = pd.read_csv(csv_path)

    # Convert any Symptom_* columns to numeric where possible.
    symptom_cols = [c for c in df.columns if str(c).startswith("Symptom_")]
    for c in symptom_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    X = pd.DataFrame(index=df.index)
    for f in feature_names:
        if f in df.columns:
            X[f] = df[f].fillna(0)
        else:
            X[f] = 0

    # Ensure integer-ish / finite
    X = X.replace([np.inf, -np.inf], 0).fillna(0)
    X = X.astype(float)

    if len(X) > max_rows:
        X = X.sample(n=max_rows, random_state=42)

    return X.to_numpy(dtype=float)


def _ensemble_predict_proba(inference, X_scaled: np.ndarray) -> np.ndarray:
    """
    Return ensemble probabilities for a batch of rows in scaled feature space.
    Mirrors `MLInference.predict` logic but vectorized.
    """
    if not inference.is_loaded:
        raise RuntimeError(inference.error_msg or "Model not loaded")

    n_classes = len(inference.diseases_dict)
    proba = np.zeros((X_scaled.shape[0], n_classes), dtype=float)

    for model_name, model in inference.models.items():
        if not hasattr(model, "predict_proba"):
            continue
        w = inference.weights.get(model_name, 0.25)
        raw = model.predict_proba(X_scaled)
        p = np.zeros((raw.shape[0], n_classes), dtype=float)
        classes = getattr(model, "classes_", np.arange(raw.shape[1]))
        for j, c in enumerate(classes):
            ci = int(c)
            if 0 <= ci < n_classes and j < raw.shape[1]:
                p[:, ci] = raw[:, j]
        proba += w * p

    row_sums = proba.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    return proba / row_sums


@dataclass
class ExplainabilityService:
    inference: Any
    background_raw: Optional[np.ndarray] = None
    background_scaled: Optional[np.ndarray] = None
    lime_explainer: Optional[Any] = None
    shap_explainers: Optional[Dict[str, Any]] = None

    def ensure_background(self, csv_path: str) -> None:
        if self.background_raw is not None and self.background_scaled is not None:
            return
        feats = self.inference.get_all_symptoms()
        self.background_raw = _load_background_matrix(csv_path, feats, max_rows=600)
        self.background_scaled = self.inference.scaler.transform(self.background_raw)

    def ensure_lime(self, csv_path: str) -> None:
        if self.lime_explainer is not None:
            return
        self.ensure_background(csv_path)
        from lime.lime_tabular import LimeTabularExplainer

        class_names = [str(x) for x in self.inference.get_all_diseases()]
        self.lime_explainer = LimeTabularExplainer(
            training_data=self.background_scaled,
            feature_names=self.inference.get_all_symptoms(),
            class_names=class_names,
            mode="classification",
            discretize_continuous=False,
            random_state=42,
        )

    def ensure_shap(self, csv_path: str) -> None:
        if self.shap_explainers is not None:
            return
        self.ensure_background(csv_path)
        import shap

        explainers: Dict[str, Any] = {}
        # Prefer tree explainers for speed/quality if present
        for name in ("xgb", "rf", "hgb", "et"):
            model = self.inference.models.get(name)
            if model is None:
                continue
            try:
                explainers[name] = shap.TreeExplainer(model)
            except Exception:
                # Some model versions may require different SHAP setup; ignore gracefully.
                continue

        self.shap_explainers = explainers

    def explain_lime_local(
        self,
        symptom_vector_raw: np.ndarray,
        csv_path: str,
        top_k_features: int = 10,
    ) -> Dict[str, Any]:
        if not self.inference.is_loaded:
            return {"success": False, "error": self.inference.error_msg or "Model not loaded"}

        self.ensure_lime(csv_path)

        x_raw = np.array(symptom_vector_raw, dtype=float).reshape(1, -1)
        x_scaled = self.inference.scaler.transform(x_raw)

        probs = _ensemble_predict_proba(self.inference, x_scaled)[0]
        top_class = int(np.argmax(probs))

        def predict_fn(batch_scaled: np.ndarray) -> np.ndarray:
            return _ensemble_predict_proba(self.inference, batch_scaled)

        exp = self.lime_explainer.explain_instance(
            data_row=x_scaled[0],
            predict_fn=predict_fn,
            num_features=int(top_k_features),
            top_labels=1,
        )

        # LIME returns feature "Symptom_X <= 0.00" style strings.
        local = exp.as_list(label=top_class)
        contributions = [{"feature": f, "weight": _safe_float(w)} for f, w in local]

        return {
            "success": True,
            "top_class_index": top_class,
            "top_class_name": str(self.inference.diseases_dict.get(top_class, top_class)),
            "top_class_probability": _safe_float(probs[top_class]),
            "contributions": contributions,
        }

    def shap_global_summary(
        self,
        csv_path: str,
        model_preference: Tuple[str, ...] = ("xgb", "rf", "hgb", "et"),
        max_background: int = 250,
        top_n: int = 20,
    ) -> Dict[str, Any]:
        if not self.inference.is_loaded:
            return {"success": False, "error": self.inference.error_msg or "Model not loaded"}

        self.ensure_shap(csv_path)
        if not self.shap_explainers:
            return {
                "success": False,
                "error": "No SHAP-compatible tree model loaded (expected rf/xgb).",
            }

        chosen_name = None
        for n in model_preference:
            if n in self.shap_explainers:
                chosen_name = n
                break
        if chosen_name is None:
            chosen_name = next(iter(self.shap_explainers.keys()))

        explainer = self.shap_explainers[chosen_name]
        X = self.background_scaled
        if X is None or len(X) == 0:
            return {"success": False, "error": "Background dataset not available"}

        Xs = X[: int(max_background)]

        # SHAP multi-class can return list[n_classes](n_samples, n_features) or array(n_samples, n_features, n_classes)
        shap_vals = explainer.shap_values(Xs)
        shap_arr: np.ndarray
        if isinstance(shap_vals, list):
            shap_arr = np.stack(shap_vals, axis=-1)  # (n, f, c)
        else:
            shap_arr = np.array(shap_vals)
            if shap_arr.ndim == 2:
                shap_arr = shap_arr[:, :, None]

        mean_abs = np.mean(np.abs(shap_arr), axis=(0, 2))  # (f,)
        feats = self.inference.get_all_symptoms()
        order = np.argsort(mean_abs)[::-1][: int(top_n)]

        items = [{"feature": feats[i], "importance": _safe_float(mean_abs[i])} for i in order]

        return {
            "success": True,
            "model_used": chosen_name,
            "n_background": int(Xs.shape[0]),
            "top_features": items,
        }

