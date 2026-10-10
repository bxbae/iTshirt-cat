# LLM Wiki — 목차
리서치·결정·함정을 주제별로 정리. 새 문서는 여기에 링크한다.

## 모델 서비스별 (선정 근거, 크기, 라이선스, Windows 함정)
- [classification](classification.md)
- [detection](detection.md)
- [pose](pose.md)
- [face](face.md)
- [emotion](emotion.md)

## 공통 교훈
- 업로드 이미지는 디코드 전에 픽셀 수 상한을 검사 (압축폭탄 방어)
- async 엔드포인트에서 동기 추론은 threadpool로
- Windows PowerShell: `curl`은 Invoke-WebRequest 별칭 → `curl.exe` 또는 Invoke-RestMethod, 환경변수는 `$env:X`
- 서비스 테스트는 디렉터리별로 실행 (모듈명 `app` 충돌)
