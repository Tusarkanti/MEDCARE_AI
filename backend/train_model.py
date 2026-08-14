"""
Legacy entry point — delegates to train_ensemble_models (unified multi-CSV training).

Run from backend/:   python train_model.py
"""

import os
import sys

# Run as script from backend/
if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    from train_ensemble_models import train_and_save_models

    train_and_save_models()
