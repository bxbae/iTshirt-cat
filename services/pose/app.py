"""Pose estimation API - Ultralytics YOLO11n-pose (COCO 17 keypoints). 라이선스: AGPL-3.0 (wiki/pose.md 참고).

실행: uvicorn app:app --port 8003
환경변수:
  POSE_WEIGHTS   = 가중치 경로/이름 (기본 "yolo11n-pose.pt", 없으면 ultralytics가 현재 작업 디렉터리에 자동 다운로드)
  POSE_MAX_BYTES = 업로드 최대 바이트 (기본 10MB)
  POSE_IMGSZ     = 추론 해상도 (기본 640)
  POSE_MAX_PIXELS = 디코딩 후 최대 픽셀 수 (기본 40,000,000)
"""
import io
import os
import threading
from typing import List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response
from PIL import Image, ImageDraw, UnidentifiedImageError
from pydantic import BaseModel

MAX_BYTES = int(os.environ.get("POSE_MAX_BYTES", 10 * 1024 * 1024))
MAX_PIXELS = int(os.environ.get("POSE_MAX_PIXELS", 40_000_000))
BODY_HEADROOM = 64 * 1024  # multipart 경계/헤더 여유분
IMGSZ = int(os.environ.get("POSE_IMGSZ", 640))
WEIGHTS = os.environ.get("POSE_WEIGHTS", "yolo11n-pose.pt")
MODEL_NAME = "yolo11n-pose"

KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
]
# COCO 스켈레톤 (0-based 인덱스 쌍)
SKELETON = [
    (15, 13), (13, 11), (16, 14), (14, 12), (11, 12), (5, 11), (6, 12), (5, 6),
    (5, 7), (6, 8), (7, 9), (8, 10), (1, 2), (0, 1), (0, 2), (1, 3), (2, 4), (3, 5), (4, 6),
]

app = FastAPI(title="Pose Estimation (YOLO11n-pose)", version="1.0")
# PIL의 자체 임계(경고/DecompressionBombError)는 끄고 read_image()의 MAX_PIXELS 검사를 단일 기준으로 쓴다.
# (ultralytics가 Image.open을 패치해 예외를 ModuleNotFoundError로 바꿔버릴 수 있어 PIL 예외에 의존하지 않음)
Image.MAX_IMAGE_PIXELS = None


class BodySizeLimitMiddleware:
    """폼 파싱(임시파일 spool) 이전에 Content-Length로 본문 크기를 거부하는 ASGI 미들웨어.

    POST 요청에 Content-Length가 없으면(chunked) 411로 거부한다.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] == "POST":
            headers = dict(scope["headers"])
            raw = headers.get(b"content-length")
            status = detail = None
            if raw is None:
                status, detail = 411, "Content-Length 헤더가 필요합니다."
            else:
                try:
                    length = int(raw)
                except ValueError:
                    length = -1
                if length < 0:
                    status, detail = 400, "잘못된 Content-Length 입니다."
                elif length > MAX_BYTES + BODY_HEADROOM:
                    status, detail = 413, f"요청 본문이 너무 큽니다 (최대 약 {MAX_BYTES} bytes)."
            if status:
                await JSONResponse({"detail": detail}, status_code=status)(scope, receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(BodySizeLimitMiddleware)

_lock = threading.Lock()
_state = {"model": None, "device": None}


class Keypoint(BaseModel):
    name: str
    x: float
    y: float
    score: float


class Person(BaseModel):
    bbox: List[float]  # [x1, y1, x2, y2] 픽셀
    score: float
    keypoints: List[Keypoint]


class PoseResponse(BaseModel):
    model: str
    device: str
    keypoint_format: str
    image_width: int
    image_height: int
    num_persons: int
    persons: List[Person]


def load_model():
    """모델을 전역에 1회만 로드한다 (thread-safe). 테스트에서는 monkeypatch 대상."""
    if _state["model"] is not None:
        return _state
    with _lock:
        if _state["model"] is not None:
            return _state
        import torch
        from ultralytics import YOLO

        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = YOLO(WEIGHTS)
        model.to(device)
        _state.update(model=model, device=device)
    return _state


def run_inference(image: Image.Image, conf: float, kp_conf: float = 0.0):
    """(device, persons) 반환. persons: list of dict(bbox, score, keypoints[{name,x,y,score}])."""
    st = load_model()
    res = st["model"].predict(image, imgsz=IMGSZ, conf=conf, device=st["device"], verbose=False)[0]
    persons = []
    if res.boxes is None or res.keypoints is None or len(res.boxes) == 0:
        return st["device"], persons
    boxes = res.boxes.xyxy.cpu().tolist()
    scores = res.boxes.conf.cpu().tolist()
    kxy = res.keypoints.xy.cpu().tolist()
    kcf = res.keypoints.conf.cpu().tolist() if res.keypoints.conf is not None else None
    for i, box in enumerate(boxes):
        kps = []
        for j, (x, y) in enumerate(kxy[i]):
            s = kcf[i][j] if kcf is not None else 1.0
            kps.append({"name": KEYPOINT_NAMES[j], "x": float(x), "y": float(y), "score": float(s)})
        persons.append({"bbox": [float(v) for v in box], "score": float(scores[i]), "keypoints": kps})
    return st["device"], persons


async def read_image(file: UploadFile) -> Image.Image:
    data = await file.read(MAX_BYTES + 1)
    if not data:
        raise HTTPException(400, "빈 파일입니다.")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"파일이 너무 큽니다 (최대 {MAX_BYTES} bytes).")
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_PIXELS:  # 디코딩 전에 헤더 정보로 검사
            raise HTTPException(413, f"이미지 해상도가 너무 큽니다 (최대 {MAX_PIXELS} 픽셀).")
        image.load()
        return image.convert("RGB")
    except Image.DecompressionBombError:
        raise HTTPException(413, "이미지 해상도가 너무 큽니다 (decompression bomb).")
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "이미지로 디코딩할 수 없는 파일입니다.")


def infer_or_503(image, conf, kp_conf):
    try:
        return run_inference(image, conf, kp_conf)
    except Exception as e:  # 모델 로드/다운로드 실패 등
        raise HTTPException(503, f"모델 추론 실패: {type(e).__name__}: {e}")


def draw_overlay(image: Image.Image, persons, kp_conf: float) -> Image.Image:
    out = image.copy()
    d = ImageDraw.Draw(out)
    w = max(2, round(min(out.size) / 200))
    for p in persons:
        x1, y1, x2, y2 = p["bbox"]
        d.rectangle([x1, y1, x2, y2], outline=(255, 200, 0), width=max(1, w // 2))
        kps = p["keypoints"]
        for a, b in SKELETON:
            if kps[a]["score"] >= kp_conf and kps[b]["score"] >= kp_conf:
                d.line([kps[a]["x"], kps[a]["y"], kps[b]["x"], kps[b]["y"]], fill=(0, 255, 0), width=w)
        for k in kps:
            if k["score"] >= kp_conf:
                r = w + 1
                d.ellipse([k["x"] - r, k["y"] - r, k["x"] + r, k["y"] + r], fill=(255, 0, 0))
    return out


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME, "loaded": _state["model"] is not None,
            "device": _state["device"]}


@app.post("/pose", response_model=PoseResponse)
async def pose(file: UploadFile = File(...),
               conf: float = Query(0.25, ge=0.0, le=1.0, description="사람 검출 최소 신뢰도"),
               kp_conf: float = Query(0.0, ge=0.0, le=1.0, description="이 값 미만 keypoint는 응답에서 제외")):
    image = await read_image(file)
    device, persons = infer_or_503(image, conf, kp_conf)
    if kp_conf > 0:
        for p in persons:
            p["keypoints"] = [k for k in p["keypoints"] if k["score"] >= kp_conf]
    return {"model": MODEL_NAME, "device": device, "keypoint_format": "coco17",
            "image_width": image.width, "image_height": image.height,
            "num_persons": len(persons), "persons": persons}


@app.post("/pose/image", responses={200: {"content": {"image/png": {}}}})
async def pose_image(file: UploadFile = File(...),
                     conf: float = Query(0.25, ge=0.0, le=1.0),
                     kp_conf: float = Query(0.3, ge=0.0, le=1.0, description="이 값 이상 keypoint만 그림")):
    image = await read_image(file)
    device, persons = infer_or_503(image, conf, kp_conf)
    out = draw_overlay(image, persons, kp_conf)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"X-Num-Persons": str(len(persons)), "X-Device": device})
