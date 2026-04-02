"""
Orchestrator Agent - 协调整个审查流程
负责任务调度、进度更新和结果汇总
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Orchestrator agent for managing the review workflow"""

    def __init__(
        self,
        pdf_parser,
        rule_classifier,
        document_reviewer,
        progress_callback: Optional[Callable] = None
    ):
        """
        初始化 Orchestrator

        Args:
            pdf_parser: PDFParserAgent 实例
            rule_classifier: RuleClassifierAgent 实例
            document_reviewer: DocumentReviewerAgent 实例
            progress_callback: 进度回调函数 (stage, progress, message)
        """
        self.pdf_parser = pdf_parser
        self.rule_classifier = rule_classifier
        self.document_reviewer = document_reviewer
        self.progress_callback = progress_callback

    def _update_progress(self, stage: str, progress: float, message: str = ""):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(stage, progress, message)

    async def run_review(
        self,
        pdf_path: Optional[str] = None,
        doc_text: Optional[str] = None,
        standard_content: Optional[str] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        执行完整的文档审查流程

        Args:
            pdf_path: 要审查的 PDF 文件路径
            doc_text: 要审查的文档文本（如果已有文本）
            standard_content: 标准文档内容（用于提取规则）
            rules: 预定义规则列表（如果有）
            task_id: 任务 ID

        Returns:
            审查结果:
            {
                "task_id": "...",
                "status": "completed",
                "stage": "finalized",
                "progress": 100,
                "results": [...],
                "summary": {...}
            }
        """
        start_time = datetime.now()
        result = {
            "task_id": task_id,
            "status": "processing",
            "start_time": start_time.isoformat(),
            "stages": {}
        }

        try:
            # Stage 1: 解析待审文档
            self._update_progress("parsing", 10, "正在解析文档...")
            if pdf_path:
                doc_content = self.pdf_parser.parse_to_text(pdf_path)
            elif doc_text:
                doc_content = doc_text
            else:
                raise ValueError("需要提供 pdf_path 或 doc_text")

            result["stages"]["parsing"] = {
                "status": "completed",
                "content_length": len(doc_content)
            }
            self._update_progress("parsing", 30, "文档解析完成")

            # Stage 2: 获取规则
            if standard_content and not rules:
                self._update_progress("classifying", 30, "正在分析审查标准...")
                classification = self.rule_classifier.run(standard_content)
                rules = self._extract_rules_from_classification(classification)
                result["stages"]["classifying"] = {
                    "status": "completed",
                    "rules_count": len(rules)
                }
            elif rules:
                result["stages"]["classifying"] = {
                    "status": "skipped",
                    "rules_count": len(rules),
                    "reason": "使用预定义规则"
                }

            if not rules:
                raise ValueError("没有可用的审查规则")

            self._update_progress("classifying", 50, f"已加载 {len(rules)} 条规则")

            # Stage 3: 审查文档
            self._update_progress("reviewing", 50, "正在进行文档审查...")
            review_result = self.document_reviewer.run(doc_content, rules)

            result["stages"]["reviewing"] = {
                "status": "completed",
                "results_count": len(review_result.get("results", []))
            }

            passed = review_result.get("summary", {}).get("passed", 0)
            total = review_result.get("summary", {}).get("total", 0)
            score = review_result.get("summary", {}).get("overall_score", 0)

            progress = 80 + int(score * 20)
            self._update_progress(
                "reviewing",
                progress,
                f"审查完成: {passed}/{total} 通过"
            )

            # Stage 4: 汇总结果
            result["status"] = "completed"
            result["stage"] = "finalized"
            result["progress"] = 100
            result["results"] = review_result.get("results", [])
            result["summary"] = review_result.get("summary", {})
            result["end_time"] = datetime.now().isoformat()

            duration = (datetime.now() - start_time).total_seconds()
            result["duration_seconds"] = duration

            self._update_progress("finalized", 100, f"审查完成，耗时 {duration:.1f} 秒")

            return result

        except Exception as e:
            logger.error(f"Review workflow failed: {str(e)}")
            result["status"] = "failed"
            result["error"] = str(e)
            result["end_time"] = datetime.now().isoformat()
            self._update_progress("failed", 0, f"审查失败: {str(e)}")
            return result

    def _extract_rules_from_classification(
        self,
        classification: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """从分类结果中提取规则列表"""
        rules = []
        rule_groups = classification.get("rule_groups", [])

        for group in rule_groups:
            group_name = group.get("group_name", "未分类")
            for rule in group.get("rules", []):
                rules.append({
                    "title": rule.get("title", ""),
                    "content": rule.get("content", ""),
                    "rule_group": group_name,
                    "source_page": rule.get("source_page")
                })

        return rules

    async def run_review_batch(
        self,
        documents: List[Dict[str, Any]],
        rules: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        批量审查多个文档

        Args:
            documents: 文档列表，每个包含 pdf_path 或 doc_text
            rules: 规则列表

        Returns:
            每个文档的审查结果列表
        """
        results = []
        total = len(documents)

        for i, doc in enumerate(documents):
            self._update_progress(
                "batch",
                int(i / total * 100),
                f"正在审查第 {i+1}/{total} 个文档"
            )

            result = await self.run_review(
                pdf_path=doc.get("pdf_path"),
                doc_text=doc.get("doc_text"),
                rules=rules,
                task_id=doc.get("task_id")
            )
            results.append(result)

        return results


# 便捷函数
def create_orchestrator(
    provider_type: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    progress_callback: Optional[Callable] = None,
    **kwargs
) -> OrchestratorAgent:
    """创建 Orchestrator Agent 的便捷函数"""
    from .pdf_parser_agent import PDFParserAgent
    from .react_llm_bridge import create_react_backend
    from .rule_classifier_agent import RuleClassifierAgent
    from .document_reviewer_agent import DocumentReviewerAgent

    backend = create_react_backend(
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        model=model,
        **kwargs
    )

    pdf_parser = PDFParserAgent()
    rule_classifier = RuleClassifierAgent(backend)
    document_reviewer = DocumentReviewerAgent(backend)

    return OrchestratorAgent(
        pdf_parser=pdf_parser,
        rule_classifier=rule_classifier,
        document_reviewer=document_reviewer,
        progress_callback=progress_callback
    )