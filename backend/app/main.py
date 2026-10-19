import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import admin, chat, config, meetings, notify, public
from .bootstrap import sync_reference_data
from .db import SessionLocal

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tables come from Alembic migrations (`alembic upgrade head`); this only syncs reference data.
    with SessionLocal() as db:
        sync_reference_data(db)
    worker = asyncio.create_task(notify.worker_loop()) if config.NOTIFY_WORKER_ENABLED else None
    yield
    if worker:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

app = FastAPI(
    title="Homexo Property Services API",
    version="0.2.0",
    description="Service catalogue, ticket intake and tracking, staff ticket workspace, video consultations and chat assistant.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.include_router(public.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(meetings.router)
