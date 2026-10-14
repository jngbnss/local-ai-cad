# Local AI CAD

자연어로 CAD를 설계하는 로컬 AI 도구. **외부 LLM API를 쓰지 않고** 이 PC의 GPU에서 모델을 직접 실행한다.

- 전체 단계 로드맵: `docs/roadmap.md`
- 현재 단계: **Phase 1~6 완료** — API, DesignSpec, CAD 생성, SSE 3D UI, 영속 이력 검증
- Phase 1 상세 설계: `docs/phase-1-design.md`

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

브라우저에서 `http://127.0.0.1:5173`을 연다. GPU 모델 없이 전체 흐름만 빠르게
확인하려면 백엔드 실행 전에 `$env:LOCAL_AI_CAD_USE_MOCK = "1"`을 지정한다. Mock도
DesignSpec → CadQuery → STL/STEP → Three.js 경로를 실제로 실행하며 성능 측정에는 쓰지 않는다.

실제 모델 20문항 평가는 1차 80%, 교정 재시도 포함 90%였다. 상세 결과는
`experiments/spec_accuracy_report.md`에 있다. 다음 단계는 Phase 7 Docker/WSL2 패키징이며,
복합 가구 정확도 개선을 위한 트랙 Q(LoRA/모델 교체)는 별도 권장 항목이다.

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
