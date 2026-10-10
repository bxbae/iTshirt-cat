"""Korean emotion classification API (FastAPI). Run: uvicorn app:app --port 8005"""
import os
import threading
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODEL_ID = os.environ.get("MODEL_ID", "GGARA02/kcelectra-korean-emotion")
MAX_TEXTS = int(os.environ.get("MAX_TEXTS", "64"))
MAX_CHARS = int(os.environ.get("MAX_CHARS", "1000"))
MAX_LENGTH = int(os.environ.get("MAX_LENGTH", "256"))
# MULTI_LABEL=1 -> sigmoid (independent scores, e.g. KOTE-style 43 labels); default: auto from config
MULTI_LABEL = os.environ.get("MULTI_LABEL")

app = FastAPI(title="Korean Emotion API", version="1.0")


class PredictRequest(BaseModel):
    texts: List[str] = Field(..., min_length=1)
    top_k: int = Field(3, ge=1, le=50)


class Score(BaseModel):
    label: str
    score: float


class PredictResponse(BaseModel):
    model: str
    device: str
    results: List[List[Score]]


class Predictor:
    def __init__(self, model_id: str):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch = torch
        self.model_id = model_id
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_id).to(self.device).eval()
        cfg = self.model.config
        self.id2label = {int(k): v for k, v in cfg.id2label.items()}
        if MULTI_LABEL is not None:
            self.multi = MULTI_LABEL == "1"
        else:
            self.multi = getattr(cfg, "problem_type", None) == "multi_label_classification"

    def predict(self, texts: List[str], top_k: int):
        torch = self.torch
        enc = self.tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=MAX_LENGTH)
        enc = {k: v.to(self.device) for k, v in enc.items()}
        with torch.inference_mode():
            logits = self.model(**enc).logits
        probs = (torch.sigmoid(logits) if self.multi else torch.softmax(logits, dim=-1)).cpu().tolist()
        out = []
        for row in probs:
            order = sorted(range(len(row)), key=lambda i: -row[i])[:top_k]
            out.append([{"label": self.id2label.get(i, str(i)), "score": round(row[i], 6)} for i in order])
        return out


_predictor: Optional[Any] = None
_lock = threading.Lock()


def get_predictor():
    global _predictor
    if _predictor is None:
        with _lock:
            if _predictor is None:
                _predictor = Predictor(MODEL_ID)
    return _predictor


@app.get("/health")
def health():
    return {"status": "ok", "model_id": MODEL_ID, "loaded": _predictor is not None,
            "device": getattr(_predictor, "device", None)}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    if len(req.texts) > MAX_TEXTS:
        raise HTTPException(422, f"too many texts (max {MAX_TEXTS})")
    for t in req.texts:
        if not t.strip():
            raise HTTPException(422, "empty text")
        if len(t) > MAX_CHARS:
            raise HTTPException(422, f"text too long (max {MAX_CHARS} chars)")
    try:
        p = get_predictor()
    except Exception as e:  # download/load failure
        raise HTTPException(503, f"model load failed: {type(e).__name__}: {e}")
    with _lock:  # serialize inference; keeps GPU memory predictable
        results = p.predict(req.texts, req.top_k)
    return {"model": MODEL_ID, "device": p.device, "results": results}
