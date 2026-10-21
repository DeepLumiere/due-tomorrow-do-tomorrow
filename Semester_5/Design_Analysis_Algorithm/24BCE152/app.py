"""
FastAPI Server for Content-Aware Seam Carving.
Serves index.html from static template and exposes REST endpoints.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image, ImageDraw

from seam_carving import SeamCarver

app = FastAPI(title="Seam Carving")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML_PATH = BASE_DIR / "index.html"


def array_to_base64_png(arr: np.ndarray) -> str:
    pil_img = Image.fromarray(arr.astype(np.uint8))
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")




@app.get("/")
def get_index():
    return FileResponse(INDEX_HTML_PATH, media_type="text/html")



@app.post("/api/carve")
async def carve_image(
    file: UploadFile = File(...),
    seams_v: int = Form(default=40),
    seams_h: int = Form(default=0),
    energy_method: str = Form(default="dual_gradient"),
    max_dimension: int = Form(default=4096),
):
    try:
        contents = await file.read()
        pil_img = Image.open(io.BytesIO(contents)).convert("RGB")

        if max_dimension and (pil_img.width > max_dimension or pil_img.height > max_dimension):
            pil_img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        orig_w, orig_h = pil_img.size
        target_w = max(1, orig_w - max(0, seams_v))
        target_h = max(1, orig_h - max(0, seams_h))

        carver = SeamCarver(pil_img)
        init_energy_img = carver.get_energy_map_image(target="original")

        metrics = carver.resize(target_width=target_w, target_height=target_h)

        comp_img = carver.current_image
        seam_vis = carver.get_seam_visualization()
        final_energy_img = carver.get_energy_map_image(target="compressed")

        return {
            "success": True,
            "metrics": {
                "original_width": metrics.original_width,
                "original_height": metrics.original_height,
                "compressed_width": metrics.compressed_width,
                "compressed_height": metrics.compressed_height,
                "vertical_seams_removed": metrics.vertical_seams_removed,
                "horizontal_seams_removed": metrics.horizontal_seams_removed,
                "total_pixels_removed": metrics.total_pixels_removed,
                "pixel_reduction_percent": metrics.pixel_reduction_percent,
                "original_bytes_png": metrics.original_bytes_png,
                "compressed_bytes_png": metrics.compressed_bytes_png,
                "byte_compression_ratio": metrics.byte_compression_ratio,
                "total_time_seconds": metrics.total_time_seconds,
                "seams_per_second": metrics.seams_per_second,
                "initial_average_energy": metrics.initial_average_energy,
                "final_average_energy": metrics.final_average_energy,
                "energy_density_change_percent": metrics.energy_density_change_percent,
                "energy_method": metrics.energy_method,
            },
            "images": {
                "original": array_to_base64_png(carver.original_image),
                "compressed": array_to_base64_png(comp_img),
                "seam_overlay": array_to_base64_png(seam_vis),
                "energy_initial": array_to_base64_png(init_energy_img),
                "energy_final": array_to_base64_png(final_energy_img),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
