from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, contacts, metadata, rules
from app.core.config import get_settings
from app.core.database import close_database, get_database


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_database()
    yield
    await close_database()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Dynamic Rule Builder API for creating nested filter conditions, "
            "saving rule templates, and querying MongoDB datasets."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    prefix = settings.api_prefix
    app.include_router(auth.router, prefix=prefix)
    app.include_router(metadata.router, prefix=prefix)
    app.include_router(rules.router, prefix=prefix)
    app.include_router(contacts.router, prefix=prefix)

    @app.get("/", tags=["Health"])
    async def root() -> dict[str, str]:
        return {
            "message": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
        }

    @app.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
