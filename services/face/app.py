"""Face service (YuNet detection + SFace embedding via OpenCV). Port 8004.

Run:  uvicorn app:app --port 8004
Models (ONNX, ~0.2MB + ~37MB) are downloaded on first use into ./models (override: FACE_MODEL_DIR).
"""
import hashlib
import os
import struct
import threading
import urllib.request
from pathlib import Path
from typing import Optional

# Decompression-bomb guard: must be set before cv2 is first used (defence in depth; _probe_size is the main check).
MAX_PIXELS = int(os.environ.get("FACE_MAX_PIXELS", 40_000_000))
os.environ.setdefault("CV_IO_MAX_IMAGE_PIXELS", str(MAX_PIXELS))

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

MODEL_DIR = Path(os.environ.get("FACE_MODEL_DIR", Path(__file__).parent / "models"))
MAX_BYTES = int(os.environ.get("FACE_MAX_BYTES", 10 * 1024 * 1024))
MAX_SIDE = int(os.environ.get("FACE_MAX_SIDE", 1280))  # detection runs on image downscaled to this
# OpenCV zoo recommended cosine threshold for SFace (same-person if cosine >= 0.363)
COSINE_THRESHOLD = float(os.environ.get("FACE_COSINE_THRESHOLD", 0.363))
DET_SCORE_THRESHOLD = 0.7

# (filename, urls tried in order, sha256 of the file as downloaded when this service was written)
_BASE = "opencv/opencv_zoo/main/models"
MODELS = {
    "detector": (
        "face_detection_yunet_2023mar.onnx",
        [f"https://media.githubusercontent.com/media/{_BASE}/face_detection_yunet/face_detection_yunet_2023mar.onnx",
         f"https://github.com/{_BASE.replace('/main/', '/raw/main/')}/face_detection_yunet/face_detection_yunet_2023mar.onnx"],
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "recognizer": (
        "face_recognition_sface_2021dec.onnx",
        [f"https://media.githubusercontent.com/media/{_BASE}/face_recognition_sface/face_recognition_sface_2021dec.onnx",
         f"https://github.com/{_BASE.replace('/main/', '/raw/main/')}/face_recognition_sface/face_recognition_sface_2021dec.onnx"],
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}

app = FastAPI(title="Face Service (YuNet + SFace)", version="1.0")

_lock = threading.Lock()  # FaceDetectorYN.setInputSize mutates state -> serialize inference
_detector = None
_recognizer = None
_gallery: dict[str, np.ndarray] = {}  # name -> L2-normalised 128-d embedding (in-memory)
_load_error: Optional[str] = None  # cached model load failure -> 503 instead of retrying a slow download every request


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_model(key: str) -> Path:
    name, urls, sha = MODELS[key]
    path = MODEL_DIR / name
    if path.exists() and _sha256(path) == sha:
        return path
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    last = None
    for url in urls:
        try:
            tmp = path.with_suffix(".part")
            with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            if _sha256(tmp) != sha:
                tmp.unlink(missing_ok=True)
                raise RuntimeError("sha256 mismatch")
            tmp.replace(path)
            return path
        except Exception as e:  # try next URL
            last = f"{url}: {e}"
    raise RuntimeError(f"cannot download {name} ({last}). Place the file manually in {MODEL_DIR}")


def _load():
    """Lazy-load once (global). Called with _lock held."""
    global _detector, _recognizer, _load_error
    if _detector is not None:
        return
    if _load_error:
        raise HTTPException(503, _load_error)
    try:
        dpath, rpath = _ensure_model("detector"), _ensure_model("recognizer")
        # OpenCV DNN opens str paths with the ANSI codepage on Windows -> non-ASCII (e.g. Korean) paths can fail.
        # Prefer the in-memory buffer overload; fall back to path only if the buffer overload is unavailable.
        try:
            det = cv2.FaceDetectorYN.create("onnx", dpath.read_bytes(), b"", (320, 320), DET_SCORE_THRESHOLD, 0.3, 5000)
        except (TypeError, cv2.error):
            if not str(dpath).isascii():
                raise RuntimeError(f"model path {dpath} is non-ASCII and this OpenCV cannot load from memory; "
                                   "set FACE_MODEL_DIR to an ASCII-only folder (e.g. C:\\face_models)")
            det = cv2.FaceDetectorYN.create(str(dpath), "", (320, 320), DET_SCORE_THRESHOLD, 0.3, 5000)
        if not str(rpath).isascii():
            # FaceRecognizerSF.create has no buffer overload in Python bindings
            raise RuntimeError(f"model path {rpath} is non-ASCII; set FACE_MODEL_DIR to an ASCII-only folder "
                               "(e.g. C:\\face_models)")
        _recognizer = cv2.FaceRecognizerSF.create(str(rpath), "")
        _detector = det
    except HTTPException:
        raise
    except Exception as e:
        _load_error = f"face model unavailable: {e}"
        raise HTTPException(503, _load_error)


def _probe_size(d: bytes) -> Optional[tuple]:
    """Read (width, height) from the header without decoding. Supports PNG/JPEG/BMP/WebP; None if unknown."""
    try:
        if d[:8] == b"\x89PNG\r\n\x1a\n" and len(d) >= 24:
            return struct.unpack(">II", d[16:24])
        if d[:2] == b"BM" and len(d) >= 26:
            w, h = struct.unpack("<ii", d[18:26])
            return abs(w), abs(h)
        if d[:4] == b"RIFF" and d[8:12] == b"WEBP":
            if d[12:16] == b"VP8X":
                return 1 + int.from_bytes(d[24:27], "little"), 1 + int.from_bytes(d[27:30], "little")
            if d[12:16] == b"VP8 ":
                w, h = struct.unpack("<HH", d[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if d[12:16] == b"VP8L":
                b = int.from_bytes(d[21:25], "little")
                return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
        if d[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(d):
                if d[i] != 0xFF:
                    i += 1
                    continue
                m = d[i + 1]
                if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7 or m == 0xFF:
                    i += 1 if m == 0xFF else 2
                    continue
                if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", d[i + 5:i + 9])
                    return w, h
                i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
    except Exception:
        pass
    return None


def _decode(data: bytes) -> np.ndarray:
    if not data:
        raise HTTPException(400, "empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"file too large (> {MAX_BYTES} bytes)")
    size = _probe_size(data)
    if size and size[0] * size[1] > MAX_PIXELS:
        raise HTTPException(413, f"image too large ({size[0]}x{size[1]} px > {MAX_PIXELS} px)")
    try:
        img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    except cv2.error:
        raise HTTPException(413, "image rejected by decoder (too many pixels or corrupt)")
    if img is None:
        raise HTTPException(400, "not a valid image (jpg/png/bmp/webp)")
    return img


async def _read_image(file: UploadFile) -> np.ndarray:
    # read at most MAX_BYTES+1 so an oversized upload is never fully pulled into RAM
    data = await file.read(MAX_BYTES + 1)
    return await run_in_threadpool(_decode, data)


def _detect(img: np.ndarray, threshold: Optional[float] = None) -> np.ndarray:
    """Return Nx15 array in ORIGINAL image coords: x,y,w,h, 5 landmarks (x,y), score. Sorted by score desc."""
    with _lock:
        _load()
        h, w = img.shape[:2]
        scale = min(1.0, MAX_SIDE / max(h, w))
        small = cv2.resize(img, (max(1, round(w * scale)), max(1, round(h * scale)))) if scale < 1 else img
        _detector.setInputSize((small.shape[1], small.shape[0]))
        if threshold is not None:
            _detector.setScoreThreshold(float(threshold))
        else:
            _detector.setScoreThreshold(DET_SCORE_THRESHOLD)
        _, faces = _detector.detect(small)
    if faces is None:
        return np.zeros((0, 15), np.float32)
    faces = faces.copy()
    faces[:, :14] /= scale
    return faces[np.argsort(-faces[:, 14])]


def _embed(img: np.ndarray, face: np.ndarray) -> np.ndarray:
    with _lock:
        _load()
        aligned = _recognizer.alignCrop(img, face)
        feat = _recognizer.feature(aligned).flatten().astype(np.float32)
    n = np.linalg.norm(feat)
    return feat / n if n > 0 else feat


def _face_json(f: np.ndarray) -> dict:
    return {
        "box": {"x": float(f[0]), "y": float(f[1]), "w": float(f[2]), "h": float(f[3])},
        "landmarks": {k: [float(f[4 + 2 * i]), float(f[5 + 2 * i])]
                      for i, k in enumerate(["right_eye", "left_eye", "nose", "right_mouth", "left_mouth"])},
        "score": float(f[14]),
    }


def _best_embedding(img: np.ndarray):
    faces = _detect(img)
    if len(faces) == 0:
        raise HTTPException(422, "no face detected")
    # pick the largest face (area), more robust than top score for group shots
    f = faces[int(np.argmax(faces[:, 2] * faces[:, 3]))]
    return f, _embed(img, f)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "models_loaded": _detector is not None,
        "device": "cpu",  # OpenCV DNN default backend; these models are small enough for CPU
        "opencv": cv2.__version__,
        "gallery_size": len(_gallery),
        "cosine_threshold": COSINE_THRESHOLD,
    }


@app.post("/detect")
async def detect(file: UploadFile = File(...), score_threshold: float = Form(DET_SCORE_THRESHOLD)):
    if not 0.0 <= score_threshold <= 1.0:
        raise HTTPException(422, "score_threshold must be in [0,1]")
    img = await _read_image(file)
    faces = await run_in_threadpool(_detect, img, score_threshold)
    return {"image": {"width": img.shape[1], "height": img.shape[0]},
            "count": len(faces), "faces": [_face_json(f) for f in faces]}


@app.post("/embed")
async def embed(file: UploadFile = File(...)):
    img = await _read_image(file)
    f, e = await run_in_threadpool(_best_embedding, img)
    return {"face": _face_json(f), "dim": int(e.shape[0]), "normalized": True, "embedding": e.tolist()}


@app.post("/verify")
async def verify(file1: UploadFile = File(...), file2: UploadFile = File(...)):
    a, b = await _read_image(file1), await _read_image(file2)
    fa, ea = await run_in_threadpool(_best_embedding, a)
    fb, eb = await run_in_threadpool(_best_embedding, b)
    sim = float(np.dot(ea, eb))
    return {"same_person": sim >= COSINE_THRESHOLD, "cosine_similarity": sim, "threshold": COSINE_THRESHOLD,
            "face1": _face_json(fa), "face2": _face_json(fb)}


@app.post("/gallery/register")
async def gallery_register(name: str = Form(...), file: UploadFile = File(...)):
    name = name.strip()
    if not name or len(name) > 100:
        raise HTTPException(422, "name must be 1..100 chars")
    img = await _read_image(file)
    f, e = await run_in_threadpool(_best_embedding, img)
    replaced = name in _gallery
    _gallery[name] = e
    return {"name": name, "replaced": replaced, "gallery_size": len(_gallery), "face": _face_json(f)}


@app.post("/gallery/identify")
async def gallery_identify(file: UploadFile = File(...)):
    if not _gallery:
        raise HTTPException(409, "gallery is empty; register faces first")
    img = await _read_image(file)
    f, e = await run_in_threadpool(_best_embedding, img)
    scores = sorted(((n, float(np.dot(e, v))) for n, v in _gallery.items()), key=lambda t: -t[1])
    name, sim = scores[0]
    return {"match": sim >= COSINE_THRESHOLD, "name": name if sim >= COSINE_THRESHOLD else None,
            "best_name": name, "cosine_similarity": sim, "threshold": COSINE_THRESHOLD,
            "candidates": [{"name": n, "cosine_similarity": s} for n, s in scores[:5]], "face": _face_json(f)}


@app.get("/gallery")
def gallery_list():
    return {"names": sorted(_gallery), "size": len(_gallery)}


@app.delete("/gallery/{name}")
def gallery_delete(name: str):
    if name not in _gallery:
        raise HTTPException(404, "unknown name")
    del _gallery[name]
    return {"deleted": name, "gallery_size": len(_gallery)}
