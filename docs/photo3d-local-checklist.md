# 로컬 GPU 사진 3D 체크리스트

## 경계

- [x] `C:\3-design`의 5면 정합·Hunyuan 로컬 provider·메시/CAD 구분을 검토했다.
- [x] 사진 생성 결과를 GLB 삼각형 메시로 명시하고 STEP·치수 CAD로 오인시키지 않는다.
- [x] 외부 Hugging Face Inference API 대신 로컬 `Hunyuan3D-2mv` CUDA 서버를 사용한다.
- [x] 공개 모델 가중치는 최초 다운로드 후 Hugging Face 로컬 캐시에서 재사용한다.
- [x] Hunyuan3D-2 비상업 라이선스와 상용 배포 검토 필요성을 문서화했다.

## API·UI

- [x] 정면 필수, 후면·좌측·우측 선택 업로드 계약을 제공한다.
- [x] JPEG/PNG/WebP, 10MB·4096² 제한과 EXIF 방향 보정을 적용한다.
- [x] 기존 알파를 보존하고 불투명 사진은 테두리 배경색으로 전경을 분리한다.
- [x] 로컬 서버 health, 연결 실패, GPU 생성 실패, 손상 GLB를 구분한다.
- [x] GLB를 안전한 임의 artifact 이름으로 저장한다.
- [x] 기존 Three.js 뷰어가 STL과 GLB를 각각 올바른 up-axis로 표시한다.
- [x] 별도 venv 설치와 RTX 4050 6GB에서 검증한 native CUDA 실행 스크립트를 제공한다.

## 검증

- [x] 친구 프로젝트 원본 테스트 25/25, TypeScript, CLI, CAD 빌드가 통과했다.
- [x] RTX 4050 6GB에서 로컬 Hunyuan health가 준비 상태가 됐다.
- [x] 실제 로컬 GPU 생성이 유효 GLB를 반환하고 통합 API·Edge 브라우저에 표시됐다.
- [x] local-ai-cad 백엔드 70개 테스트와 프론트엔드 빌드가 통과했다.
## 의도적으로 제외

- [x] 생성 메시를 CAD B-rep 또는 STEP이라고 표시하지 않는다.
- [x] 6GB GPU에서 Qwen 1.5B와 Hunyuan shape 모델의 동시 상주를 지원한다고 주장하지 않는다.
- [x] 텍스처 생성은 16GB 이상 VRAM 요구 범위라 현재 RTX 4050 경로에서 제외한다.
