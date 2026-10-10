"""Object detection service: torchvision SSDlite320 MobileNetV3-Large (COCO, BSD-3).

Run:  uvicorn app:app --port 8002
Env:  DETECTION_DEVICE=cpu|cuda  (default: auto)
      DETECTION_WEIGHTS=default|none  ('none' = random weights, ONLY for smoke tests)
      DETECTION_MAX_BYTES (default 10 MB)
"""
import io
import os
import threading
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from pydantic import BaseModel

MODEL_NAME = "ssdlite320_mobilenet_v3_large"
MAX_BYTES = int(os.getenv("DETECTION_MAX_BYTES", 10 * 1024 * 1024))
MAX_PIXELS = 25_000_000
INFER_MAX_SIDE = 1280  # downscale before inference (model input is 320x320 anyway)
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp", "application/octet-stream"}

app = FastAPI(title="Object Detection (SSDlite320 MobileNetV3)", version="1.0.0")

_state = {"model": None, "categories": None, "device": None, "transform": None}
_load_lock = threading.Lock()
_infer_lock = threading.Lock()


class Box(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class Detection(BaseModel):
    label: str
    label_id: int
    score: float
    bbox: Box


class DetectResponse(BaseModel):
    model: str
    width: int
    height: int
    count: int
    detections: List[Detection]


def _pick_device() -> str:
    import torch

    want = os.getenv("DETECTION_DEVICE", "").lower()
    if want in ("cpu", "cuda"):
        if want == "cuda" and not torch.cuda.is_available():
            return "cpu"
        return want
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_model():
    """Lazy, process-wide single load (thread-safe)."""
    if _state["model"] is None:
        with _load_lock:
            if _state["model"] is None:
                import torch  # noqa: F401
                from torchvision.models.detection import (
                    SSDLite320_MobileNet_V3_Large_Weights,
                    ssdlite320_mobilenet_v3_large,
                )

                weights_enum = SSDLite320_MobileNet_V3_Large_Weights.DEFAULT
                if os.getenv("DETECTION_WEIGHTS", "default").lower() == "none":
                    model = ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None)
                else:
                    model = ssdlite320_mobilenet_v3_large(weights=weights_enum)
                device = _pick_device()
                model.eval().to(device)
                _state.update(
                    model=model,
                    categories=weights_enum.meta["categories"],
                    device=device,
                    transform=weights_enum.transforms(),
                )
    return _state["model"]


def _infer(img: Image.Image, threshold: float, max_det: int) -> List[Detection]:
    """Run the model. Boxes are in original-image pixel coordinates."""
    import torch
    from torchvision.transforms.functional import pil_to_tensor

    model = get_model()
    device = _state["device"]
    # Downscale large images; boxes are mapped back to original coordinates below.
    scale_x = scale_y = 1.0
    small = img
    if max(img.size) > INFER_MAX_SIDE:
        small = img.copy()
        small.thumbnail((INFER_MAX_SIDE, INFER_MAX_SIDE))
        scale_x = img.width / small.width
        scale_y = img.height / small.height
    # Tensor build + device transfer happen inside the lock so concurrent
    # requests do not each hold a full tensor in RAM/VRAM.
    with _infer_lock, torch.inference_mode():
        tensor = _state["transform"](pil_to_tensor(small)).to(device)
        out = model([tensor])[0]
        del tensor
    cats = _state["categories"]
    res: List[Detection] = []
    for b, l, s in zip(out["boxes"].tolist(), out["labels"].tolist(), out["scores"].tolist()):
        if s < threshold:
            continue
        res.append(
            Detection(
                label=cats[l] if 0 <= l < len(cats) else str(l),
                label_id=int(l),
                score=round(float(s), 4),
                bbox=Box(x1=b[0] * scale_x, y1=b[1] * scale_y, x2=b[2] * scale_x, y2=b[3] * scale_y),
            )
        )
        if len(res) >= max_det:
            break
    return res


def _load_image(data: bytes) -> Image.Image:
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"file too large (> {MAX_BYTES} bytes)")
    try:
        probe = Image.open(io.BytesIO(data))
        if probe.width * probe.height > MAX_PIXELS:
            raise HTTPException(413, "image dimensions too large")
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        return img.convert("RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
        raise HTTPException(400, "cannot decode image (send jpeg/png/webp/bmp)")


def _check_type(file: UploadFile):
    if file.content_type and file.content_type.lower() not in ALLOWED_TYPES:
        raise HTTPException(415, f"unsupported content-type: {file.content_type}")


def _detect(file: UploadFile, threshold: float, max_det: int):
    _check_type(file)
    data = file.file.read(MAX_BYTES + 1)  # bounded read: never buffer more than limit+1
    img = _load_image(data)
    try:
        dets = _infer(img, threshold, max_det)
    except HTTPException:
        raise
    except Exception as e:  # model load / weight download failure etc.
        raise HTTPException(503, f"inference unavailable: {type(e).__name__}: {e}")
    return img, dets


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "loaded": _state["model"] is not None,
        "device": _state["device"],
    }


@app.post("/detect", response_model=DetectResponse)
def detect(
    file: UploadFile = File(..., description="image file"),
    score_threshold: float = Form(0.5, ge=0.0, le=1.0),
    max_detections: int = Form(100, ge=1, le=300),
):
    img, dets = _detect(file, score_threshold, max_detections)
    return DetectResponse(
        model=MODEL_NAME, width=img.width, height=img.height, count=len(dets), detections=dets
    )


@app.post("/detect/image")
def detect_image(
    file: UploadFile = File(...),
    score_threshold: float = Form(0.5, ge=0.0, le=1.0),
    max_detections: int = Form(100, ge=1, le=300),
):
    img, dets = _detect(file, score_threshold, max_detections)
    canvas = img.copy()
    draw = ImageDraw.Draw(canvas)
    width = max(2, round(min(canvas.size) / 200))
    for d in dets:
        b = d.bbox
        color = ((d.label_id * 67) % 256, (d.label_id * 131) % 256, (d.label_id * 197) % 256)
        draw.rectangle([b.x1, b.y1, b.x2, b.y2], outline=color, width=width)
        text = f"{d.label} {d.score:.2f}"
        tb = draw.textbbox((b.x1, b.y1), text)
        ty = max(0, b.y1 - (tb[3] - tb[1]) - 2)
        draw.rectangle([b.x1, ty, b.x1 + (tb[2] - tb[0]) + 4, ty + (tb[3] - tb[1]) + 2], fill=color)
        draw.text((b.x1 + 2, ty), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"X-Detection-Count": str(len(dets))})
