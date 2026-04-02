"""
OpenTelemetry 辅助与 Mock LLM（业务 LLM 请使用 react_llm_bridge.ReactLLMBackend + ReActAgent）。
"""
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

_tracer_provider = None
_tracer = None
_run_id = None
_project_name = None


def _init_opentelemetry():
    """初始化 OpenTelemetry tracing（与 AgentScope 全局 TracerProvider 合并）"""
    global _tracer_provider, _tracer, _run_id, _project_name

    if _tracer_provider is not None:
        return _tracer

    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry import trace

        studio_url = os.environ.get("AGENTSCOPE_STUDIO_URL")
        if not studio_url:
            return None

        try:
            import agentscope

            if hasattr(agentscope, "_config") and agentscope._config:
                _run_id = agentscope._config.run_id
                _project_name = agentscope._config.project
        except Exception:
            pass

        _run_id = _run_id or os.environ.get("AGENTSCOPE_RUN_ID", "default_run")
        _project_name = _project_name or os.environ.get(
            "AGENTSCOPE_PROJECT", "doc_revewer"
        )

        studio_url = str(studio_url).strip().strip('"').rstrip("/")
        endpoint = f"{studio_url}/v1/traces"
        current = trace.get_tracer_provider()

        if isinstance(current, TracerProvider):
            _tracer_provider = current
            _tracer = current.get_tracer("doc_revewer", "1.0.0")
            logger.info("复用全局 TracerProvider（与 AgentScope 一致）")
            return _tracer

        _tracer_provider = TracerProvider()
        exporter = OTLPSpanExporter(endpoint=endpoint)
        _tracer_provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(_tracer_provider)
        _tracer = _tracer_provider.get_tracer("doc_revewer", "1.0.0")
        return _tracer

    except ImportError:
        logger.warning("opentelemetry not installed, tracing disabled")
        return None
    except Exception as e:
        logger.warning("Failed to init OpenTelemetry tracing: %s", e)
        return None


def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = _init_opentelemetry()
    return _tracer


def get_run_context() -> Dict[str, str]:
    return {
        "run_id": _run_id or "unknown",
        "project": _project_name or "doc_revewer",
    }


class MockAgent:
    """测试用占位，不发起真实请求。"""

    provider_type = "mock"

    def __init__(self, **kwargs):
        self.base_url = ""
        self.api_key = ""
        self.model = "mock"
        self.mock_responses = kwargs.get("mock_responses", {})

    def call_llm(
        self,
        system: str,
        user: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        return self.mock_responses.get("default", "Mock response")

    def run(self, *args: Any, **kwargs: Any) -> Any:
        return self.mock_responses.get("default", "Mock response")
