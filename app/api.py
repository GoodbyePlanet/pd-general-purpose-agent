from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.slack_app import socket_handler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await socket_handler.connect_async()
    yield
    await socket_handler.disconnect_async()


api = FastAPI(title="PD General Purpose Agent", lifespan=lifespan)


@api.get("/health")
async def health():
    return {"status": "ok"}
