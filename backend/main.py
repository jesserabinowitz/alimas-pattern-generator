"""
Sewing Pattern Generator API
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import os

from database import Base, engine
from models import User, UserMeasurements  # ensure models are registered
from routers.auth import router as auth_router
from patterns.openpattern_bridge import render_svg, render_pdf, OPENPATTERN_GARMENTS

app = FastAPI(title="Sewing Pattern Generator", version="0.3.0")

# Create DB tables on startup
Base.metadata.create_all(bind=engine)

app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# ------------------------------------------------------------------
# Garment registry
# ------------------------------------------------------------------

GARMENTS = OPENPATTERN_GARMENTS


@app.get("/garments")
def list_garments():
    """Return all supported garment types with their measurement fields."""
    return GARMENTS


class GenerateRequest(BaseModel):
    garment: str
    measurements: dict
    seam_allowance: float = Field(default=1.5, ge=0, le=3)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@app.post("/generate")
def generate_pattern(req: GenerateRequest):
    """Generate a sewing pattern and return a PDF file."""
    if req.garment.startswith("op_"):
        try:
            pdf_bytes = render_pdf(req.garment, req.measurements)
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{req.garment}_pattern.pdf"'},
        )
    raise HTTPException(status_code=404, detail=f"Unknown garment: {req.garment!r}")


@app.post("/preview")
def preview_pattern(req: GenerateRequest):
    """Generate a sewing pattern and return an SVG for browser preview."""
    if req.garment.startswith("op_"):
        try:
            svg_bytes = render_svg(req.garment, req.measurements)
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))
        return Response(content=svg_bytes, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail=f"Unknown garment: {req.garment!r}")


