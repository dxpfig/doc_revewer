"""
Agents package - 提供文档审查所需的各类 Agent
"""
from .base_agent import MockAgent
from .react_llm_bridge import ReactLLMBackend, create_react_backend
from .pdf_parser_agent import (
    PDFParserAgent,
    create_pdf_parser_agent,
    parse_pdf,
    pdf_to_text,
)
from .rule_classifier_agent import RuleClassifierAgent, create_rule_classifier
from .rule_extractor_agent import RuleExtractorAgent, create_rule_extractor
from .document_reviewer_agent import DocumentReviewerAgent, create_document_reviewer
from .orchestrator_agent import OrchestratorAgent, create_orchestrator

# AgentScope 集成（ReActAgent + KimiHTTPChatModel，对齐 examples/game/werewolves/test_kimi）
from .agentscope_agent import (
    KimiHTTPChatModel,
    create_doc_reviewer_agent,
    create_document_review_react_agent,
    msg_to_text,
)

from .kimi_model import create_kimi_model

# AgentScope Review Agent
from .agentscope_review_agent import (
    create_review_agent,
    review_document_with_agentscope,
)
from .skills import PDFPageResult, PDFParseOrchestrator, PDFParseRequest, PDFParseResult

__all__ = [
    "ReactLLMBackend",
    "create_react_backend",
    "MockAgent",
    "PDFParserAgent",
    "create_pdf_parser_agent",
    "parse_pdf",
    "pdf_to_text",
    "RuleClassifierAgent",
    "create_rule_classifier",
    "RuleExtractorAgent",
    "create_rule_extractor",
    "DocumentReviewerAgent",
    "create_document_reviewer",
    "OrchestratorAgent",
    "create_orchestrator",
    # AgentScope 集成
    "KimiHTTPChatModel",
    "create_doc_reviewer_agent",
    "create_document_review_react_agent",
    "msg_to_text",
    "create_kimi_model",
    "create_review_agent",
    "review_document_with_agentscope",
    # PDF skills/models
    "PDFParseRequest",
    "PDFPageResult",
    "PDFParseResult",
    "PDFParseOrchestrator",
]