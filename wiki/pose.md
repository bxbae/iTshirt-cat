# Pose estimation (services/pose, 포트 8003)

## 선택: Ultralytics YOLO11n-pose (COCO 17 keypoints, 다인 지원)
| 항목 | 값 | 출처/확인 |
|---|---|---|
| 파라미터 | 2,874,462 | 이 컨테이너에서 ultralytics 8.4.175로 가중치 로드 후 직접 계산 |
| 가중치 파일 | 6,255,593 bytes (~6.3MB) | `github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt` 직접 다운로드 확인 |
| 출력 | 사람별 bbox + 17 keypoints(x,y,score) | 실제 호출로 확인 |
| 코드/가중치 라이선스 | AGPL-3.0 (Enterprise 라이선스 별도 판매) | 기억 기반, 이 세션에서 라이선스 페이지 미확인. 사용 전 ultralytics.com/license 확인 필요 |
| 정확도(COCO pose mAP) | 미확인 | 공식 문서 수치를 이 세션에서 확인하지 못함 |

## 후보 비교
| 후보 | 장점 | 단점 | 판단 |
|---|---|---|---|
| YOLO11n-pose | 다인(multi-person) 한 번에, torch 기반이라 기존 env 재사용, GPU 자동, 설치 단순 | AGPL-3.0: 네트워크 서비스로 제공 시 소스 공개 의무 가능, 상업은 유료 라이선스 | 선택 (프로젝트가 로컬/학습용) |
| MediaPipe Pose / PoseLandmarker | Apache-2.0(기억 기반, 미확인), 매우 가벼움, 33 landmarks | 레거시 Pose는 단일 인물 중심, 다인은 Tasks API `PoseLandmarker(num_poses)` + 별도 .task 모델 파일 필요(다운로드 미확인), torch 미사용이라 GPU 이점 없음, Windows에서 protobuf/numpy 버전 충돌 보고 있음(미확인) | 대안. 상업 라이선스가 필요하면 교체 후보 |
| torchvision keypointrcnn_resnet50_fpn | BSD, torch 내장 | 무겁다(수십M 파라미터) | 경량 요건 미충족 |
pip 상 `mediapipe` 패키지가 PyPI에서 내려받아지는 것만 확인(실행·정확도 미확인).

## 구현 메모
- 모델은 `load_model()`에서 전역 1회 lazy-load, 락으로 보호. 장치는 `torch.cuda.is_available()`로 자동 선택.
- `run_inference`를 테스트에서 mock 하여 API 계약을 검증. 오버레이는 PIL로 그려 별도 시각화 의존성 없음.
- 응답 keypoint는 가려진 점도 좌표를 낸다(score 낮음). `kp_conf`로 필터.

## Windows 함정
- 가중치가 없으면 ultralytics가 **현재 작업 디렉터리**에 `yolo11n-pose.pt`를 내려받는다. 항상 `services\pose`에서 실행하거나 `POSE_WEIGHTS`로 경로 지정. 첫 호출 지연은 다운로드 때문.
- `pip install ultralytics`가 torch 의존성을 만족시키는 과정에서 기존 CUDA 빌드를 CPU 빌드로 덮을 수 있음: torch가 이미 있으면 설치 후 `python -c "import torch;print(torch.cuda.is_available())"`로 확인 (이 현상 자체는 Windows에서 미확인, 일반적 주의).
- `opencv-python`은 ultralytics 의존성으로 같이 설치됨. 서버 환경이면 headless 변형과 충돌하지 않게 하나만 둔다.
- uvicorn `--reload`는 모델을 매번 재로드.

## 검증 상태 (2026-10-10, Linux 컨테이너, Python 3.13, torch 2.14.1, ultralytics 8.4.175)
- 실행해서 통과: pytest 11개 (mock 10개 + 실제 yolo11n-pose 가중치로 단색 이미지 추론 1개).
- 실행해서 확인: 실제 uvicorn 기동 + `example_client.py`로 ultralytics 번들 `bus.jpg` 호출 -> /pose 200, 사람 4명 검출(CPU), /pose/image 200 PNG 반환. keypoint 위치가 사람 위치와 대응하는지 오버레이 이미지를 눈으로 보지는 않음(좌표/score 수치만 확인).
- 미검증: Windows/CUDA 12.6/GPU 경로, Python 3.11, MediaPipe 대안 구현, 정확도 벤치마크, AGPL 조건의 정확한 해석.
