# Face (얼굴 인식)

## 결정
- 선택: OpenCV Zoo의 YuNet(검출, `face_detection_yunet_2023mar.onnx`) + SFace(임베딩, `face_recognition_sface_2021dec.onnx`), `cv2.FaceDetectorYN` / `cv2.FaceRecognizerSF` 사용 (`services/face`, 포트 8004).
- 이유: torch 불필요(OpenCV만), 합계 약 37MB, CPU에서 실용적, 추가 의존성 최소.

## 파일 정보 (직접 다운로드로 확인, 2026-10-10)
| 모델 | 크기 | sha256 |
|---|---|---|
| YuNet 2023mar | 232,589 B | 8f2383e4...04552fa4 |
| SFace 2021dec | 38,696,353 B | 0ba9fbfa...e04e79 |
- 다운로드 URL: `https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/<dir>/<file>` (이 컨테이너에서 200 확인). `github.com/.../raw/main/...`은 이 컨테이너 프록시에서 403(Git LFS 포인터 문제와 별개로 프록시 차단)이라 2순위 폴백으로만 둠. Windows 로컬에서의 접근성은 미확인.
- sha256은 내가 받은 파일의 해시이며 공식 게시 해시와의 대조는 하지 않았다(미확인).

## 구현 메모
- 검출 결과 15값: x,y,w,h + 랜드마크 5점(우안, 좌안, 코, 우입꼬리, 좌입꼬리) + score. 입력 크기는 이미지마다 `setInputSize`로 지정 -> 전역 객체 상태 변경이라 락으로 직렬화.
- 긴 변 1280px 초과 이미지는 축소해서 검출 후 좌표를 원본으로 환산, 임베딩은 원본에서 alignCrop.
- 임베딩 128차원, L2 정규화 후 내적 = 코사인 유사도. 임계값 0.363(코사인) 은 OpenCV zoo 샘플의 권장값으로 알고 있으나 공식 문서로 이번에 재확인하지 않음(미확인).
- 갤러리는 메모리 dict(영속화 없음).

## 라이선스 (미확인 포함)
- YuNet: MIT, SFace: Apache-2.0 로 알고 있으나 repo의 LICENSE를 직접 확인하지 않았다(미확인). 배포 전 opencv_zoo 각 모델 폴더의 LICENSE 확인 필요.

## 함정
- `FaceDetectorYN`은 OpenCV 4.5.4+ 에서 제공, 2023mar 모델은 4.8+ 권장 -> requirements는 `opencv-python-headless>=4.8`. 컨테이너 테스트는 OpenCV 5.0.0 이었고 4.x에서는 실행해보지 않았다.
- `opencv-python`과 `opencv-python-headless`를 같이 설치하면 충돌(실제로 같은 환경에서 import 시 Bus error를 겪음, 재설치로 해결). 하나만 둘 것.
- OpenCV 5.0 로그에 "Targets are not supported by the new graph engine" 경고가 뜨나 동작에는 영향 없음.
- GPU(CUDA) 사용은 pip의 OpenCV 휠이 CUDA DNN 미지원이라 CPU 전용. 모델이 작아 문제 없음.
- `FaceRecognizerSF.create`는 파일 경로만 받음: Windows 사용자 경로에 한글이 있으면 모델 로드 실패 가능(미확인) -> `FACE_MODEL_DIR`을 ASCII 경로로 지정.
- 얼굴 없는 이미지는 422. 정확도(LFW 등) 수치는 직접 측정하지 않았다(미확인).
- 생체정보라 개인정보 이슈.

## 출처
- https://github.com/opencv/opencv_zoo (models/face_detection_yunet, models/face_recognition_sface)
- OpenCV docs: cv::FaceDetectorYN, cv::FaceRecognizerSF
