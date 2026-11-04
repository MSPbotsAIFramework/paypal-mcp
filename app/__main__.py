"""Entry point: `python -m app` starts the HTTP server (SOP S8 Dockerfile CMD)."""

from __future__ import annotations

import uvicorn

from app.server import create_app
from app.settings import settings


def main() -> None:
    app = create_app()
    uvicorn.run(app, host=settings.mcp_http_host, port=settings.mcp_http_port)


if __name__ == "__main__":
    main()
