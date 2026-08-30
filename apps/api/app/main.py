from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  # register SQLAlchemy models before create_all
from app.api.routes import health, items
from app.core.config import Settings, get_settings
from app.db.session import create_engine, create_session_factory, init_db


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    engine = create_engine(app_settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app_settings.environment == "development":
            await init_db(engine)
        yield
        await engine.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        description="Python API for the UniApp multi-platform starter.",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router, prefix="/api/v1", tags=["system"])
    app.include_router(items.router, prefix="/api/v1", tags=["items"])
    return app


app = create_app()
