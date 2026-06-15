import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Must be first — lets agent.*, data.*, config resolve from the repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from backend.routers import auth, bets, public, queue
from backend.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stoppage-Time API",
        description="Backend API for the Stoppage-Time betting agent.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/auth")
    app.include_router(public.router, prefix="/api/public")
    app.include_router(bets.router, prefix="/api")
    app.include_router(queue.router, prefix="/api")

    return app


app = create_app()
