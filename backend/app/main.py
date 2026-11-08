from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.db import init_db

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="BantayPondo API", version="0.2.0", lifespan=lifespan,
              description="Public infrastructure spending watchdog. All data is linked to its source.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")

# Serve the GUI at "/" (open http://localhost:8000)
if FRONTEND.exists():
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
