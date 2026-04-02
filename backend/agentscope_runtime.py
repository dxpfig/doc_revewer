from __future__ import annotations

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# AgentScope Studio 配置
_agentscope_initialized = False

# AgentScope：当前后台任务对应的 run_id（仅运维观测）
_agentscope_active_run_id = None


def is_agentscope_initialized() -> bool:
    return _agentscope_initialized


def init_agentscope() -> None:
    """初始化 AgentScope Studio 监控。"""
    global _agentscope_initialized

    # 防止重复初始化（确保只初始化一次）
    if _agentscope_initialized:
        return

    studio_url = (os.environ.get("AGENTSCOPE_STUDIO_URL") or "").strip().strip('"')
    if studio_url:
        try:
            import agentscope

            # 进程内只 init 一次：挂载 tracing / Studio hooks
            agentscope.init(
                studio_url=studio_url,
                project="doc_revewer",
                name="doc_revewer_server",
                logging_level="INFO",
            )

            _agentscope_initialized = True
            print(f"✅ AgentScope Studio connected: {studio_url}")
            print(f"   Project: {agentscope._config.project}")
            print(f"   Name: {agentscope._config.name}")
            print(f"   Run ID: {agentscope._config.run_id}")
        except ImportError:
            print("⚠️  agentscope not installed, Studio monitoring disabled")
        except Exception as e:
            # agentscope.init 先 registerRun 再 setup_tracing；Studio 未启动时整段失败会导致
            # 从未挂载 OTLP，后台任务里 trace 永远为空。
            print(f"⚠️  Failed to init AgentScope (full init): {e}")
            try:
                import agentscope
                from agentscope.tracing import setup_tracing

                base = studio_url.rstrip("/")
                setup_tracing(endpoint=f"{base}/v1/traces")
                agentscope._config.trace_enabled = True
                agentscope._config.project = "doc_revewer"
                agentscope._config.name = "doc_revewer_server_otlp_only"
                _agentscope_initialized = True
                print(
                    "✅ AgentScope OTLP 已挂载（registerRun 失败时的降级）；"
                    f" endpoint={base}/v1/traces — 请先启动 Studio 或可稍后在任务内重试 registerRun"
                )
            except Exception as e2:
                print(f"⚠️  AgentScope OTLP 降级也失败: {e2}")
    else:
        print("ℹ️  AGENTSCOPE_STUDIO_URL not set, Studio monitoring disabled")


def register_agentscope_task_run(task_id: str) -> str | None:
    """
    在 init_agentscope() 已成功的前提下，为单个审查任务注册 Studio 侧 run。
    不再次调用 agentscope.init / setup_tracing，避免重复挂载 OTLP SpanProcessor。
    """
    global _agentscope_active_run_id

    if not _agentscope_initialized:
        logger.warning(
            "AgentScope 未在进程启动时初始化成功，跳过任务级 run；"
            "请检查 AGENTSCOPE_STUDIO_URL 与 Studio 是否可访问（registerRun）。"
        )
        return None

    studio_url = (os.environ.get("AGENTSCOPE_STUDIO_URL") or "").strip().strip('"')
    if not studio_url:
        return None

    try:
        import requests
        import agentscope
        from agentscope.agent import StudioUserInput, UserAgent
        from agentscope.hooks import _equip_as_studio_hooks

        # 当前 asyncio 任务内开启 tracing（与 lifespan 不是同一上下文）
        agentscope._config.trace_enabled = True

        run_id = f"task_{task_id}"
        _agentscope_active_run_id = run_id

        agentscope._config.project = "doc_revewer"
        agentscope._config.name = f"review_task_{task_id}"
        agentscope._config.run_id = run_id
        agentscope._config.created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        base = studio_url.rstrip("/")
        data = {
            "id": agentscope._config.run_id,
            "project": agentscope._config.project,
            "name": agentscope._config.name,
            "timestamp": agentscope._config.created_at,
            "pid": os.getpid(),
            "status": "running",
            "run_dir": "",
        }
        response = requests.post(
            url=f"{base}/trpc/registerRun",
            json=data,
            timeout=10,
        )
        response.raise_for_status()

        UserAgent.override_class_input_method(
            StudioUserInput(
                studio_url=base,
                run_id=agentscope._config.run_id,
                max_retries=3,
            ),
        )
        _equip_as_studio_hooks(base)

        logger.info(
            "AgentScope 已为审查任务注册 Studio run："
            "run_id=%s（Studio TRACE 按此会话 ID 关联）display_name=%s project=%s",
            run_id,
            agentscope._config.name,
            agentscope._config.project,
        )
        print(
            f"🎯 AgentScope: run_id={run_id} name={agentscope._config.name} "
            f"— 在 Studio 项目 doc_revewer 中查找本条（TRACE 页）"
        )
        maybe_agentscope_trace_diagnostic_pulse(task_id)
        return run_id
    except Exception as e:
        logger.warning("注册 AgentScope 任务 run 失败（trace 仍可能上报到默认 run）: %s", e)
        print(f"⚠️  Failed to register AgentScope task run: {e}")
        return None


def start_agentscope_run(task_id: str) -> str | None:
    """兼容旧名：等同 register_agentscope_task_run。"""
    return register_agentscope_task_run(task_id)


def stop_agentscope_run() -> None:
    """停止当前的 AgentScope run。"""
    global _agentscope_active_run_id
    _agentscope_active_run_id = None


def ensure_agentscope_trace_for_worker() -> None:
    """在后台审查协程内尽早调用，写入当前 asyncio Context 的 trace_enabled。"""
    if not _agentscope_initialized:
        return
    import agentscope

    agentscope._config.trace_enabled = True


def flush_agentscope_traces(timeout_millis: int = 15_000) -> None:
    """将 BatchSpanProcessor 中未导出的 span 推送到 Studio。"""
    if not _agentscope_initialized:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider):
            provider.force_flush(timeout_millis=timeout_millis)
    except Exception as exc:
        logger.debug("AgentScope OTEL force_flush: %s", exc)


def maybe_agentscope_trace_diagnostic_pulse(task_id: str) -> None:
    """环境变量 AGENTSCOPE_TRACE_DIAG=1 时打一个测试 span，确认 OTLP 通路。"""
    if os.environ.get("AGENTSCOPE_TRACE_DIAG", "").lower() not in ("1", "true", "yes"):
        return
    if not _agentscope_initialized:
        return
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("doc_revewer_diag", "1.0.0")
        with tracer.start_as_current_span("doc_revewer_trace_diag_pulse") as span:
            span.set_attribute("doc_revewer.task_id", str(task_id))
        flush_agentscope_traces(timeout_millis=5_000)
        print(f"🔬 AgentScope TRACE_DIAG: 已发送测试 span，task_id={task_id}")
    except Exception as exc:
        logger.warning("AgentScope TRACE_DIAG 失败: %s", exc)
