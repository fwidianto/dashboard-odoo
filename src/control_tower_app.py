"""Entrypoint FastAPI yang menambahkan Control Tower API tanpa mengubah app lama.

Jalankan:
    python -m uvicorn src.control_tower_app:app --host 127.0.0.1 --port 8000
"""

from src.api import app
from src.control_tower.router import router as control_tower_router


app.include_router(control_tower_router)
