from pathlib import Path

F29 = Path(__file__).resolve().parent
WORKSPACE = F29.parents[3]
MODELS = F29 / "models"
CONFIG = F29 / "config"
DATA = F29 / "data"
