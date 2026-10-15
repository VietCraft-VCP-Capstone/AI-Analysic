
import sys
import os

# Thêm đường dẫn app vào sys.path để import
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app.config import *  # noqa: F401, F403
