# Face Service (YuNet 검출 + SFace 임베딩) - 포트 8004

OpenCV `cv2.FaceDetectorYN`(YuNet 2023mar, 약 0.23MB) + `cv2.FaceRecognizerSF`(SFace 2021dec, 약 37MB). torch 불필요, CPU 전용(OpenCV DNN).
ONNX 파일은 첫 요청 시 `services/face/models/`에 자동 다운로드(sha256 검증). 환경변수 `FACE_MODEL_DIR`로 위치 변경 가능.

## 설치 (Windows, conda env py311)
```powershell
conda activate py311
cd services\face
pip install -r requirements.txt
uvicorn app:app --port 8004
```
오프라인이면 두 .onnx를 https://github.com/opencv/opencv_zoo (models/face_detection_yunet, models/face_recognition_sface; Git LFS 파일)에서 받아 `models\`에 직접 넣는다. 파일명/sha256이 다르면 재다운로드를 시도한다.

## 엔드포인트
| 메서드 | 경로 | 입력 | 설명 |
|---|---|---|---|
| GET | /health | - | 상태, 갤러리 크기, 임계값 |
| POST | /detect | file, score_threshold(옵션, 기본 0.7) | 얼굴 박스/랜드마크 5점/점수 |
| POST | /embed | file | 가장 큰 얼굴의 128차원 L2 정규화 임베딩 |
| POST | /verify | file1, file2 | 동일인 여부 + 코사인 유사도(임계 0.363) |
| POST | /gallery/register | name, file | 메모리 갤러리에 등록(같은 이름은 덮어씀) |
| POST | /gallery/identify | file | 가장 비슷한 등록자 (임계 미만이면 match=false) |
| GET / DELETE | /gallery, /gallery/{name} | - | 목록 / 삭제 |

오류: 400 잘못된 이미지, 413 10MB 초과, 422 얼굴 없음/잘못된 파라미터, 409 빈 갤러리.
갤러리는 프로세스 메모리에만 있다(재시작 시 소멸, 영속화 없음).

## curl 예시
```bash
curl -F "file=@me.jpg" http://127.0.0.1:8004/detect
curl -F "file1=@a.jpg" -F "file2=@b.jpg" http://127.0.0.1:8004/verify
curl -F "name=alice" -F "file=@alice.jpg" http://127.0.0.1:8004/gallery/register
curl -F "file=@unknown.jpg" http://127.0.0.1:8004/gallery/identify
```
(PowerShell에서는 `curl.exe`를 사용)

## 응답 예시
```json
// POST /detect
{"image":{"width":512,"height":512},"count":1,"faces":[{"box":{"x":207.8,"y":182.5,"w":145.9,"h":206.9},
 "landmarks":{"right_eye":[..,..],"left_eye":[..,..],"nose":[..,..],"right_mouth":[..,..],"left_mouth":[..,..]},"score":0.909}]}
// POST /verify
{"same_person":true,"cosine_similarity":1.0,"threshold":0.363,"face1":{...},"face2":{...}}
```

## 예시 클라이언트 / 테스트
```powershell
python example_client.py                 # 공개 샘플(lena.jpg) 자동 다운로드
python example_client.py a.jpg b.jpg     # 내 사진 두 장 비교
pytest -q tests                          # 모델 mock, 다운로드 불필요
$env:FACE_TEST_IMAGE="me.jpg"; pytest -q tests   # 실제 모델 테스트 포함
```

## 설정 (환경변수)
`FACE_MODEL_DIR`, `FACE_COSINE_THRESHOLD`(기본 0.363), `FACE_MAX_BYTES`(10MB), `FACE_MAX_SIDE`(검출 시 축소 기준 1280px).

## 주의
- **OpenCV 배포판**: 이 프로젝트는 conda env 하나를 공유하며 pose의 ultralytics가 `opencv-python`을 설치한다. face도 `opencv-python`을 쓴다. `opencv-python-headless`가 이미 깔려 있으면 `pip uninstall -y opencv-python opencv-python-headless` 후 `pip install "opencv-python>=4.8"` 하나만 재설치할 것(둘이 섞이면 `import cv2`가 깨진다).
- **한글 경로(Windows)**: OpenCV DNN은 경로를 ANSI로 열어 사용자 폴더에 한글이 있으면 로드가 실패할 수 있다. 검출기는 메모리 버퍼로 로드하지만, 인식기(SFace)는 경로만 지원하므로 `FACE_MODEL_DIR`을 ASCII 경로로 지정할 것: `$env:FACE_MODEL_DIR="C:\face_models"`. 모델 로드 실패 시 503과 안내 메시지를 반환한다.
- 업로드 제한: 파일 `FACE_MAX_BYTES`(10MB), 해상도 `FACE_MAX_PIXELS`(기본 4천만 픽셀) 초과 시 413.
- 사진 속 사람은 얼굴 인식 시 개인정보(생체정보)이므로 법적/윤리적 사용 범위를 확인할 것.
- 임계값 0.363은 OpenCV zoo 권장값이며 데이터에 따라 조정 필요.
