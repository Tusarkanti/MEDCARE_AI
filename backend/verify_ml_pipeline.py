"""
End-to-end verification for MEDCARE ML training, metrics, diagrams, and inference.
Run: python verify_ml_pipeline.py
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import joblib
import numpy as np

_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

OUTPUT_DIR = _BACKEND / "ml_evaluation_outputs"
ARTIFACTS = _BACKEND / "ml" / "artifacts"

REQUIRED_PNGS = [
    "improved_accuracy_curve.png",
    "improved_loss_curve.png",
    "improved_roc_curve.png",
    "improved_confusion_matrix.png",
    "improved_precision_recall_curve.png",
]
REQUIRED_TXT = ["classification_report.txt", "final_model_metrics.txt"]
ZIP_NAME = "final_ml_outputs.zip"

THRESHOLDS = {
    "accuracy": 0.97,
    "precision": 0.97,
    "recall": 0.97,
    "f1": 0.97,
    "roc_auc": 0.98,
}


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    msg = f"  [{mark}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return ok


def verify_outputs() -> bool:
    all_ok = True
    print("\n=== Output files ===")
    for fn in REQUIRED_PNGS:
        p = OUTPUT_DIR / fn
        ok = p.is_file() and p.stat().st_size > 5000
        all_ok &= check(fn, ok, f"{p.stat().st_size:,} bytes" if ok else "missing or too small")

    for fn in REQUIRED_TXT:
        p = OUTPUT_DIR / fn
        ok = p.is_file() and p.stat().st_size > 100
        all_ok &= check(fn, ok, f"{p.stat().st_size:,} bytes" if ok else "missing or too small")

    zp = OUTPUT_DIR / ZIP_NAME
    zip_ok = zp.is_file() and zp.stat().st_size > 10000
    all_ok &= check(ZIP_NAME, zip_ok, f"{zp.stat().st_size:,} bytes" if zip_ok else "missing")

    if zip_ok:
        with zipfile.ZipFile(zp, "r") as zf:
            names = set(zf.namelist())
        for fn in REQUIRED_PNGS + REQUIRED_TXT:
            all_ok &= check(f"zip contains {fn}", fn in names)

    # PNG readable
    try:
        from PIL import Image

        for fn in REQUIRED_PNGS:
            img = Image.open(OUTPUT_DIR / fn)
            w, h = img.size
            all_ok &= check(f"{fn} opens", w >= 400 and h >= 300, f"{w}x{h}")
    except ImportError:
        print("  [SKIP] PIL not installed — PNG pixel check skipped")
    except Exception as e:
        all_ok &= check("PNG validation", False, str(e))

    return all_ok


def verify_metrics() -> bool:
    print("\n=== Metrics thresholds ===")
    all_ok = True
    mp = ARTIFACTS / "model_metrics.pkl"
    if not mp.exists():
        return check("model_metrics.pkl", False, "not found")

    m = joblib.load(mp)
    # train_ensemble_models.pkl uses test_accuracy; evaluation script uses accuracy
    alias = {
        "accuracy": ("accuracy", "test_accuracy"),
        "precision": ("precision", "test_precision"),
        "recall": ("recall", "test_recall"),
        "f1": ("f1", "test_f1"),
        "roc_auc": ("roc_auc", "test_roc_auc"),
    }
    for key, min_val in THRESHOLDS.items():
        val = 0.0
        for k in alias.get(key, (key, f"test_{key}")):
            if k in m:
                val = float(m[k])
                break
        if val == 0.0 and key == "f1" and "test_f1" in m:
            val = float(m["test_f1"])
        if val == 0.0 and key in ("precision", "recall", "roc_auc"):
            # Parse from final_model_metrics.txt when train script saved partial metrics
            txt = (OUTPUT_DIR / "final_model_metrics.txt")
            if txt.is_file():
                for line in txt.read_text(encoding="utf-8").splitlines():
                    if line.lower().startswith(key.replace("_", " ") + ":") or (
                        key == "roc_auc" and "ROC AUC:" in line
                    ):
                        try:
                            val = float(line.split(":")[1].strip().split()[0])
                        except (IndexError, ValueError):
                            pass
        ok = val >= min_val
        all_ok &= check(f"{key} >= {min_val:.2f}", ok, f"{val:.4f}")

    txt = (OUTPUT_DIR / "final_model_metrics.txt").read_text(encoding="utf-8")
    all_ok &= check("final_model_metrics.txt readable", "Accuracy:" in txt and "98" in txt.split("Accuracy:")[1][:12])

    report = (OUTPUT_DIR / "classification_report.txt").read_text(encoding="utf-8")
    all_ok &= check("classification_report.txt", "precision" in report and "accuracy" in report)

    return all_ok


def verify_inference() -> bool:
    print("\n=== Runtime inference ===")
    all_ok = True
    try:
        from ml.inference import MLInference

        inf = MLInference(str(ARTIFACTS))
        loaded = inf.load_artifacts()
        all_ok &= check("MLInference.load_artifacts()", loaded, inf.error_msg or "ok")

        if loaded:
            vec = np.zeros(len(inf.symptom_list), dtype=float)
            for name in ("fever", "cough", "fatigue", "headache"):
                idx = inf.get_symptom_index(name)
                if idx is not None:
                    vec[idx] = 1.0
            matched = int(vec.sum())
            all_ok &= check("symptom token mapping", matched >= 1, f"{matched} features set")
            result = inf.predict(vec, top_k=3)
            top = result.get("predictions", [{}])[0].get("disease", "") if result.get("predictions") else ""
            all_ok &= check(
                "predict() returns results",
                result.get("success") and len(result.get("predictions", [])) > 0,
                top[:60],
            )
    except Exception as e:
        all_ok &= check("MLInference", False, str(e))
    return all_ok


def verify_artifacts() -> bool:
    print("\n=== Artifacts ===")
    all_ok = True
    for fn in [
        "ensemble_models.pkl",
        "label_encoder.pkl",
        "scaler.pkl",
        "symptom_list.pkl",
        "diseases_dict.pkl",
        "ensemble_weights.pkl",
        "model_metrics.pkl",
    ]:
        p = ARTIFACTS / fn
        all_ok &= check(fn, p.is_file() and p.stat().st_size > 100)
    return all_ok


def main() -> int:
    print("MEDCARE ML Pipeline Verification")
    print(f"Backend: {_BACKEND}")
    results = [
        verify_artifacts(),
        verify_outputs(),
        verify_metrics(),
        verify_inference(),
    ]
    ok = all(results)
    print("\n" + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
