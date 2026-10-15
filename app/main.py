"""
RailMate - FastAPI application factory.

Run locally from the project root:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.db import USER_SCHEMA, connect, init_schema
from app.middleware import RateLimitMiddleware, RequestContextMiddleware
from app.routers import auth, info, journeys, stations, trips
from app.services.delay_model import DelayModel
from app.services.helpdesk import HelpDesk
from app.services.timetable import Timetable

__version__ = "2.0.0"
log = logging.getLogger("railmate")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_schema(settings.user_db_path, USER_SCHEMA)
        app.state.timetable = Timetable()
        if settings.db_path.exists():
            conn = connect(settings.db_path)
            try:
                app.state.timetable = Timetable.from_db(conn)
            except Exception:
                log.exception("Could not read timetable database %s", settings.db_path)
            finally:
                conn.close()
        if not app.state.timetable.loaded:
            log.warning("Timetable is empty - run: python -m scripts.build_dataset")
        else:
            log.info("Timetable loaded: %d trains, %d stations",
                     len(app.state.timetable.trains), len(app.state.timetable.stations))
        app.state.delay_model = DelayModel(settings.model_path)
        app.state.helpdesk = HelpDesk(settings.faq_path)
        yield

    app = FastAPI(
        title="RailMate API",
        version=__version__,
        description="Train journey planner: direct and connecting journeys, explainable ranking, "
                    "delay-risk model, saved trips and a help desk.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.secret = settings.resolved_secret()

    # Middleware order: the last one added runs first
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(RateLimitMiddleware, per_minute=settings.rate_limit_per_minute)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["GET", "POST", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"])
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        # Friendly, flat error messages for the frontend
        messages = []
        for err in exc.errors():
            field = ".".join(str(p) for p in err.get("loc", [])[1:])
            msg = err.get("msg", "Invalid value").removeprefix("Value error, ")
            messages.append(f"{field}: {msg}" if field else msg)
        return JSONResponse({"detail": "; ".join(messages)}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception):
        log.exception("Unhandled error: %s", exc)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    for r in (info.router, stations.router, journeys.router, auth.router, trips.router):
        app.include_router(r)

    app.mount("/static", StaticFiles(directory=settings.frontend_dir), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(settings.frontend_dir / "index.html")

    return app


app = create_app()
