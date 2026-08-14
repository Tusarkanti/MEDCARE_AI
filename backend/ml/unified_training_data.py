"""
Build a single training matrix from all structured CSV files under backend/data/.

- disease_symptoms.csv: primary symptom tokens + binary flags
- indian_diseases_dataset.csv: disease_name + symptoms text → multi-hot over shared vocabulary
- vitamin_deficiency_* .csv: disease_diagnosis + binary symptom flags + key numerics
- heart.csv: heart disease labels + numeric features (appended columns)
- disease_medicine / disease_precaution / disease_riskFactors: merged counts per disease name
- train.csv: unstructured Q&A — not used for supervised symptom matrix (logged only)

Feature names are stable strings so inference + SHAP use the same ordering.
"""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "data"


def normalize_symptom_token(s: object) -> str:
    """Public: same normalization used when building training columns and at inference."""
    return _norm_symptom(s)


def _norm_symptom(s: object) -> str:
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    t = str(s).strip().lower()
    if not t or t in ("0", "1", "nan", "none"):
        return ""
    t = re.sub(r"\s+", "_", t)
    t = re.sub(r"[^a-z0-9_]", "", t)
    return t


def _collect_tokens_from_disease_symptoms(df: pd.DataFrame) -> List[str]:
    tok: Set[str] = set()
    for col in df.columns:
        if not str(col).startswith("Symptom_"):
            continue
        for v in df[col]:
            if isinstance(v, str) and not v.strip().isdigit():
                n = _norm_symptom(v)
                if n:
                    tok.add(n)
            else:
                try:
                    float(v)
                except (TypeError, ValueError):
                    n = _norm_symptom(v)
                    if n:
                        tok.add(n)
    return sorted(tok)


def _row_tokens_disease_symptoms(row: pd.Series, symptom_cols: List[str]) -> Set[str]:
    out: Set[str] = set()
    for c in symptom_cols:
        v = row.get(c)
        if pd.isna(v):
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if float(v) >= 0.5:
                out.add(str(c).lower())  # flag column fires as synthetic token name
            continue
        n = _norm_symptom(v)
        if n:
            out.add(n)
    return out


def _match_tokens_from_text(text: str, vocab: List[str]) -> Set[str]:
    if not text or not isinstance(text, str):
        return set()
    text_l = text.lower()
    found: Set[str] = set()
    for t in vocab:
        if len(t) >= 3 and t in text_l.replace(" ", "_"):
            found.add(t)
        elif len(t) < 3 and re.search(r"\b" + re.escape(t) + r"\b", text_l):
            found.add(t)
    # also split indian style "Fever, Body ache"
    for part in re.split(r"[,;]", text_l):
        part = part.strip()
        p = _norm_symptom(part)
        if p in vocab:
            found.add(p)
    return found


def _normalize_disease_name(s: object) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return "unknown"
    t = str(s).strip()
    t = re.sub(r"\s+", " ", t)
    return t


def load_unified_training_frame(
    data_dir: Optional[Path] = None,
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, object]]:
    """
    Returns:
      X: feature DataFrame (numeric 0/1 + scaled numerics)
      y: disease label strings
      meta: dict with vocab, feature lists, skip notes
    """
    root = data_dir or _data_dir()
    meta: Dict[str, object] = {"sources": [], "skipped": []}

    # ---------- disease_symptoms.csv ----------
    path_ds = root / "disease_symptoms.csv"
    if not path_ds.exists():
        raise FileNotFoundError(f"Required file missing: {path_ds}")

    df_ds = pd.read_csv(path_ds)
    vocab = _collect_tokens_from_disease_symptoms(df_ds)
    symptom_cols = [c for c in df_ds.columns if str(c).startswith("Symptom_")]

    token_to_i = {t: i for i, t in enumerate(vocab)}
    n_tok = len(vocab)

    def empty_X(n_rows: int) -> pd.DataFrame:
        # Column per vocabulary token (same names used at inference for matching)
        return pd.DataFrame(0.0, index=range(n_rows), columns=list(vocab))

    y_ds = []
    Xb = empty_X(len(df_ds))
    for i in range(len(df_ds)):
        row = df_ds.iloc[i]
        y_ds.append(_normalize_disease_name(row.get("Disease")))
        toks = _row_tokens_disease_symptoms(row, symptom_cols)
        for t in toks:
            if t in token_to_i:
                Xb.iat[i, token_to_i[t]] = 1.0

    X_parts = [Xb]
    y_parts = [pd.Series(y_ds, name="Disease")]
    src_parts = [pd.Series(["disease_symptoms"] * len(y_ds), name="source")]

    meta["sources"].append(f"disease_symptoms.csv ({len(df_ds)} rows)")
    meta["vocab_size"] = n_tok

    # ---------- Lookup: medicine / precaution / risk (by disease name) ----------
    med_counts: Dict[str, int] = {}
    prec_counts: Dict[str, int] = {}
    risk_counts: Dict[str, int] = {}

    pm = root / "disease_medicine.csv"
    if pm.exists():
        dm = pd.read_csv(pm)
        if "Disease_ID" in dm.columns:
            for _, r in dm.iterrows():
                d = _normalize_disease_name(r["Disease_ID"])
                med_counts[d] = med_counts.get(d, 0) + 1
        meta["sources"].append("disease_medicine.csv (lookup)")

    pp = root / "disease_precaution.csv"
    if pp.exists():
        dp = pd.read_csv(pp)
        if "Disease" in dp.columns:
            for _, r in dp.iterrows():
                d = _normalize_disease_name(r["Disease"])
                prec_counts[d] = sum(
                    1 for c in dp.columns
                    if c.startswith("Precaution_") and pd.notna(r.get(c)) and str(r.get(c)).strip()
                )
        meta["sources"].append("disease_precaution.csv (lookup)")

    pr = root / "disease_riskFactors.csv"
    if pr.exists():
        with open(pr, newline="", encoding="utf-8") as fh:
            reader = csv.reader(fh)
            next(reader, None)  # header
            for row in reader:
                if len(row) < 5:
                    continue
                d = _normalize_disease_name(row[1])
                risk_counts[d] = max(0, len(row) - 4)
        meta["sources"].append("disease_riskFactors.csv (lookup)")

    def lookup_features(labels: List[str]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "meta_n_medicines": [med_counts.get(_normalize_disease_name(l), 0) for l in labels],
                "meta_n_precautions": [prec_counts.get(_normalize_disease_name(l), 0) for l in labels],
                "meta_n_risk_factors": [risk_counts.get(_normalize_disease_name(l), 0) for l in labels],
            }
        )

    meta_cols = lookup_features(y_ds)
    X_parts[0] = pd.concat([X_parts[0].reset_index(drop=True), meta_cols], axis=1)

    # ---------- indian_diseases_dataset.csv ----------
    ind_path = root / "indian_diseases_dataset.csv"
    if ind_path.exists():
        ind = pd.read_csv(ind_path, low_memory=False)
        n = len(ind)
        Xi = empty_X(n)
        yi = []
        si = []
        for i, row in ind.iterrows():
            dis = _normalize_disease_name(row.get("disease_name", row.get("Disease", "unknown")))
            yi.append(dis)
            si.append("indian_diseases")
            st = row.get("symptoms", "")
            if pd.notna(st):
                for t in _match_tokens_from_text(str(st), vocab):
                    Xi.iat[i, token_to_i[t]] = 1.0
        Xi_meta = lookup_features(yi)
        X_parts.append(pd.concat([Xi.reset_index(drop=True), Xi_meta], axis=1))
        y_parts.append(pd.Series(yi))
        src_parts.append(pd.Series(si))
        meta["sources"].append(f"indian_diseases_dataset.csv ({n} rows)")

    # ---------- vitamin deficiency dataset ----------
    vit_path = list(root.glob("vitamin_deficiency*.csv"))
    vit_path = vit_path[0] if vit_path else None
    if vit_path and vit_path.exists():
        vit = pd.read_csv(vit_path)
        n = len(vit)
        Xv = empty_X(n)
        yv = []
        sv = []
        has_cols = [c for c in vit.columns if str(c).startswith("has_")]
        for i, row in vit.iterrows():
            dis = _normalize_disease_name(row.get("disease_diagnosis", "unknown"))
            yv.append(dis)
            sv.append("vitamin")
            for c in has_cols:
                try:
                    if float(row.get(c, 0)) >= 0.5:
                        cn = _norm_symptom(c.replace("has_", ""))
                        if cn in token_to_i:
                            Xv.iat[i, token_to_i[cn]] = 1.0
                except (TypeError, ValueError):
                    pass
            sl = row.get("symptoms_list", "")
            if pd.notna(sl) and str(sl).lower() not in ("none", "nan", ""):
                for t in _match_tokens_from_text(str(sl).replace(";", ","), vocab):
                    Xv.iat[i, token_to_i[t]] = 1.0
        # numeric context (scaled later in training script)
        for col in ("bmi", "symptoms_count", "hemoglobin_g_dl"):
            if col in vit.columns:
                Xv[f"ext_{col}"] = pd.to_numeric(vit[col], errors="coerce").fillna(0.0).values
        Xv_meta = lookup_features(yv)
        Xv = pd.concat([Xv.reset_index(drop=True), Xv_meta], axis=1)
        X_parts.append(Xv)
        y_parts.append(pd.Series(yv))
        src_parts.append(pd.Series(sv))
        meta["sources"].append(f"{vit_path.name} ({n} rows)")

    # ---------- heart.csv (binary HD) ----------
    hp = root / "heart.csv"
    if hp.exists():
        hd = pd.read_csv(hp)
        n = len(hd)
        Xh = empty_X(n)
        # map heart columns into ext_* only (no symptom tokens unless we add synonyms)
        label_col = "Heart Disease" if "Heart Disease" in hd.columns else hd.columns[-1]
        yh = []
        sh = []
        for i, row in hd.iterrows():
            raw = str(row[label_col]).strip().lower()
            yh.append("Heart_Disease_Presence" if "presence" in raw or raw in ("1", "true", "yes") else "Heart_Disease_Absence")
            sh.append("heart")
        num_cols = [c for c in hd.columns if c != label_col]
        for c in num_cols:
            Xh[f"ext_{c}"] = pd.to_numeric(hd[c], errors="coerce").fillna(0.0).values
        Xh_meta = lookup_features(yh)
        Xh = pd.concat([Xh.reset_index(drop=True), Xh_meta], axis=1)
        X_parts.append(Xh)
        y_parts.append(pd.Series(yh))
        src_parts.append(pd.Series(sh))
        meta["sources"].append(f"heart.csv ({n} rows)")

    # ---------- train.csv: skip with note ----------
    tp = root / "train.csv"
    if tp.exists():
        try:
            tt = pd.read_csv(tp, nrows=5)
            meta["skipped"].append(
                f"train.csv ({sum(1 for _ in open(tp, 'rb'))} lines): columns {list(tt.columns)} - Q&A text, not merged into symptom matrix"
            )
        except OSError:
            meta["skipped"].append("train.csv: could not inspect")

    # ---------- align columns across parts ----------
    all_cols: List[str] = []
    for part in X_parts:
        all_cols.extend([c for c in part.columns if c not in all_cols])

    def align(df: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame(0.0, index=range(len(df)), columns=all_cols)
        for c in df.columns:
            if c in out.columns:
                out[c] = df[c].values
        return out

    X_aligned = [align(p) for p in X_parts]
    X_full = pd.concat(X_aligned, axis=0, ignore_index=True)
    y_full = pd.concat(y_parts, axis=0, ignore_index=True)
    src_full = pd.concat(src_parts, axis=0, ignore_index=True)

    meta["feature_columns"] = list(X_full.columns)
    meta["vocab"] = vocab
    meta["n_rows"] = len(X_full)
    meta["source_series"] = src_full
    meta["label_type"] = "disease_name"

    return X_full, y_full, meta


def load_indian_category_training_frame(
    data_dir: Optional[Path] = None,
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, object]]:
    """
    High-accuracy pipeline: single clean source (Indian hospital-style rows) with
    label = disease_category (e.g. Vector-Borne, Infectious). Typically reaches
    much higher hold-out accuracy than merging all CSVs with fine-grained disease names.
    """
    root = data_dir or _data_dir()
    meta: Dict[str, object] = {
        "sources": [],
        "skipped": [],
        "label_type": "disease_category",
    }

    path_ds = root / "disease_symptoms.csv"
    if not path_ds.exists():
        raise FileNotFoundError(f"Required file missing: {path_ds}")
    df_ds = pd.read_csv(path_ds)
    vocab = _collect_tokens_from_disease_symptoms(df_ds)
    token_to_i = {t: i for i, t in enumerate(vocab)}

    ind_path = root / "indian_diseases_dataset.csv"
    if not ind_path.exists():
        raise FileNotFoundError(f"Required for category training: {ind_path}")

    ind = pd.read_csv(ind_path, low_memory=False)
    n = len(ind)
    X = pd.DataFrame(0.0, index=range(n), columns=list(vocab))

    for i, row in ind.iterrows():
        st = row.get("symptoms", "")
        if pd.notna(st):
            for t in _match_tokens_from_text(str(st), vocab):
                X.iat[i, token_to_i[t]] = 1.0

    X["ext_age"] = pd.to_numeric(ind["age"], errors="coerce")
    X["ext_bmi"] = pd.to_numeric(ind["bmi"], errors="coerce")
    if "days_hospitalized" in ind.columns:
        X["ext_days_hospitalized"] = pd.to_numeric(ind["days_hospitalized"], errors="coerce").fillna(0)
    if "treatment_cost_inr" in ind.columns:
        X["ext_log_cost"] = np.log1p(
            pd.to_numeric(ind["treatment_cost_inr"], errors="coerce").fillna(0).clip(lower=0)
        )

    X["ext_age"] = X["ext_age"].fillna(X["ext_age"].median())
    X["ext_bmi"] = X["ext_bmi"].fillna(X["ext_bmi"].median())

    for col, prefix in (
        ("gender", "g"),
        ("region", "r"),
        ("urban_rural", "u"),
        ("severity", "sev"),
        ("season", "season"),
    ):
        if col not in ind.columns:
            continue
        dummies = pd.get_dummies(ind[col].fillna("unk").astype(str), prefix=prefix)
        for c in dummies.columns:
            if c not in X.columns:
                X[c] = dummies[c].values

    y = ind["disease_category"].astype(str)
    meta["sources"].append(f"indian_diseases_dataset.csv ({n} rows), y=disease_category")
    meta["vocab"] = vocab
    meta["feature_columns"] = list(X.columns)
    meta["n_rows"] = len(X)

    tp = root / "train.csv"
    if tp.exists():
        meta["skipped"].append(
            "train.csv: Q&A text not used (same as unified pipeline)"
        )

    return X, y, meta


def preprocess_training_frame(
    X_df: pd.DataFrame,
    y_series: pd.Series,
    *,
    min_matched_symptoms: int = 1,
    drop_duplicates: bool = True,
    add_engineered_features: bool = True,
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, object]]:
    """
    Clean and enrich the Indian category training matrix.

    - Removes exact duplicate rows
    - Fills numeric NaNs with column medians
    - Adds symptom_count / symptom_density / age_bmi features
    - Optionally drops low-signal rows with fewer than ``min_matched_symptoms`` tokens
    """
    stats: Dict[str, object] = {
        "rows_in": int(len(X_df)),
        "min_matched_symptoms": int(min_matched_symptoms),
    }

    X_df = X_df.copy()
    y_series = y_series.copy().reset_index(drop=True)
    X_df = X_df.reset_index(drop=True)

    if drop_duplicates:
        combo = pd.concat([X_df, y_series.rename("_y")], axis=1)
        combo = combo.drop_duplicates()
        X_df = combo.drop(columns=["_y"]).reset_index(drop=True)
        y_series = combo["_y"].reset_index(drop=True)
        stats["rows_after_dedup"] = int(len(X_df))

    meta_prefixes = ("ext_", "g_", "r_", "u_", "sev_", "season_")
    sym_cols = [c for c in X_df.columns if not any(c.startswith(p) for p in meta_prefixes)]

    for col in X_df.select_dtypes(include=[np.number]).columns:
        med = X_df[col].median()
        X_df[col] = X_df[col].fillna(med if pd.notna(med) else 0.0)

    if add_engineered_features:
        scount = (X_df[sym_cols] > 0).sum(axis=1)
        X_df["symptom_count"] = scount
        X_df["symptom_density"] = scount / max(len(sym_cols), 1)
        if "ext_age" in X_df.columns and "ext_bmi" in X_df.columns:
            X_df["age_bmi"] = X_df["ext_age"] * X_df["ext_bmi"]
        stats["engineered_features"] = ["symptom_count", "symptom_density", "age_bmi"]

    if min_matched_symptoms > 0 and sym_cols:
        scount = (X_df[sym_cols] > 0).sum(axis=1)
        keep = scount >= min_matched_symptoms
        X_df = X_df.loc[keep].reset_index(drop=True)
        y_series = y_series.loc[keep].reset_index(drop=True)
        stats["rows_after_symptom_filter"] = int(len(X_df))

    stats["rows_out"] = int(len(X_df))
    return X_df, y_series, stats


def export_background_sample(
    X: pd.DataFrame,
    path: Path,
    n: int = 800,
) -> None:
    """Save a stratified random sample for SHAP/LIME background (JSON-friendly path)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(X) <= n:
        X.to_csv(path, index=False)
        return
    X.sample(n=min(n, len(X)), random_state=42).to_csv(path, index=False)
