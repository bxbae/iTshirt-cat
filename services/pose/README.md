# Pose Estimation API (YOLO11n-pose, COCO 17 keypoints)

Ultralytics `yolo11n-pose` (약 2.9M 파라미터, 가중치 약 6.3MB). CPU에서도 실용적, CUDA가 있으면 자동 사용.
**라이선스 주의: Ultralytics는 AGPL-3.0** (상업/비공개 서비스에는 Enterprise 라이선스 필요). 자세한 비교는 `wiki/pose.md`.

## 설치 (Windows, conda env `py311`)
```powershell
conda activate py311
cd services\pose
# torch/torchvision은 이미 CUDA 12.6 빌드가 있으므로 그대로 둔다. ultralytics가 torch를 덮어쓰지 않는지 pip 출력 확인.
pip install ultralytics fastapi "uvicorn[standard]" python-multipart pillow requests pytest httpx
```

## 실행
```powershell
uvicorn app:app --port 8003
```
첫 `/pose` 호출 때 모델을 로드한다. 가중치 `yolo11n-pose.pt`가 현재 디렉터리에 없으면 ultralytics가 GitHub에서 **현재 작업 디렉터리**로 자동 다운로드한다
(`services\pose`에서 실행할 것. `*.pt`는 .gitignore 대상). 다른 위치는 `set POSE_WEIGHTS=C:\path\yolo11n-pose.pt`.
환경변수: `POSE_MAX_BYTES`(기본 10MB), `POSE_MAX_PIXELS`(디코딩 후 최대 픽셀, 기본 40,000,000), `POSE_IMGSZ`(기본 640).

업로드 제한: Content-Length가 `POSE_MAX_BYTES`+64KB를 넘으면 폼 파싱 전에 413으로 거부하며, Content-Length 없는(chunked) POST는 411입니다. 외부 노출 시에는 리버스 프록시(nginx `client_max_body_size`)에서도 제한하세요.

## 엔드포인트
- `GET /health`
- `POST /pose` (multipart, 필드 `file`, 쿼리 `conf`=사람 검출 임계값 기본 0.25, `kp_conf`=이 값 미만 keypoint 제외 기본 0) -> 사람별 bbox/score/17 keypoints(JSON)
- `POST /pose/image` (같은 입력, `kp_conf` 기본 0.3) -> 스켈레톤 오버레이 PNG (헤더 `X-Num-Persons`)
- 오류: 400 빈 파일/이미지 아님, 413 크기/해상도 초과, 411 Content-Length 없음, 422 파라미터 오류, 503 모델 로드/추론 실패

```powershell
curl -X POST "http://127.0.0.1:8003/pose?conf=0.25" -F "file=@people.jpg"
curl -X POST "http://127.0.0.1:8003/pose/image" -F "file=@people.jpg" -o overlay.png
```
응답 예시 (값은 형식 예시):
```json
{"model":"yolo11n-pose","device":"cpu","keypoint_format":"coco17","image_width":810,"image_height":1080,
 "num_persons":1,"persons":[{"bbox":[48,400,244,906],"score":0.89,
 "keypoints":[{"name":"nose","x":142.0,"y":442.0,"score":0.99}, "... 17개 ..."]}]}
```
keypoint 순서: nose, left/right_eye, left/right_ear, left/right_shoulder, elbow, wrist, hip, knee, ankle. 화면 밖/가려진 점은 score가 낮고 좌표가 가장자리에 붙을 수 있으므로 score로 거른다.

## 예시 클라이언트 / 테스트
```powershell
python example_client.py            # GitHub의 bus.jpg 샘플 사용, 실패 시 단색 이미지
python example_client.py my.jpg     # 로컬 파일 또는 URL. 오버레이는 pose_overlay.png로 저장
pytest -q tests
```
