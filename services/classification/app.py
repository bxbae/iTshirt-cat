"""이미지 분류 API - torchvision MobileNetV3-Small (ImageNet-1k).

실행: uvicorn app:app --port 8001
환경변수:
  CLS_WEIGHTS = "default"(기본, ImageNet 가중치 자동 다운로드) | "none"(무작위 가중치, 오프라인 스모크 테스트용)
  CLS_MAX_BYTES = 업로드 최대 바이트 (기본 10MB)
"""
import io
import os
import threading
from typing import List

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

MAX_BYTES = int(os.environ.get("CLS_MAX_BYTES", 10 * 1024 * 1024))
MAX_PIXELS = int(os.environ.get("CLS_MAX_PIXELS", 40_000_000))  # 디코딩 폭탄 방어
MODEL_NAME = "mobilenet_v3_small"

app = FastAPI(title="Image Classification (MobileNetV3-Small)", version="1.0")

_lock = threading.Lock()
_state = {"model": None, "preprocess": None, "labels": None, "device": None}


class Prediction(BaseModel):
    label: str
    index: int
    probability: float


class PredictResponse(BaseModel):
    model: str
    device: str
    top_k: int
    predictions: List[Prediction]


def load_model():
    """모델을 전역에 1회만 로드한다 (thread-safe). 테스트에서는 monkeypatch 대상."""
    if _state["model"] is not None:
        return _state
    with _lock:
        if _state["model"] is not None:
            return _state
        import torch
        from torchvision import models

        device = "cuda" if torch.cuda.is_available() else "cpu"
        use_weights = os.environ.get("CLS_WEIGHTS", "default").lower() != "none"
        if use_weights:
            weights = models.MobileNet_V3_Small_Weights.DEFAULT
            model = models.mobilenet_v3_small(weights=weights)
            preprocess = weights.transforms()
            labels = list(weights.meta["categories"])
        else:
            from torchvision import transforms as T

            model = models.mobilenet_v3_small(weights=None)
            preprocess = T.Compose([
                T.Resize(256), T.CenterCrop(224), T.ToTensor(),
                T.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ])
            labels = [f"class_{i}" for i in range(1000)]
        model.eval().to(device)
        _state.update(model=model, preprocess=preprocess, labels=labels, device=device)
    return _state


def run_inference(image: Image.Image, top_k: int):
    import torch

    st = load_model()
    x = st["preprocess"](image).unsqueeze(0).to(st["device"])
    with torch.inference_mode():
        probs = torch.softmax(st["model"](x)[0], dim=0)
    k = min(top_k, probs.numel())
    p, idx = probs.topk(k)
    return st["device"], [
        {"label": st["labels"][i], "index": int(i), "probability": float(v)}
        for v, i in zip(p.cpu().tolist(), idx.cpu().tolist())
    ]


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "loaded": _state["model"] is not None,
            "device": _state["device"]}


@app.post("/predict", response_model=PredictResponse)
async def predict(file: UploadFile = File(...), top_k: int = Query(5, ge=1, le=20)):
    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(400, "빈 파일입니다.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"파일이 너무 큽니다 (최대 {MAX_BYTES} bytes).")
    try:
        image = Image.open(io.BytesIO(data))  # 헤더만 파싱, 픽셀 디코딩 전
        w, h = image.size
        if w * h > MAX_PIXELS:
            raise HTTPException(413, f"이미지 해상도가 너무 큽니다 (최대 {MAX_PIXELS} 픽셀).")
        image.load()
        image = image.convert("RGB")
    except HTTPException:
        raise
    except Image.DecompressionBombError:
        raise HTTPException(413, "이미지 해상도가 너무 큽니다.")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "이미지로 디코딩할 수 없는 파일입니다.")
    try:
        # 모델 로드/다운로드와 추론은 블로킹이므로 이벤트 루프 밖(스레드풀)에서 실행
        device, preds = await run_in_threadpool(run_inference, image, top_k)
    except Exception as e:  # 모델 로드/다운로드 실패 등
        raise HTTPException(503, f"모델 추론 실패: {type(e).__name__}: {e}")
    return {"model": MODEL_NAME, "device": device, "top_k": len(preds), "predictions": preds}
