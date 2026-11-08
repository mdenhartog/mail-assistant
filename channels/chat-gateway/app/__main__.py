"""Entry point: ``python -m app``."""

import uvicorn

from app.main import create_app_from_env
from app.settings import BIND_HOST, Settings

uvicorn.run(create_app_from_env(), host=BIND_HOST, port=Settings.from_env().port, log_level="info", proxy_headers=True)
