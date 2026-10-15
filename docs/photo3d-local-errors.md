# 로컬 GPU 사진 3D 오류 기록

기준일: 2026-10-15

## 해결됨

| 단계 | 관찰된 오류 | 원인 | 처리 |
|---|---|---|---|
| Hunyuan 저장소 설치 | `git clone` 연결 reset·early EOF | 네트워크 전송 중단 | 불완전한 신규 설치 디렉터리만 제거하고 `--filter=blob:none --depth 1`로 재시도 |
| 친구 코드 `--low-vram` 기동 | `AttributeError: ... has no attribute 'components'` | 현재 upstream pipeline이 Diffusers offload helper를 포함하지만 `components`를 정의하지 않음 | 해당 helper를 제품 경로에서 제거 |
| 임시 Accelerate offload | CPU/CUDA tensor 혼합, 이후 meta tensor `.item()` 실패 | Hunyuan pipeline이 `self.device`와 일부 파라미터의 실제 장치를 직접 가정 | 불완전한 offload 우회를 제거하고 검증된 native CUDA 경로만 제공 |
| 첫 배경 분리 회귀 | 균일 이미지 거부 문구와 테스트 regex 불일치 | 구현은 정상 거부했지만 테스트가 특정 단어를 과도하게 고정 | 소비자 의미인 `배경` 오류만 검증하도록 수정 |

## 최종 판정

- RTX 4050 Laptop GPU 6,141MiB에서 Qwen 프로세스를 종료한 뒤 Hunyuan3D-2mv turbo shape 모델이 정상 로드됐다.
- 로드 직후 VRAM은 5,690MiB 사용, 234MiB 여유로 측정됐다.
- 정면·후면·좌측·우측 합성 의자 4장을 실제 로컬 CUDA로 처리해 98.086초에 2,742,784바이트 GLB를 생성했다.
- 같은 입력은 SHA-256 콘텐츠 캐시로 재추론 없이 반환됐다.
- 실제 Edge에서 네 사진 업로드, 캐시 결과 요청, GLB 렌더, 다운로드 링크, 콘솔 오류 0건을 확인했다.
- 6GB GPU에서 Qwen과 Hunyuan을 동시에 상주시키는 경로는 지원하지 않는다.
