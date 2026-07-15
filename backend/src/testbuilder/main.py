from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import create_all

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        await create_all()  # zero-setup dev; Postgres uses Alembic
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exc(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": str(exc.detail)}
        return JSONResponse(
            status_code=exc.status_code, content={"data": None, "error": detail}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        from fastapi.encoders import jsonable_encoder

        return JSONResponse(
            status_code=422,
            content={
                "data": None,
                "error": {
                    "code": "validation_error",
                    "details": jsonable_encoder(
                        exc.errors(), custom_encoder={ValueError: str}
                    ),
                },
            },
        )

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok"}

    from .api.routes import (
        admin_users,
        assessments,
        assignments,
        audit,
        auth,
        candidate_auth,
        code,
        evaluations,
        exam,
        proctoring,
        questions,
        reports,
        timer_ws,
    )

    prefix = "/api/v1"
    app.include_router(auth.router, prefix=prefix)
    app.include_router(auth.unified_router, prefix=prefix)
    app.include_router(admin_users.router, prefix=prefix)
    app.include_router(audit.router, prefix=prefix)
    app.include_router(questions.router, prefix=prefix)
    app.include_router(assessments.router, prefix=prefix)
    app.include_router(assessments.section_router, prefix=prefix)
    app.include_router(assignments.router, prefix=prefix)
    app.include_router(candidate_auth.router, prefix=prefix)
    app.include_router(exam.router, prefix=prefix)
    app.include_router(code.router, prefix=prefix)
    app.include_router(proctoring.router, prefix=prefix)
    app.include_router(evaluations.router, prefix=prefix)
    app.include_router(reports.router, prefix=prefix)
    app.include_router(timer_ws.router, prefix=prefix)
    return app


app = create_app()
