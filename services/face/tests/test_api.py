"""API contract tests. Models are mocked (no download needed); one optional real-model test.

Run from services/face:  pytest -q
Real-model test: set FACE_TEST_IMAGE=<path to a jpg with one face> (models auto-download).
"""
import os
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as face_app  # noqa: E402

client = TestClient(face_app.app)


def png(w=200, h=100) -> bytes:
    ok, buf = cv2.imencode(".png", np.full((h, w, 3), 128, np.uint8))
    return buf.tobytes()


def fake_face(x=10, y=20, w=50, h=60, score=0.95):
    return np.array([[x, y, w, h, 20, 30, 40, 30, 30, 40, 22, 50, 38, 50, score]], np.float32)


@pytest.fixture
def mocked(monkeypatch):
    """Embedding depends on image width so different images give different vectors."""
    def det(img, threshold=None):
        return fake_face() if img.shape[1] != 7 else np.zeros((0, 15), np.float32)

    def emb(img, face):
        rng = np.random.default_rng(img.shape[1])
        v = rng.normal(size=128).astype(np.float32)
        return v / np.linalg.norm(v)

    monkeypatch.setattr(face_app, "_detect", det)
    monkeypatch.setattr(face_app, "_embed", emb)
    face_app._gallery.clear()
    yield


def files(b, key="file"):
    return {key: ("a.png", b, "image/png")}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_detect(mocked):
    r = client.post("/detect", files=files(png()))
    j = r.json()
    assert r.status_code == 200 and j["count"] == 1
    assert j["image"] == {"width": 200, "height": 100}
    assert set(j["faces"][0]) == {"box", "landmarks", "score"}
    assert len(j["faces"][0]["landmarks"]) == 5


def test_detect_no_face(mocked):
    r = client.post("/detect", files=files(png(w=7)))
    assert r.status_code == 200 and r.json()["count"] == 0


def test_invalid_image_and_empty(mocked):
    assert client.post("/detect", files=files(b"not an image")).status_code == 400
    assert client.post("/detect", files=files(b"")).status_code == 400
    assert client.post("/detect").status_code == 422


def test_too_large(mocked, monkeypatch):
    monkeypatch.setattr(face_app, "MAX_BYTES", 10)
    assert client.post("/detect", files=files(png())).status_code == 413


def test_pixel_bomb_rejected(mocked):
    import struct, zlib
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    w = h = 30000
    raw = zlib.compress(b"\x00" * (w * 3 + 1), 9)  # header claims 30000x30000; body is not needed for the probe
    bomb = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", raw) + chunk(b"IEND", b""))
    r = client.post("/detect", files=files(bomb))
    assert r.status_code == 413 and "too large" in r.json()["detail"]


def test_probe_size_formats():
    assert face_app._probe_size(png(200, 100)) == (200, 100)
    ok, jpg = cv2.imencode(".jpg", np.zeros((60, 90, 3), np.uint8))
    assert face_app._probe_size(jpg.tobytes()) == (90, 60)
    ok, bmp = cv2.imencode(".bmp", np.zeros((60, 90, 3), np.uint8))
    assert face_app._probe_size(bmp.tobytes()) == (90, 60)
    ok, wp = cv2.imencode(".webp", np.zeros((60, 90, 3), np.uint8))
    assert face_app._probe_size(wp.tobytes()) == (90, 60)


def test_model_load_failure_is_503_and_cached(monkeypatch):
    calls = []
    def boom(key):
        calls.append(key)
        raise RuntimeError("no network")
    monkeypatch.setattr(face_app, "_ensure_model", boom)
    monkeypatch.setattr(face_app, "_detector", None)
    monkeypatch.setattr(face_app, "_load_error", None)
    r1 = client.post("/detect", files=files(png()))
    r2 = client.post("/detect", files=files(png()))
    assert r1.status_code == 503 and r2.status_code == 503 and len(calls) == 1


def test_bad_threshold(mocked):
    r = client.post("/detect", files=files(png()), data={"score_threshold": "2"})
    assert r.status_code == 422


def test_embed(mocked):
    j = client.post("/embed", files=files(png())).json()
    assert j["dim"] == 128 and len(j["embedding"]) == 128
    assert abs(np.linalg.norm(j["embedding"]) - 1) < 1e-4


def test_embed_no_face(mocked):
    assert client.post("/embed", files=files(png(w=7))).status_code == 422


def test_verify_same_and_different(mocked):
    same = client.post("/verify", files={**files(png(200), "file1"), **files(png(200), "file2")}).json()
    assert same["same_person"] is True and same["cosine_similarity"] > 0.99
    diff = client.post("/verify", files={**files(png(200), "file1"), **files(png(201), "file2")}).json()
    assert diff["same_person"] is False


def test_gallery_flow(mocked):
    assert client.post("/gallery/identify", files=files(png(200))).status_code == 409
    r = client.post("/gallery/register", files=files(png(200)), data={"name": "alice"})
    assert r.status_code == 200 and r.json()["gallery_size"] == 1
    client.post("/gallery/register", files=files(png(201)), data={"name": "bob"})
    j = client.post("/gallery/identify", files=files(png(200))).json()
    assert j["match"] and j["name"] == "alice"
    j = client.post("/gallery/identify", files=files(png(300))).json()
    assert j["match"] is False and j["name"] is None
    assert client.get("/gallery").json()["names"] == ["alice", "bob"]
    assert client.delete("/gallery/alice").status_code == 200
    assert client.delete("/gallery/alice").status_code == 404
    assert client.post("/gallery/register", files=files(png()), data={"name": "  "}).status_code == 422


@pytest.mark.skipif(not os.environ.get("FACE_TEST_IMAGE"), reason="set FACE_TEST_IMAGE to run with real models")
def test_real_models():
    data = Path(os.environ["FACE_TEST_IMAGE"]).read_bytes()
    j = client.post("/detect", files=files(data)).json()
    assert j["count"] >= 1
    v = client.post("/verify", files={**files(data, "file1"), **files(data, "file2")}).json()
    assert v["same_person"] and v["cosine_similarity"] > 0.99
