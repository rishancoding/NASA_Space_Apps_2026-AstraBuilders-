"""Load backend-only local settings without replacing deployment environment variables."""
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_environment() -> bool:
    # Resolve against this module so startup does not depend on the shell's cwd.
    return load_dotenv(ENV_FILE, override=False)
