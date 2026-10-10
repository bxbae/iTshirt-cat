# Image Classification API (MobileNetV3-Small, ImageNet-1k)

torchvision `mobilenet_v3_small` (2.54M 파라미터, 가중치 약 9.8MB). CPU에서도 실용적, GPU(CUDA)가 있으면 자동 사용.

## 설치 (Windows, conda env `py311`)
```powershell
conda activate py311
cd services\classification
# torch/torchvision은 이미 CUDA 12.6 빌드가 있으므로 그대로 두고 나머지만 설치
pip install fastapi "uvicorn[standard]" python-multipart pillow requests pytest httpx
# torch가 없다면: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

## 실행
```powershell
uvicorn app:app --port 8001
```
첫 `/predict` 호출 때 모델을 로드하며 ImageNet 가중치(~9.8MB)를 `%USERPROFILE%\.cache\torch\hub\checkpoints`에 자동 다운로드한다.
오프라인 스모크 테스트: PowerShell은 `$env:CLS_WEIGHTS="none"` (cmd.exe는 `set CLS_WEIGHTS=none`) 후 uvicorn 실행 (무작위 가중치, 라벨은 class_N; 결과는 의미 없음).

## 엔드포인트
- `GET /health` -> `{"status":"ok","model":"mobilenet_v3_small","loaded":false,"device":null}`
- `POST /predict?top_k=5` (multipart, 필드명 `file`, top_k 1..20). 오류: 400 빈 파일/이미지 아님, 413 크기 초과(파일 기본 10MB `CLS_MAX_BYTES`, 해상도 기본 40M 픽셀 `CLS_MAX_PIXELS`), 422 파라미터 오류, 503 모델 로드/추론 실패.

```powershell
curl.exe -X POST "http://127.0.0.1:8001/predict?top_k=3" -F "file=@cat.jpg"
```
응답 예시(형식 예시이며 실제 확률값이 아님):
```json
{"model":"mobilenet_v3_small","device":"cuda","top_k":3,
 "predictions":[{"label":"tabby","index":281,"probability":0.62},
                {"label":"tiger cat","index":282,"probability":0.20},
                {"label":"Egyptian cat","index":285,"probability":0.08}]}
```

## 예시 클라이언트 / 테스트
```powershell
python example_client.py            # 코드로 만든 단색 이미지 전송
python example_client.py cat.jpg    # 파일 또는 URL
python -m pytest tests -q
```
