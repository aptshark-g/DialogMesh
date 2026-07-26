"""DialogMesh v6 — minimal FastAPI app with chat + checkpoint + status endpoints.

Bypasses legacy module imports. Only loads v6-specific dependencies.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="DialogMesh v6", version="6.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ═══ Chat endpoints ═══
from core.agent.api.chat_api import router as chat_router, set_orchestrator
app.include_router(chat_router)

# ═══ Lazy-load orchestrator on startup ═══
@app.on_event("startup")
async def startup():
    from core.agent.orchestrator.bootstrap_v6 import bootstrap
    orch = bootstrap()
    set_orchestrator(orch)
    print("[v6] Orchestrator loaded")

@app.get("/v6/health")
async def health():
    return {"status": "ok", "version": "6.0.0"}

@app.get("/v6/status")
async def status():
    orch = getattr(
        getattr(chat_router, '_orchestrator', None) or
        __import__('core.agent.orchestrator.bootstrap_v6', fromlist=['bootstrap']).bootstrap,
        '__self__', None)
    return {"status": "running", "modules": "v6"}
