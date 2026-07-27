"""The platform's HTTP interface (AGENTS.md section 14).

Read-only on purpose. Every write the platform performs — submitting a run,
publishing a component, promoting one — changes a laboratory's record or
spends its cluster time, and the platform has no authorization model yet
(section 15). Exposing those over unauthenticated HTTP would be the wrong kind
of convenient, so the API reports and the CLI acts (ADR 0011).

Routes are thin: they read through the same stores and services the CLI uses.
"""

from __future__ import annotations

from fastapi import FastAPI

from api.errors import install_error_handlers
from api.routes import artifacts, backends, components, projects, runs

API_VERSION = "v1"
TITLE = "Research Execution Platform"

app = FastAPI(
    title=TITLE,
    version=API_VERSION,
    summary="Read access to what the platform has recorded.",
)

install_error_handlers(app)
for router in (
    projects.router,
    runs.router,
    components.router,
    artifacts.router,
    backends.router,
):
    app.include_router(router, prefix=f"/{API_VERSION}")


@app.get("/health", tags=["service"])
def health() -> dict[str, str]:
    return {"status": "ok", "api_version": API_VERSION}
