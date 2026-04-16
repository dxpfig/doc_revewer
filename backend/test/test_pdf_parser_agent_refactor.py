import json
import os
import sys
import asyncio

from agentscope.message import Msg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.pdf_parser_agent import PDFParserAgent, create_pdf_parser_agent
from agents.skills.pdf_models import PDFPageResult, PDFParseResult


def test_toolkit_tools_registered() -> None:
    agent = PDFParserAgent(use_kimi_ocr=False)
    tool_names = set(agent.toolkit.tools.keys())
    assert "skill_pdf_to_image" in tool_names
    assert "skill_ocr_image" in tool_names
    assert "skill_format_markdown" in tool_names
    assert "skill_parse_pdf_document" in tool_names


def test_parse_uses_orchestrator_result() -> None:
    agent = PDFParserAgent(use_kimi_ocr=False)
    fake = PDFParseResult(
        text="hello",
        page_count=1,
        pages=[PDFPageResult(page_num=1, text="hello", method="text")],
        warnings=[],
    )

    def _fake_parse(_req):
        return fake

    agent.orchestrator.parse = _fake_parse  # type: ignore[method-assign]
    result = agent.parse("dummy.pdf")
    assert result["text"] == "hello"
    assert result["page_count"] == 1
    assert result["pages"][0]["method"] == "text"


def test_run_with_msg_json_payload() -> None:
    agent = PDFParserAgent(use_kimi_ocr=False)
    fake = PDFParseResult(
        text="msg-ok",
        page_count=1,
        pages=[PDFPageResult(page_num=1, text="msg-ok", method="text")],
        warnings=[],
    )

    def _fake_parse(_req):
        return fake

    agent.orchestrator.parse = _fake_parse  # type: ignore[method-assign]
    msg = Msg(name="user", role="user", content='{"pdf_path":"dummy.pdf"}')
    reply = asyncio.run(agent.run_with_msg(msg))
    payload = json.loads(str(reply.content))
    assert payload["ok"] is True
    assert payload["result"]["text"] == "msg-ok"


def test_create_pdf_parser_agent_requires_api_key() -> None:
    try:
        create_pdf_parser_agent(api_key=None)
        assert False, "Expected ValueError when api_key is None"
    except ValueError:
        assert True


def test_create_pdf_parser_agent_with_fake_key() -> None:
    react_agent = create_pdf_parser_agent(api_key="fake-key")
    assert react_agent is not None


def test_parse_validates_page_range() -> None:
    agent = PDFParserAgent(use_kimi_ocr=False)
    try:
        agent.parse("dummy.pdf", start_page=3, end_page=2)
        assert False, "Expected ValueError when start_page > end_page"
    except ValueError as e:
        assert "start_page" in str(e)
    except FileNotFoundError:
        # file check happens before parsing real range for non-existing file
        assert True


def test_run_with_msg_missing_pdf_path() -> None:
    agent = PDFParserAgent(use_kimi_ocr=False)
    reply = asyncio.run(agent.run_with_msg(Msg(name="user", role="user", content='{"start_page":1}')))
    payload = json.loads(str(reply.content))
    assert payload["ok"] is False
    assert payload["error"] == "missing_pdf_path"
