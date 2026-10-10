# Detection service (포트 8002)

torchvision `ssdlite320_mobilenet_v3_large` (COCO 91 클래스 인덱스, 3.44M params, 가중치 약 13.4MB, BSD-3).
선택 근거와 대안 비교는 `wiki/detection.md` 참고.

## 설치 (Windows, conda env py311)
```powershell
conda activate py311
# torch/torchvision이 아직 없다면 (CUDA 12.6):
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
cd services\detection
pip install -r requirements.txt
```
`requirements.txt`의 `torchvision`은 이미 설치된 torch와 버전이 맞아야 한다. pip가 torch를 CPU 빌드로 덮어쓰면 위 cu126 명령으로 다시 설치.

## 실행
```powershell
uvicorn app:app --port 8002
```
첫 `/detect` 호출 때 가중치(~13MB)를 `%USERPROFILE%\.cache\torch\hub\checkpoints`에 받는다(lazy-load). GPU가 있으면 자동 사용, 강제는 `set DETECTION_DEVICE=cpu`.
환경변수: `DETECTION_DEVICE`(cpu/cuda), `DETECTION_MAX_BYTES`(기본 10MB). `DETECTION_WEIGHTS=none`은 랜덤 가중치(스모크 테스트 전용, 결과 무의미).

## API
- `GET /health`
- `POST /detect` multipart: `file`(이미지), `score_threshold`(0~1, 기본 0.5), `max_detections`(1~300, 기본 100) -> JSON
- `POST /detect/image` 같은 입력 -> 박스가 그려진 PNG (`X-Detection-Count` 헤더)

오류: 400 디코딩 실패/빈 파일, 413 크기 초과, 415 content-type 불가, 422 파라미터 범위 오류, 503 모델 로드/추론 실패(예: 가중치 다운로드 불가).

## curl 예시
```powershell
curl.exe -X POST http://127.0.0.1:8002/detect -F "file=@street.jpg" -F "score_threshold=0.5"
curl.exe -X POST http://127.0.0.1:8002/detect/image -F "file=@street.jpg" -o result.png
```

## 응답 예시
```json
{"model":"ssdlite320_mobilenet_v3_large","width":640,"height":480,"count":1,
 "detections":[{"label":"cat","label_id":17,"score":0.9123,
   "bbox":{"x1":10.2,"y1":30.5,"x2":300.1,"y2":420.0}}]}
```
bbox는 원본 이미지 픽셀 좌표(x1,y1 좌상단 / x2,y2 우하단).

## 예제 클라이언트 / 테스트
```powershell
python example_client.py [이미지경로 또는 URL]   # 인자 없으면 합성 이미지(객체 없음 가능)
python -m pytest -q                              # 모델 mock으로 API 계약 검증
```
