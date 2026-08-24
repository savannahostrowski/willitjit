from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

app = FastAPI(
    title="Will It JIT?",
    description="CPython JIT compatibility across popular Python packages.",
)

STATIC_DIR = Path(__file__).parent / "static"


class HealthResponse(BaseModel):
    status: Literal["ok"]


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    lines = [
        "# HELP willitjit_up Whether the application is serving requests.",
        "# TYPE willitjit_up gauge",
        "willitjit_up 1",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


# Keep this last: browser routes fall back to the Vite entrypoint.
app.frontend("/", directory=str(STATIC_DIR), fallback="index.html", check_dir=False)
