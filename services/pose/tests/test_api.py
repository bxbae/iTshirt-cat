import io
import os
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app as appmod  # noqa: E402

client = TestClient(appmod.app)


def img_bytes(fmt="PNG", size=(120, 160)):
    b = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(b, format=fmt)
    return b.getvalue()


def fake_person():
    kps = [{"name": n, "x": 20.0 + i * 5, "y": 10.0 + i * 8, "score": 0.9 if i % 2 == 0 else 0.1}
           for i, n in enumerate(appmod.KEYPOINT_NAMES)]
    return {"bbox": [5.0, 5.0, 100.0, 150.0], "score": 0.88, "keypoints": kps}


@pytest.fixture
def mock_infer(monkeypatch):
    monkeypatch.setattr(appmod, "run_inference", lambda image, conf, kp_conf=0.0: ("cpu", [fake_person(), fake_person()]))


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_pose_ok(mock_infer):
    r = client.post("/pose", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 200
    j = r.json()
    assert j["num_persons"] == 2 and j["keypoint_format"] == "coco17"
    assert (j["image_width"], j["image_height"]) == (120, 160)
    p = j["persons"][0]
    assert len(p["keypoints"]) == 17 and set(p["keypoints"][0]) == {"name", "x", "y", "score"}
    assert len(p["bbox"]) == 4


def test_pose_kp_conf_filters(mock_infer):
    r = client.post("/pose?kp_conf=0.5", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 200
    assert len(r.json()["persons"][0]["keypoints"]) == 9  # 짝수 인덱스 9개만 0.9


def test_pose_no_person(monkeypatch):
    monkeypatch.setattr(appmod, "run_inference", lambda *a, **k: ("cpu", []))
    r = client.post("/pose", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 200 and r.json()["num_persons"] == 0 and r.json()["persons"] == []


def test_pose_image_png(mock_infer):
    r = client.post("/pose/image", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["x-num-persons"] == "2"
    out = Image.open(io.BytesIO(r.content))
    assert out.size == (120, 160)
    assert out.getpixel((5, 5)) != (10, 20, 30)  # 박스가 그려졌는지


def test_empty_file():
    for path in ("/pose", "/pose/image"):
        assert client.post(path, files={"file": ("a.png", b"", "image/png")}).status_code == 400


def test_not_image():
    assert client.post("/pose", files={"file": ("a.txt", b"hello", "text/plain")}).status_code == 400


def test_too_large(monkeypatch):
    monkeypatch.setattr(appmod, "MAX_BYTES", 10)
    assert client.post("/pose", files={"file": ("a.png", img_bytes(), "image/png")}).status_code == 413


def test_missing_file_and_bad_params(mock_infer):
    assert client.post("/pose").status_code == 422
    r = client.post("/pose?conf=2", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 422


def test_model_failure_503(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no weights")
    monkeypatch.setattr(appmod, "run_inference", boom)
    assert client.post("/pose", files={"file": ("a.png", img_bytes(), "image/png")}).status_code == 503


def test_real_model_if_available():
    """실제 yolo11n-pose 가중치가 로컬에 있을 때만: 단색 이미지 -> 사람 0명이어도 200이어야 한다."""
    w = os.environ.get("POSE_WEIGHTS", "yolo11n-pose.pt")
    if not os.path.exists(w):
        pytest.skip("가중치 파일 없음")
    r = client.post("/pose", files={"file": ("a.png", img_bytes(size=(320, 240)), "image/png")})
    assert r.status_code == 200 and r.json()["num_persons"] >= 0


def test_pixel_limit_413(monkeypatch):
    monkeypatch.setattr(appmod, "MAX_PIXELS", 100)
    r = client.post("/pose", files={"file": ("a.png", img_bytes(size=(64, 64)), "image/png")})
    assert r.status_code == 413


def test_decompression_bomb_413_not_500(monkeypatch):
    # PIL 임계에 걸려 예외가 나는 경로가 아니라, 우리 픽셀 검사가 먼저 413을 돌려줘야 한다.
    assert appmod.Image.MAX_IMAGE_PIXELS is None
    monkeypatch.setattr(appmod, "MAX_PIXELS", 10)
    r = client.post("/pose/image", files={"file": ("a.png", img_bytes(size=(64, 64)), "image/png")})
    assert r.status_code == 413


def test_content_length_rejected_before_parsing(monkeypatch):
    monkeypatch.setattr(appmod, "MAX_BYTES", 10)
    monkeypatch.setattr(appmod, "BODY_HEADROOM", 0)
    r = client.post("/pose", files={"file": ("a.png", img_bytes(), "image/png")})
    assert r.status_code == 413 and "본문" in r.json()["detail"]


def test_missing_content_length_411():
    def gen():
        yield b"x"
    r = client.post("/pose", content=gen(), headers={"content-type": "multipart/form-data; boundary=a"})
    assert r.status_code == 411
