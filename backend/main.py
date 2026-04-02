from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from db.session import init_db
from api.v1.auth import router as auth_router
from api.v1.standards import router as standards_router
from api.v1.review_tasks import router as review_tasks_router
from api.v1.results import router as results_router
from api.v1.admin import router as admin_router
import os
from pathlib import Path
import agentscope_runtime as as_runtime

# 加载 .env 文件
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时初始化
    as_runtime.init_agentscope()
    await init_db()
    from db.seed import seed_default_users
    await seed_default_users()
    yield


app = FastAPI(
    title="Doc Revewer API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(standards_router, prefix="/api/v1")
app.include_router(review_tasks_router, prefix="/api/v1")
app.include_router(results_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"message": "Doc Revewer API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/v1/agentscope/status")
async def agentscope_status():
    """
    开发/排错：进程内 AgentScope 是否完成启动初始化。
    注意：HTTP 请求所在协程的 trace_enabled 与后台审查任务无关；
    审查任务在 register_agentscope_task_run 内单独开启。
    """
    studio = (os.environ.get("AGENTSCOPE_STUDIO_URL") or "").strip().strip('"')
    if not as_runtime.is_agentscope_initialized():
        return {
            "data": {
                "studio_initialized": False,
                "studio_url_configured": bool(studio),
                "hint": "启动时 init_agentscope 失败或未配置 URL；查看服务端日志中的 AgentScope 行。",
            }
        }
    import agentscope

    return {
        "data": {
            "studio_initialized": True,
            "studio_url_configured": bool(studio),
            "startup_run_id": agentscope._config.run_id,
            "startup_run_name": agentscope._config.name,
            "project": agentscope._config.project,
            "find_task_traces": (
                "发起审查后看后端日志「AgentScope: run_id=task_<数字>」；"
                "Studio 列表中 name 形如 review_task_<同一数字>；TRACE 须点选该 run。"
                " 若仍无数据：设置 AGENTSCOPE_TRACE_DIAG=1 重启后再跑任务，应出现 doc_revewer_trace_diag_pulse。"
            ),
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18000)