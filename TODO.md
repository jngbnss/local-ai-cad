# Local AI CAD — 다음 작업

현재 상태: **Phase 1~6 완료**. 다음 정식 단계는 Phase 7이며, 복합 가구 정확도 개선은 별도 트랙 Q로 진행한다.

## 0. Phase 7 시작 전 공간 확보

- [ ] C: 여유 공간을 현재 24.1GB에서 **최소 35GB, 권장 40GB 이상**으로 확보한다.
- [ ] Docker Desktop의 이미지·빌드 캐시·WSL 가상 디스크 위치를 확인한다.
- [ ] 모델 가중치는 Docker 이미지에 넣지 않고 기존 Hugging Face 캐시를 볼륨으로 연결한다.

예상 추가 사용량은 15~25GB다. 빌드 도중 레이어가 중복되므로 24.1GB 상태에서 바로 시작하지 않는다.

## 1. Phase 7 — Docker/WSL2 GPU 패키징

- [ ] WSL2 배포판과 Docker Desktop의 WSL 통합 상태를 확인한다.
- [ ] 컨테이너에서 NVIDIA GPU가 노출되는지 확인한다.
  - `nvidia-smi`
  - `python -c "import torch; print(torch.cuda.is_available())"`
- [ ] `docker/Dockerfile.backend`를 작성한다.
  - Python 3.11
  - CUDA 호환 PyTorch
  - FastAPI, CadQuery/OCP
  - 모델 캐시는 이미지에서 제외
- [ ] `docker/Dockerfile.frontend`를 작성한다.
  - Vite 프로덕션 빌드
  - 정적 파일 서빙 및 `/api` 프록시
- [ ] `docker-compose.yml`을 작성한다.
  - 백엔드 워커 1개 고정
  - GPU 예약
  - 모델 캐시·설계 DB·CAD 아티팩트 볼륨 분리
  - healthcheck 추가
- [ ] `.dockerignore`를 작성해 `.venv`, `node_modules`, 모델 캐시, 아티팩트를 제외한다.
- [ ] `docker compose up --build` 한 번으로 전체 서비스가 실행되는지 확인한다.
- [ ] 컨테이너에서 실제 GPU 프롬프트 → DesignSpec → STL/STEP 생성 E2E를 실행한다.
- [ ] Windows 호스트 대비 모델 적재 시간·추론 시간·VRAM 사용량을 측정한다.
- [ ] 최종 이미지 크기와 디스크 사용량을 기록한다.
- [ ] `docs/phase-7-design.md`와 완료 보고서를 작성한다.

### Phase 7 완료 조건

- [ ] 컨테이너 안에서 `torch.cuda.is_available() == True`다.
- [ ] `docker compose up`만으로 프론트엔드와 백엔드가 실행된다.
- [ ] 실제 GPU CAD 생성과 STL/STEP 다운로드가 성공한다.
- [ ] 모델 캐시가 이미지에 포함되지 않는다.
- [ ] 호스트/컨테이너 성능 비교와 이미지 크기가 문서에 남는다.

## 2. 트랙 Q — 복합 가구 정확도 개선

현재 실제 모델 평가 결과는 1차 16/20(80%), 교정 재시도 포함 18/20(90%)다. 네 다리 책상 두 문항에서 중복 부품 ID를 교정하지 못했다.

- [ ] 실패한 `desk-01`, `desk-02`를 회귀 평가셋으로 고정한다.
- [ ] JSON 문법 제약 디코딩 라이브러리의 Windows/CUDA 호환성을 조사한다.
- [ ] 프롬프트 개선, 문법 제약, LoRA, 더 큰 양자화 모델을 동일 조건으로 비교한다.
- [ ] 각 후보의 유효율·추론 시간·최대 VRAM·디스크 사용량을 기록한다.
- [ ] 20문항 재시도 포함 성공률 목표를 **100%**로 둔다.
- [ ] 결과가 개선된 경우 `experiments/spec_accuracy_report.md`를 갱신한다.

## 3. 후속 품질 개선

- [ ] Three.js를 동적 import로 분리해 프론트엔드 번들 경고(약 790KB)를 줄인다.
- [ ] Starlette `TestClient`의 `httpx` 사용 중단 경고에 맞춰 테스트 클라이언트를 교체한다.
- [ ] API와 프론트엔드에 취소 기능을 추가해 긴 GPU 요청을 중단할 수 있게 한다.
- [ ] 생성 아티팩트와 오래된 설계 이력의 정리 정책을 추가한다.
- [ ] 실제 GPU 서버 10회 연속 설계 생성 장시간 테스트를 자동화한다.

## 참고 자료

- Phase 2~6 완료 근거: `docs/phase-2-6-report.md`
- 실제 모델 정확도: `experiments/spec_accuracy_report.md`
- 전체 로드맵: `docs/roadmap.md`
