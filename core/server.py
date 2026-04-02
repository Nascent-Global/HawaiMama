from __future__ import annotations

import uvicorn

from traffic_monitoring.server import app


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        timeout_keep_alive=1,
        timeout_graceful_shutdown=1,
    )
