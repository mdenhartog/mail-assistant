"""Container health check: ``python -m app.healthcheck``."""

import os
import sys
import urllib.request

HTTP_OK = 200
URL = f"http://127.0.0.1:{os.environ.get('PORT', '8000')}/ping"
with urllib.request.urlopen(URL, timeout=3) as response:  # nosec B310
    sys.exit(0 if response.status == HTTP_OK else 1)
