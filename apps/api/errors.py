"""Typed error objects, with the same codes the CLI reports (section 14)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lab_domain.errors import LabError, NotFoundError, StateStoreError

STATUS_BY_ERROR: dict[type[LabError], int] = {
    NotFoundError: 404,
    StateStoreError: 500,
}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(LabError)
    async def handle(request: Request, error: LabError) -> JSONResponse:
        status = next(
            (code for kind, code in STATUS_BY_ERROR.items() if isinstance(error, kind)),
            400,
        )
        return JSONResponse(
            status_code=status,
            content={"status": "error", "code": error.code, "message": str(error)},
        )
