# 이미지 분류 (services/classification, 포트 8001)

## 선택: torchvision MobileNetV3-Small (ImageNet-1k)
| 항목 | 값 | 출처/확인 |
|---|---|---|
| 파라미터 | 2,542,856 | 설치된 torchvision 0.29.1 `Weights.meta`에서 직접 확인 |
| 가중치 파일 | 약 9.83 MB | 위와 동일 (`_file_size`) |
| ImageNet top-1 / top-5 | 67.668 / 87.402 | 위와 동일 (`_metrics`) |
| 가중치 URL | download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth | 위와 동일; 이 컨테이너에선 접근 403이라 다운로드 미확인 |
| 코드 라이선스 | BSD-3-Clause (torchvision) | 기억 기반, 미확인 |
| 가중치 라이선스 | 명시적 별도 라이선스 미확인 (ImageNet 학습 데이터 약관은 비상업/연구 제한 논란이 있어 상업 사용 전 확인 필요) | 미확인 |
| 입력 전처리 | resize 256 -> center crop 224, ImageNet 정규화 | `Weights.transforms()` |

## 선택 근거
- 파라미터 2.5M, 가중치 10MB로 CPU에서도 실용적이며 torchvision 내장이라 의존성 추가가 없다 (torch/torchvision만).
- 대안(미검증): MobileNetV3-Large(5.4M, 더 정확), EfficientNet-B0, ResNet18(11.7M). 정확도가 더 필요하면 `mobilenet_v3_large`로 교체(코드 두 줄).

## Windows 함정
- `pip install -r requirements.txt` 시 torch를 핀하면 CUDA 빌드가 CPU 빌드로 덮일 수 있어 핀하지 않음.
- 가중치 캐시: `%USERPROFILE%\.cache\torch\hub\checkpoints`. 첫 호출이 느린 것은 다운로드 때문.
- uvicorn `--reload`는 Windows에서 모델을 매번 재로드하므로 개발 외엔 쓰지 않는다.
- 이미지는 RGBA/팔레트 PNG일 수 있어 `convert("RGB")` 필수 (구현됨).

## 검증 상태 (2026-10-10, Linux 컨테이너, Python 3.13, torch 2.14.1 cu130)
- 실행해서 통과: pytest 10개 (모델 mock으로 API 계약, 무작위 가중치 실제 torch 경로 1개), 실제 uvicorn 기동 + example_client.py 호출 200 응답.
- 미검증: 실제 ImageNet 가중치 다운로드 및 분류 정확도(pytorch.org 차단), Windows/CUDA 12.6 실행, GPU 경로, Python 3.11.
