"""
PDF Parser Agent（AgentScope + Skills 版本）
对外保留兼容 API，内部能力拆分到 backend/agents/skills。
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import Msg
from agentscope.tool import ToolResponse, Toolkit

from .agentscope_agent import KimiHTTPChatModel
from .skills.pdf_models import PDFPageResult, PDFParseRequest, PDFParseResult
from .skills.pdf_orchestrator import PDFParseOrchestrator
from .skills.pdf_skills import (
    ExtractPdfTextSkill,
    FormatMarkdownSkill,
    OcrImageSkill,
    PdfToImageSkill,
)

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False


def _tool_response(payload: dict[str, Any]) -> ToolResponse:
    return ToolResponse(content=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}])


class PDFParserAgent:
    """PDF 解析 Agent（同步 API + AgentScope Msg 双入口）。"""

    def __init__(
        self,
        ocr_enabled: bool = True,
        ocr_language: str = "chi_sim+eng",
        dpi: int = 300,
        use_kimi_ocr: bool = False,
        kimi_api_key: Optional[str] = None,
        kimi_vision_model: str = "moonshot-v1-8k-vision-preview",
        kimi_text_model: str = "moonshot-v1-8k",
        format_markdown: bool = True,
        temp_dir: str = "/tmp/kimi_ocr",
    ) -> None:
        self.ocr_enabled = ocr_enabled
        self.ocr_language = ocr_language
        self.dpi = dpi
        self.use_kimi_ocr = use_kimi_ocr
        self.format_markdown = format_markdown
        self.temp_dir = temp_dir
        os.makedirs(self.temp_dir, exist_ok=True)

        self.extract_text_skill = ExtractPdfTextSkill(
            ocr_enabled=self.ocr_enabled,
            ocr_language=self.ocr_language,
            dpi=self.dpi,
        )
        self.pdf_to_image_skill = PdfToImageSkill()
        self.ocr_image_skill = (
            OcrImageSkill(api_key=kimi_api_key, vision_model=kimi_vision_model) if use_kimi_ocr and kimi_api_key else None
        )
        self.format_markdown_skill = (
            FormatMarkdownSkill(api_key=kimi_api_key, text_model=kimi_text_model)
            if use_kimi_ocr and kimi_api_key and format_markdown
            else None
        )
        self.orchestrator = PDFParseOrchestrator(
            extract_text_skill=self.extract_text_skill,
            pdf_to_image_skill=self.pdf_to_image_skill,
            ocr_image_skill=self.ocr_image_skill,
            format_markdown_skill=self.format_markdown_skill,
            temp_dir=self.temp_dir,
        )
        self.toolkit = self._build_toolkit()

    def _build_toolkit(self) -> Toolkit:
        toolkit = Toolkit()

        def skill_pdf_to_image(pdf_path: str, page_num: int, output_dir: str, dpi: int = 150, min_size: int = 400) -> ToolResponse:
            """
            将 PDF 指定页转为 JPG 图片。
            Args:
                pdf_path: PDF 文件路径
                page_num: 页码（1-based）
                output_dir: 输出目录
                dpi: 渲染 DPI
                min_size: 图片最小边尺寸
            Returns:
                ToolResponse(JSON):
                {"ok": bool, "image_path"?: str, "error"?: str}
            """
            return _tool_response(
                self.pdf_to_image_skill.convert(
                    pdf_path=pdf_path,
                    page_num=page_num,
                    output_dir=output_dir,
                    dpi=dpi,
                    min_size=min_size,
                )
            )

        def skill_ocr_image(image_path: str, prompt: str = "请识别图片中的所有文字内容，直接输出文字，不要其他说明。") -> ToolResponse:
            """
            对图片执行 OCR 并返回文本。
            Args:
                image_path: 图片路径
                prompt: OCR 提示词
            Returns:
                ToolResponse(JSON):
                {"ok": bool, "text"?: str, "error"?: str}
            """
            if not self.ocr_image_skill:
                return _tool_response({"ok": False, "error": "Kimi OCR skill is not enabled"})
            return _tool_response(self.ocr_image_skill.run(image_path=image_path, prompt=prompt))

        def skill_format_markdown(ocr_text: str) -> ToolResponse:
            """
            将 OCR 文本格式化为 Markdown。
            Args:
                ocr_text: OCR 原始文本
            Returns:
                ToolResponse(JSON):
                {"ok": bool, "text"?: str, "error"?: str}
            """
            if not self.format_markdown_skill:
                return _tool_response({"ok": False, "error": "Markdown format skill is not enabled"})
            return _tool_response(self.format_markdown_skill.run(ocr_text))

        def skill_parse_pdf_document(
            pdf_path: str,
            start_page: int = 1,
            end_page: int = 0,
            use_kimi_ocr: bool = False,
            format_markdown: bool = False,
        ) -> ToolResponse:
            """
            解析 PDF 文件并返回结构化结果。
            Args:
                pdf_path: PDF 文件路径
                start_page: 起始页（1-based）
                end_page: 结束页（0 表示最后一页）
                use_kimi_ocr: 是否使用 Kimi OCR
                format_markdown: 是否格式化为 Markdown
            Returns:
                ToolResponse(JSON):
                {
                  "ok": bool,
                  "result"?: {
                    "text": str,
                    "page_count": int,
                    "pages": list[dict],
                    "warnings": list[str]
                  },
                  "error"?: str
                }
            """
            if not pdf_path or not isinstance(pdf_path, str):
                return _tool_response({"ok": False, "error": "invalid_pdf_path"})
            if start_page < 1:
                return _tool_response({"ok": False, "error": "invalid_start_page"})
            if end_page != 0 and end_page < 1:
                return _tool_response({"ok": False, "error": "invalid_end_page"})
            if end_page != 0 and start_page > end_page:
                return _tool_response({"ok": False, "error": "start_page_gt_end_page"})

            req = PDFParseRequest(
                pdf_path=pdf_path,
                start_page=start_page,
                end_page=None if end_page == 0 else end_page,
                use_kimi_ocr=use_kimi_ocr,
                format_markdown=format_markdown,
            )
            try:
                parsed = self.orchestrator.parse(req)
                return _tool_response({"ok": True, "result": parsed.to_dict()})
            except Exception as e:
                return _tool_response({"ok": False, "error": str(e)})

        toolkit.register_tool_function(skill_pdf_to_image)
        toolkit.register_tool_function(skill_ocr_image)
        toolkit.register_tool_function(skill_format_markdown)
        toolkit.register_tool_function(skill_parse_pdf_document)
        return toolkit

    def parse(self, pdf_path: str, start_page: Optional[int] = None, end_page: Optional[int] = None) -> dict[str, Any]:
        req = PDFParseRequest(
            pdf_path=pdf_path,
            start_page=start_page,
            end_page=end_page,
            use_kimi_ocr=self.use_kimi_ocr,
            format_markdown=self.format_markdown,
        )
        return self.orchestrator.parse(req).to_dict()

    def parse_to_text(self, pdf_path: str) -> str:
        return self.parse(pdf_path)["text"]

    def get_page_count(self, pdf_path: str) -> int:
        if not PDFPLUMBER_AVAILABLE:
            raise ImportError("pdfplumber is required for PDF parsing")
        with pdfplumber.open(pdf_path) as pdf:
            return len(pdf.pages)

    def extract_page(self, pdf_path: str, page_num: int) -> str:
        result = self.parse(pdf_path, start_page=page_num, end_page=page_num)
        pages = result.get("pages", [])
        if not pages:
            return ""
        return pages[0].get("text", "")

    async def run_with_msg(self, msg: Msg) -> Msg:
        """
        AgentScope 消息入口（不依赖 LLM），支持两种输入：
        - 纯字符串：视为 pdf_path
        - JSON 字符串：包含 pdf_path/start_page/end_page/use_kimi_ocr/format_markdown
        """
        content = msg.content
        if isinstance(content, list):
            content = "".join(
                str(item.get("text", "")) if isinstance(item, dict) and item.get("type") == "text" else ""
                for item in content
            )
        content = str(content or "").strip()

        try:
            payload = json.loads(content) if content.startswith("{") else {"pdf_path": content}
            if not isinstance(payload, dict):
                raise ValueError("invalid_payload_type")
            if "pdf_path" not in payload:
                raise ValueError("missing_pdf_path")
            if not isinstance(payload["pdf_path"], str) or not payload["pdf_path"].strip():
                raise ValueError("invalid_pdf_path")
            if payload.get("start_page") is not None and (
                not isinstance(payload["start_page"], int) or payload["start_page"] < 1
            ):
                raise ValueError("invalid_start_page")
            if payload.get("end_page") is not None and (
                not isinstance(payload["end_page"], int) or payload["end_page"] < 1
            ):
                raise ValueError("invalid_end_page")
            if payload.get("start_page") and payload.get("end_page") and payload["start_page"] > payload["end_page"]:
                raise ValueError("start_page_gt_end_page")

            req = PDFParseRequest(
                pdf_path=payload["pdf_path"],
                start_page=payload.get("start_page"),
                end_page=payload.get("end_page"),
                use_kimi_ocr=payload.get("use_kimi_ocr", self.use_kimi_ocr),
                format_markdown=payload.get("format_markdown", self.format_markdown),
            )
            result = self.orchestrator.parse(req).to_dict()
            reply = {"ok": True, "result": result}
        except Exception as e:
            reply = {"ok": False, "error": str(e), "error_type": type(e).__name__}
        return Msg(name="PDFParserAgent", role="assistant", content=json.dumps(reply, ensure_ascii=False))


def create_pdf_parser_agent(
    *,
    api_key: Optional[str] = None,
    model_name: str = "moonshot-v1-8k",
    base_url: str = "https://api.moonshot.cn/v1",
    parser_agent: Optional[PDFParserAgent] = None,
    name: str = "PDFParserReAct",
    max_iters: int = 5,
) -> ReActAgent:
    """
    创建可调用 PDF Skills 的 ReActAgent。
    若未提供 parser_agent，将创建默认实例（不启用 Kimi OCR）。
    """
    if not api_key:
        raise ValueError("api_key is required for ReAct PDF parser agent")
    parser = parser_agent or PDFParserAgent()
    model = KimiHTTPChatModel(api_key=api_key, model_name=model_name, base_url=base_url)
    sys_prompt = (
        "你是 PDF 解析助手。优先调用工具完成任务。"
        "若用户要求解析 PDF，请调用 skill_parse_pdf_document 并返回结构化结果。"
    )
    return ReActAgent(
        name=name,
        sys_prompt=sys_prompt,
        model=model,
        formatter=OpenAIChatFormatter(),
        memory=InMemoryMemory(),
        toolkit=parser.toolkit,
        max_iters=max_iters,
    )


def parse_pdf(pdf_path: str, **kwargs: Any) -> dict[str, Any]:
    """解析 PDF 文件的便捷函数（兼容旧接口）。"""
    agent = PDFParserAgent(**kwargs)
    return agent.parse(pdf_path)


def pdf_to_text(pdf_path: str) -> str:
    """将 PDF 转换为纯文本的便捷函数（兼容旧接口）。"""
    agent = PDFParserAgent()
    return agent.parse_to_text(pdf_path)


def parse_pdf_kimi(
    pdf_path: str,
    api_key: str,
    vision_model: str = "moonshot-v1-8k-vision-preview",
    text_model: str = "moonshot-v1-8k",
    format_markdown: bool = True,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """使用 Kimi OCR 解析 PDF 的便捷函数（兼容旧接口）。"""
    agent = PDFParserAgent(
        use_kimi_ocr=True,
        kimi_api_key=api_key,
        kimi_vision_model=vision_model,
        kimi_text_model=text_model,
        format_markdown=format_markdown,
        **kwargs,
    )
    return agent.parse(pdf_path, start_page=start_page, end_page=end_page)


__all__ = [
    "PDFParseRequest",
    "PDFPageResult",
    "PDFParseResult",
    "PdfToImageSkill",
    "OcrImageSkill",
    "FormatMarkdownSkill",
    "ExtractPdfTextSkill",
    "PDFParseOrchestrator",
    "PDFParserAgent",
    "create_pdf_parser_agent",
    "parse_pdf",
    "pdf_to_text",
    "parse_pdf_kimi",
]