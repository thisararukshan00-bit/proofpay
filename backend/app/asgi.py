"""Entry point for uvicorn: `uvicorn app.asgi:app --reload --port 8000`."""
import logging

from .main import create_app

logging.basicConfig(level=logging.INFO)
app = create_app()
