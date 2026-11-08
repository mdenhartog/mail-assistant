"""Test settings: the agent refuses to start without an auth mode, so tests run in development mode with auth off."""

DEV = {"AGENT_AUTH_MODE": "off", "APP_ENVIRONMENT": "development"}
