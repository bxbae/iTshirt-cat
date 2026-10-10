# Detection (객체 인식)

## 결정
- 선택: torchvision `ssdlite320_mobilenet_v3_large` (서비스 포트 8002, `services/detection`)
- 이유: BSD-3 라이선스(서비스로 배포해도 AGPL 의무 없음), 작은 가중치, torch/torchvision만으로 동작(추가 의존성 없음), conda env의 torch를 그대로 사용.

## 후보 비교
| 항목 | SSDlite320 MobileNetV3-L | Ultralytics YOLO11n |
|---|---|---|
| COCO box mAP | 21.3 (val2017) | 39.5 (mAP50-95, 640px) |
| 파라미터 | 3.44M | 2.6M |
| 연산량 | 0.58 GFLOPS | 6.5 GFLOPs |
| 가중치 크기 | 13.4MB | 미확인 |
| 라이선스 | BSD-3 (torchvision) | AGPL-3.0 / 상용 Enterprise 별도 |
| 의존성 | torchvision | ultralytics 패키지 |

- 정확도는 YOLO11n이 월등히 높다(39.5 vs 21.3, 단 입력 해상도 640 vs 320 차이). 라이선스 부담이 없고 의존성이 최소인 쪽을 기본으로 골랐다. 정확도가 더 필요하면 YOLO11n으로 교체 가능(AGPL 검토 필요, API 서비스 제공 시 소스 공개 의무가 생길 수 있음).
- 두 모델의 속도는 같은 조건에서 직접 비교하지 않았다(미확인). torchvision 블로그의 CPU 추론 0.0911초는 당시 벤치마크 환경 값이며 이 프로젝트 환경과 무관.

## 구현 메모
- 라벨: `SSDLite320_MobileNet_V3_Large_Weights.DEFAULT.meta["categories"]` (91개, 일부 "N/A"). `label_id`는 COCO 91 인덱스.
- 전처리는 weights.transforms() 사용, 박스는 모델이 원본 해상도 좌표로 반환.
- 모델은 lazy-load + 전역 1회, 추론은 락으로 직렬화.

## 함정
- 가중치는 download.pytorch.org에서 받는다(`~/.cache/torch/hub/checkpoints`). 사내망/오프라인이면 사전 다운로드 필요. 이 컨테이너에서는 403이라 실제 가중치로 추론하지 못했다.
- pip의 `torchvision`이 conda의 CUDA torch를 CPU 빌드로 바꿀 수 있다. torch/torchvision은 같은 인덱스(cu126)에서 함께 설치.
- Windows에서 PIL 기본 폰트로 라벨을 그리므로 한글 라벨은 불가(COCO 영어 라벨 사용).
- 저해상도(320) 모델이라 작은 객체 검출이 약하다.

## 출처
- https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.detection.ssdlite320_mobilenet_v3_large.html (mAP 21.3, 3.44M, 0.58 GFLOPS, 13.4MB)
- https://pytorch.org/blog/torchvision-ssdlite-implementation/
- https://docs.ultralytics.com/models/yolo11 (39.5 mAP, 2.6M, 6.5B FLOPs)
- https://www.ultralytics.com/license (AGPL-3.0 / Enterprise)
- 라이선스 BSD-3(torchvision)는 일반 지식 기반이며 이번에 라이선스 파일로 직접 확인하지 않았다(미확인).
