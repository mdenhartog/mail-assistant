# chat-gateway (messaging gateway: Telegram and WhatsApp)

Receives webhooks from Telegram and/or WhatsApp, checks that they are genuine, and hands the text to an agent (`AGENT_BACKEND=http` for an agent in this project or elsewhere, `agentcore` for an agent on AWS AgentCore Runtime). The answer goes back to the same chat.

| Channel | Switch on with | Authenticity | Who may talk to the agent |
|---|---|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET` (16+ chars `A-Za-z0-9_-`) | secret token header (`X-Telegram-Bot-Api-Secret-Token`) | `TELEGRAM_ALLOWED_CHAT_IDS` |
| WhatsApp | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | HMAC-SHA256 of the raw body (`X-Hub-Signature-256`) | `WHATSAPP_ALLOWED_NUMBERS` |

The gateway sends `AGENT_TOKEN` as a bearer token: set it to the agent's `AGENT_AUTH_TOKEN`.

A channel without an allow-list is refused at startup: otherwise anyone who finds the bot could use (and pay for) your agent.

**Register the webhook** (the gateway must be reachable over public HTTPS; for a local test use a tunnel such as `cloudflared tunnel --url http://localhost:8300`):

- Telegram: `https://api.telegram.org/bot<token>/setWebhook` with `url=https://<host>/telegram/webhook` and `secret_token=<TELEGRAM_WEBHOOK_SECRET>`.
- WhatsApp: in the Meta app dashboard set the callback URL `https://<host>/whatsapp/webhook` and the verify token.

Test: `uv run pytest` (no network) · run: `uv run python -m app` · image: `docker build .`.
