"""Retrain both predictors and rewrite model/metrics.json.

Run from the repository root:  .venv/bin/python model/train.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firesafe.predictor import train_all  # noqa: E402

if __name__ == "__main__":
    m = train_all()
    for key in ("solid", "flex"):
        print(f"\n== {key}: n={m[key]['n_observations']} classes={m[key]['class_counts']} ({m[key]['validation']})")
        for row in m[key]["comparison"]:
            print(f"  {row['model']:<66} log_loss={row['log_loss']:.3f} brier={row['brier']:.3f} "
                  f"auc={row['roc_auc']} bal_acc={row['balanced_accuracy']:.3f}")
