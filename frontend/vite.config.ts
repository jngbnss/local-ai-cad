import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/**
 * 개발 서버는 5173, `/api` 는 로컬 FastAPI(127.0.0.1:8000)로 프록시한다.
 *
 * 프록시를 두는 이유는 CORS 설정을 프런트/백엔드 양쪽에 중복으로 두지 않기 위해서다.
 * 브라우저 입장에서 모든 요청은 same-origin 이므로 STL/STEP 바이너리 다운로드도
 * 추가 헤더 없이 그대로 동작한다.
 *
 * `localhost` 가 아니라 `127.0.0.1` 을 쓴다. Windows + Node 에서 `localhost` 가
 * IPv6 `::1` 로 먼저 풀려 IPv4 로만 바인딩한 uvicorn 에 ECONNREFUSED 가 나는 사례를 피한다.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
});
