"""Entry point: ``python -m app``."""

import uvicorn

from app.server import create_app
from app.settings import BIND_HOST, Settings

settings = Settings.from_env()
uvicorn.run(create_app(settings), host=BIND_HOST, port=settings.port, log_level="info")
