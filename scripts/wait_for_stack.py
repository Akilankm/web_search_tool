from __future__ import annotations

import os
import time
import urllib.error
import urllib.request


url = os.getenv("PRODUCT_AGENT_URL", f"http://127.0.0.1:{os.getenv('AGENT_HOST_PORT', '8788')}/health")
deadline = time.monotonic() + float(os.getenv("STACK_STARTUP_TIMEOUT_SECONDS", "180"))
last_error: Exception | None = None
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if 200 <= response.status < 300:
                print(response.read().decode("utf-8"))
                raise SystemExit(0)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        last_error = exc
    time.sleep(3)
raise SystemExit(f"Stack did not become healthy: {last_error}")
