"""FireSafe backend: data access, evidence retrieval, predictors, advisor and agent.

Every number the app shows comes from these modules, never from the LLM.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"
MODEL_DIR = ROOT / "model"
