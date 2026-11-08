"""Entry point: ``python -m app`` (AGENT_PROTOCOL=http|a2a)."""

from app.settings import BIND_HOST, Settings

settings = Settings.from_env()
if settings.protocol == "a2a":
    from app.a2a_main import main

    main(settings)
else:
    from app.main import create_app

    create_app(settings).run(host=BIND_HOST, port=settings.port)
