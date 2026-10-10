# STATS (현재 상태, 2026-10-10)

| 서비스 | 포트 | 모델 | 크기 | 라이선스 | 컨테이너 테스트 | 실제 가중치 추론 |
|---|---|---|---|---|---|---|
| classification | 8001 | torchvision MobileNetV3-Small | 2.5M params, 9.8MB | BSD-3(코드, 가중치는 미확인) | 12 pass | 미검증(다운로드 403, 랜덤 가중치로 e2e) |
| detection | 8002 | torchvision SSDlite320 MobileNetV3-Large | 3.4M params, 13.4MB | BSD-3(미확인) | 15 pass | 미검증(랜덤 가중치로 e2e) |
| pose | 8003 | Ultralytics YOLO11n-pose | 2.9M params, 6.3MB | **AGPL-3.0** | 15 pass | 검증됨(bus.jpg 4명, 17 keypoints) |
| face | 8004 | OpenCV YuNet + SFace (ONNX) | 약 37MB | MIT / Apache-2.0(미확인) | 13 pass, 1 skip | 검증됨(1장; 타인 구분은 mock만) |
| emotion (ko) | 8005 | GGARA02/kcelectra-korean-emotion (6 클래스, MODEL_ID로 교체) | KcELECTRA-base급(경량 아님) | 미확인 | 10 pass | 미검증(HF 차단) |

## 알려진 한계
- Windows / py311 / CUDA 12.6 / GPU 경로 전부 미검증 (컨테이너는 Linux, py3.13, CPU)
- emotion: 진짜 경량 한국어 감정 모델은 못 찾음. base 크기이며, 더 작은 모델로 교체하려면 MODEL_ID 사용
- pose의 AGPL: 상용/배포 시 의무 발생. 대안 MediaPipe(Apache)는 구현 안 함
- 환경 스크립트 `setup-dev-env.ps1`: Windows 실행 미검증

## 에이전트 정책
메인 Sonnet 5.5 / 구현·검색 Sonnet 5.5·Haiku 5.5 / 리뷰·검증 Opus 5.5 (`.claude/agents/`)
