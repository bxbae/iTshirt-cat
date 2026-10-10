# Emotion (한국어 감정 분류) - 포트 8005

기본 모델: `GGARA02/kcelectra-korean-emotion` (KcELECTRA-base-v2022 파인튜닝, 6 클래스). `MODEL_ID` 환경변수로 교체 가능.
**주의**: 이 모델은 base 급(약 1.1~1.3억 파라미터 추정, 미확인)이라 "초경량"은 아님. 더 작은 한국어 감정 모델은 확인하지 못했다. 자세한 내용은 `wiki/emotion.md`.

## 설치 (Windows, conda env py311)
```powershell
conda activate py311
cd services\emotion
# torch가 없다면 CUDA 12.6 빌드 먼저
pip install torch --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt
```

## 실행
```powershell
uvicorn app:app --port 8005
# 다른 모델: $env:MODEL_ID="org/model"; uvicorn app:app --port 8005
# 멀티라벨(sigmoid) 모델: $env:MULTI_LABEL="1"
```
첫 `/predict` 호출 때 모델을 HF에서 다운로드(lazy-load, 이후 전역 재사용). 실패 시 503.
환경변수: `MODEL_ID`, `MULTI_LABEL`, `MAX_TEXTS`(64), `MAX_CHARS`(1000), `MAX_LENGTH`(256).

## 호출
```powershell
Invoke-RestMethod http://127.0.0.1:8005/health
# 한국어 본문은 반드시 UTF-8 바이트로 전송 (PowerShell 5.1 기준 안전한 방식)
Invoke-RestMethod -Uri http://127.0.0.1:8005/predict -Method Post `
  -ContentType 'application/json; charset=utf-8' `
  -Body ([Text.Encoding]::UTF8.GetBytes('{"texts":["오늘 승진했어! 너무 기뻐"],"top_k":3}'))
python example_client.py   # 가장 권장되는 정식 예시
```
참고: Windows PowerShell 5.1에서 `curl`은 `Invoke-WebRequest` 별칭이라 `-X/-H/-d`가 동작하지 않고, `curl.exe`로 한글 JSON을 명령행에 직접 넘기면 cp949로 전송될 수 있습니다. curl.exe를 쓰려면 JSON을 UTF-8 파일로 저장해 `curl.exe -X POST http://127.0.0.1:8005/predict -H "Content-Type: application/json" --data-binary "@body.json"` 로 보내세요.
응답 형태 (라벨명은 모델의 id2label에 따름; 값은 형식 예시):
```json
{"model":"GGARA02/kcelectra-korean-emotion","device":"cuda",
 "results":[[{"label":"<라벨>","score":0.93},{"label":"<라벨>","score":0.03}]]}
```
검증 오류(빈 문자열, 너무 긴 텍스트, top_k 범위 밖)는 422.

## 테스트
`pytest tests` (모델 mock, 다운로드 불필요).
