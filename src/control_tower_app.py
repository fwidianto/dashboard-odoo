"""Entrypoint kompatibel untuk aplikasi FastAPI kanonis.

Jalankan:
    python -m uvicorn src.control_tower_app:app --host 127.0.0.1 --port 8000
"""

from src.api import app
