# Local AI CAD

자연어로 CAD를 설계하는 로컬 AI 도구. **외부 LLM API를 쓰지 않고** 이 PC의 GPU에서 모델을 직접 실행한다.

- 전체 단계 로드맵: `docs/roadmap.md`
- 현재 진행 현황과 인수인계: `STATUS.md`
- 앞으로의 체크리스트: `TODO.md`
- 현재 단계: **Phase 1~6 + Track D 구현 완료** — 자연어/2D 도면 → 편집 → 3D → STL/STEP
- Phase 1 상세 설계: `docs/phase-1-design.md`
- 2D 도면 이미지 → 3D CAD 설계: `docs/track-d-2d-drawing-import-design.md`
- Track D 단계별 검증: `docs/track-d-checklist.md`
- Track D 측정/운영 판정: `docs/track-d-operations-decision.md`
- Track D 오류 기록: `docs/track-d-errors.md`

## MVP 실행

백엔드와 프론트엔드를 각각 한 터미널에서 실행한다.

```powershell
# 터미널 1: 실제 로컬 GPU 모델
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m app.main

# 터미널 2
cd frontend
npm.cmd run dev
```

브라우저에서 `http://127.0.0.1:5173`을 연다. **2D 도면 가져오기** 탭에서는
PNG/JPEG/WebP 업로드 → 분석 영역 선택 → 외곽선·구멍 편집 → 두 기준점과 실제 길이
확인 → 돌출 깊이 입력 → 3D 생성 순서로 사용한다. 이 경로는 배경·원근·인쇄 문자가 없는
단일 정면 선 도면용이며 제품 사진에서 정확한 CAD를 자동 복원하지 않는다. OCR 치수는
CPU에서 후보만 제시하며 사용자가 `기준 길이로 사용`을 누르기 전에는 적용되지 않는다.

**3면 CAD 복원** 탭에서는 정면도(X×Z), 평면도(X×Y), 우측면도(Y×Z)를 각각
업로드하고 공통 가로·깊이·높이를 입력한다. 서버는 세 실루엣을 직교 방향으로 돌출한 뒤
교집합을 계산해 편집 가능한 `orthographic_intersection` 설계와 STEP/STL을 만든다.
현재 베타는 깨끗한 실루엣과 관통 구멍을 지원하며 숨은선·포켓·재투영 비교는 후속 단계다.

**사진 3D · GPU** 탭은 정면과 선택적인 후면·좌측·우측 사진을
`Hunyuan3D-2mv`에 보내 GLB 삼각형 메시를 만든다. 추론은 `127.0.0.1:8090`의
별도 로컬 CUDA 프로세스에서 실행되며 Hugging Face Inference API나 사용량을
소비하지 않는다. 결과는 치수 기반 CAD 솔리드가 아니므로 STEP과 Boolean 편집은
제공하지 않는다.

```powershell
# 최초 1회: 별도 venv와 공개 모델 저장소 설치
.\scripts\setup_hunyuan_local.ps1

# 사진 3D 서버: RTX 4050 6GB 실측 경로
.\.local\hunyuan3d\.venv\Scripts\python.exe .\scripts\hunyuan_local_server.py `
  --repo .\.local\hunyuan3d\Hunyuan3D-2
```

6GB GPU에는 Qwen과 Hunyuan shape 모델을 동시에 상주시킬 여유가 없다. 사진 3D를
사용할 때는 Qwen 백엔드를 종료한 뒤 `LOCAL_AI_CAD_USE_MOCK=1`로 백엔드만 다시
실행한다. 사진 생성을 마치면 Hunyuan 서버를 종료하고 실제 Qwen 백엔드를 재시작한다.
모델 가중치는 최초 한 번만 내려받고 이후 로컬 캐시에서 읽는다.

Hunyuan3D-2 코드와 모델은 Tencent의 **비상업 라이선스** 조건을 따른다. 상용
서비스에 배포하기 전 원 저장소의 최신 라이선스를 별도로 검토해야 한다.

GPU 모델 없이 전체 흐름만 빠르게 확인하려면 백엔드 실행 전에
`$env:LOCAL_AI_CAD_USE_MOCK = "1"`을 지정한다. 도면 분석과 CadQuery 생성은 mock이
아니며 텍스트 설계의 LLM 호출만 mock으로 바뀐다.

실제 모델 20문항 평가는 1차 80%, 교정 재시도 포함 90%였다. 상세 결과는
`experiments/spec_accuracy_report.md`에 있다. Track D는 합성 30개 입력에서 30/30
통과했지만 사용자가 제공한 실제 도면 10개 검증은 입력 부재로 완료 처리하지 않았다.
Docker/WSL2 패키징은 Phase 7, 복합 가구 정확도 개선은 트랙 Q다.

---

## Phase 1 완료 보고

2026-10-14 이 머신에서 실측한 값이다. 추정치 없음.

### 실행 환경

| 항목 | 값 |
|---|---|
| OS | Windows 11 Pro, x64 |
| GPU | NVIDIA GeForce RTX 4060 (8,188 MiB, compute capability 8.9) |
| 드라이버 | 591.86 (CUDA 상한 13.1) |
| Python | 3.11.9 (`.venv`) |
| torch | 2.14.1+cu130 (`torch.version.cuda` = 13.0) |
| transformers / accelerate | 4.57.6 / 1.15.0 |
| 모델 | `Qwen/Qwen2.5-1.5B-Instruct` |

### 측정값

프롬프트: `가로 120cm 책상을 설계하기 위한 핵심 치수를 알려줘.` / FP16 / CUDA / `max_new_tokens=256` / sampling off

| 요청 | load_seconds | inference_seconds | input_tokens | output_tokens | peak_vram_mib |
|---|---|---|---|---|---|
| 1회차 | 11.705 | 21.097 | 52 | 256 | 2963.8 |
| 2회차 | **0.0** | 19.848 | 52 | 256 | 2963.8 |

- 2회차 `load_seconds=0.0`, `model_load_count=1` → **프로세스당 모델 1회 로드** 확인.
- 두 요청의 생성 텍스트가 동일 → sampling off 결정적 기준선 확인.
- 종료 코드 0, 한국어 생성 텍스트 관찰됨.
- 가중치 FP16 약 2.9 GiB. 8 GiB VRAM에서 데스크톱 프로세스와 공존 가능하나 여유는 크지 않다 (아래 주의 참조).

### 오류 경계 실측

| 상황 | 재현 방법 | 종료 코드 | 결과 |
|---|---|---|---|
| 구성 오류 | `LOCAL_AI_CAD_MODEL_ID=qwen25` | 2 | `[구성 오류] ... owner/name 형태여야 합니다` |
| CUDA 미인식 | `CUDA_VISIBLE_DEVICES=-1` | 3 | `[CudaUnavailableError]` + torch 빌드 정보. **CPU 폴백 없음** |
| 모델 다운로드 실패 | 존재하지 않는 저장소 ID | 4 | `[ModelDownloadError]` — 추론 실패와 분리 |
| GPU OOM | 브라우저 등으로 VRAM이 점유된 상태에서 로드 | 5 | 요청 실패 처리. 캐시를 비워 성공을 가장하지 않음 |

OOM(코드 5)은 가정이 아니라 실제로 발생했다. 브라우저·Electron 앱이 VRAM을 5 GiB 넘게 점유한 순간 모델 로드가 실패했고, VRAM이 확보된 뒤 같은 명령이 성공했다.

> **주의**: 추론 전 `nvidia-smi` 로 여유 VRAM을 확인하라. 여유가 3.5 GiB 미만이면 GPU를 쓰는 브라우저·게임 런처를 먼저 닫아야 한다.

---

## 설치

Python 3.11이 필요하다. 시스템에 없으면 사용자 범위로 설치한다.

```powershell
winget install --id Python.Python.3.11 --scope user --exact
```

`python` 이 Microsoft Store 별칭 스텁을 가리킬 수 있으므로 절대 경로로 가상환경을 만든다.

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable)"   # .venv 내부인지 확인
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
```

`requirements.lock` 은 PyTorch 공식 CUDA 13 인덱스를 포함한다. CUDA Toolkit 별도 설치는 필요 없다.

## 사용

```powershell
$env:PYTHONPATH = "backend"

# 1. 환경 진단 — 추론하지 않고 사실만 보고한다
.\.venv\Scripts\python.exe -m app.ai.cli diagnose

# 2. Mock 경로 점검 — 모델을 받지 않는다. GPU 성능 지표가 아니다
.\.venv\Scripts\python.exe -m app.ai.cli infer --mock

# 3. 실제 GPU 추론 (첫 실행은 가중치 약 3 GiB 다운로드)
.\.venv\Scripts\python.exe -m app.ai.cli infer --prompt "가로 120cm 책상을 설계하기 위한 핵심 치수를 알려줘."

# 4. 모델 재로드가 없는지 확인 — 2회차 load_seconds 가 0.0 이어야 한다
.\.venv\Scripts\python.exe -m app.ai.cli infer --repeat 2
```

`diagnose` 출력 예시 (실측):

```json
{
  "python_version": "3.11.9",
  "torch_version": "2.14.1+cu130",
  "torch_cuda_version": "13.0",
  "cuda_available": true,
  "device_name": "NVIDIA GeForce RTX 4060",
  "device_capability": "8.9",
  "total_vram_mib": 8188,
  "driver_version": "591.86"
}
```

## 구성

환경변수로 제어한다. 기본값은 `.env.example` 참조.

| 변수 | 기본값 | 의미 |
|---|---|---|
| `LOCAL_AI_CAD_MODEL_ID` | `Qwen/Qwen2.5-1.5B-Instruct` | Hugging Face 모델 ID |
| `LOCAL_AI_CAD_DEVICE` | `cuda` | 추론 장치. CPU 자동 폴백 없음 |
| `LOCAL_AI_CAD_DTYPE` | `float16` | 가중치 dtype |
| `LOCAL_AI_CAD_MAX_NEW_TOKENS` | `256` | 무제한 생성 방지 |
| `LOCAL_AI_CAD_HF_HOME` | 미지정 | 캐시 경로. C: 여유가 부족하면 다른 드라이브로 |
| `LOCAL_AI_CAD_LOG_LEVEL` | `INFO` | 로그 수준 |
| `LOCAL_AI_CAD_HUNYUAN_URL` | `http://127.0.0.1:8090` | 별도 로컬 Hunyuan3D shape 서버 |

**디스크 주의**: C: 여유 공간이 약 24 GB다. 모델 캐시는 `~/.cache/huggingface` 에 약 3.7 GB를 쓴다. 여유가 부족하면 `LOCAL_AI_CAD_HF_HOME` 으로 캐시를 다른 드라이브에 둔다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

단위 테스트는 보조 수단이다. Phase 1 완료 판정은 위 "측정값" 표의 실제 GPU 실행이 근거다.

## 설계 원칙

- **조용한 폴백 금지.** CUDA가 없으면 CPU로 넘어가지 않고 종료 코드 3으로 실패한다.
- **오류 경계 분리.** 구성(2) / 환경(3) / 다운로드(4) / OOM(5) 이 서로 다른 종료 코드를 쓴다.
- **동시 실행 1개.** provider 기반 클래스가 lock으로 직렬화한다. 8 GiB VRAM에서 동시 생성은 OOM 경로다.
- **Mock 과 실제의 분리.** Mock 결과는 `provider: "mock"` 이며 성능 보고에 쓰지 않는다.
- **측정 없이 완료 없음.** 수치는 전부 실행 관측값이다.
