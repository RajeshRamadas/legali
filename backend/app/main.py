import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from . import accounts, admin, blog_agent, cases, chat, config, documents, lawyers, meetings, notify, payments, posts, public, rera, verification, verification_workflow
from .bootstrap import sync_reference_data
from .db import SessionLocal
from .models import ReraProject
from .rera_sample import load_sample

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Tables come from Alembic migrations (`alembic upgrade head`); this only syncs reference data.
    with SessionLocal() as db:
        sync_reference_data(db)
        if config.RERA_SAMPLE_WHEN_EMPTY and db.scalars(select(ReraProject.id).limit(1)).first() is None:
            load_sample(db)
    workers = [asyncio.create_task(notify.worker_loop())] if config.NOTIFY_WORKER_ENABLED else []
    if config.BLOG_AGENT_ENABLED:
        workers.append(asyncio.create_task(blog_agent.worker_loop()))
    yield
    for worker in workers:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker

app = FastAPI(
    title="Homexo Property Services API",
    version="0.2.0",
    description="Service catalogue, ticket intake and tracking, staff ticket workspace, video consultations, lawyer search and booking, customer accounts with phone sign-in, customer documents and legal reports, chat assistant, blog and Karnataka RERA project check.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.include_router(public.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(cases.router)
app.include_router(meetings.router)
app.include_router(lawyers.router)
app.include_router(posts.router)
app.include_router(blog_agent.router)
app.include_router(documents.router)
app.include_router(payments.router)
app.include_router(rera.router)
app.include_router(accounts.router)
app.include_router(verification.router)
app.include_router(verification_workflow.router)
