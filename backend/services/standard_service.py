"""
Standard Service - 标准解析服务
调用 pdf_parser + rule_classifier agent 处理标准文档
"""
import logging
import os
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import Standard, Rule
from agents.pdf_parser_agent import PDFParserAgent
from agents.rule_classifier_agent import RuleClassifierAgent

logger = logging.getLogger(__name__)


class StandardService:
    """Service for managing review standards"""

    def __init__(self, db: AsyncSession, llm_service=None):
        self.db = db
        self.llm_service = llm_service
        self.pdf_parser = PDFParserAgent()

    async def get_standard(self, standard_id: int) -> Optional[Standard]:
        """获取标准详情"""
        result = await self.db.execute(
            select(Standard).where(Standard.id == standard_id)
        )
        return result.scalar_one_or_none()

    async def get_published_standards(self) -> List[Standard]:
        """获取所有已发布的标准"""
        result = await self.db.execute(
            select(Standard)
            .where(Standard.status == "published")
            .order_by(Standard.created_at.desc())
        )
        return result.scalars().all()

    async def get_standard_with_rules(self, standard_id: int) -> Optional[Dict[str, Any]]:
        """获取标准及其规则"""
        standard = await self.get_standard(standard_id)
        if not standard:
            return None

        # 获取规则
        rules_result = await self.db.execute(
            select(Rule).where(Rule.standard_id == standard_id).order_by(Rule.rule_order)
        )
        rules = rules_result.scalars().all()

        return {
            "id": standard.id,
            "name": standard.name,
            "content_mode": standard.content_mode,
            "status": standard.status,
            "parsed_content": standard.parsed_content,
            "rules": [
                {
                    "id": r.id,
                    "title": r.title,
                    "content": r.content,
                    "rule_group": r.rule_group,
                    "rule_order": r.rule_order,
                    "source_page": r.source_page,
                    "source_excerpt": r.source_excerpt
                }
                for r in rules
            ]
        }

    async def parse_standard(
        self,
        standard_id: int,
        use_llm: bool = True
    ) -> Dict[str, Any]:
        """
        解析标准文档，提取规则

        Args:
            standard_id: 标准 ID
            use_llm: 是否使用 LLM 分类（否则使用简单正则）

        Returns:
            解析结果
        """
        standard = await self.get_standard(standard_id)
        if not standard:
            raise ValueError(f"Standard {standard_id} not found")

        # 如果已有解析内容，直接返回
        if standard.parsed_content:
            # 获取现有规则
            rules_result = await self.db.execute(
                select(Rule).where(Rule.standard_id == standard_id)
            )
            existing_rules = rules_result.scalars().all()

            if existing_rules:
                return {
                    "standard_id": standard_id,
                    "parsed": True,
                    "rules_count": len(existing_rules),
                    "message": "使用已有解析结果"
                }

        # 解析 PDF
        if standard.raw_pdf_path and os.path.exists(standard.raw_pdf_path):
            parsed_result = self.pdf_parser.parse(standard.raw_pdf_path)
            parsed_text = parsed_result["text"]

            # 更新解析内容
            standard.parsed_content = parsed_text
        else:
            raise ValueError(f"Standard {standard_id} has no PDF to parse")

        # 使用 LLM 分类规则
        if use_llm and self.llm_service:
            try:
                # 创建 LLM agent
                agent = self.llm_service.create_agent()
                classifier = RuleClassifierAgent(agent)

                # 分类规则
                classification = classifier.run(parsed_text)

                # 保存规则
                await self._save_rules_from_classification(
                    standard_id, classification
                )

                return {
                    "standard_id": standard_id,
                    "parsed": True,
                    "llm_classified": True,
                    "rules_count": len(classification.get("rule_groups", [])),
                    "summary": classification.get("summary", "")
                }

            except Exception as e:
                logger.error(f"LLM classification failed: {str(e)}")
                # 降级到简单正则解析

        # 简单正则解析
        rules = self._parse_rules_simple(parsed_text)
        await self._save_rules(standard_id, rules)

        return {
            "standard_id": standard_id,
            "parsed": True,
            "llm_classified": False,
            "rules_count": len(rules)
        }

    def _parse_rules_simple(self, text: str) -> List[Dict[str, Any]]:
        """简单的规则解析（使用正则）"""
        import re
        rules = []
        pattern = re.compile(r'^(?:\d+\.|第[\d一二三四五六七八九十]+条|第[\d]+章)\s*(.+)$', re.MULTILINE)

        for i, match in enumerate(pattern.finditer(text)):
            title = match.group(1).strip()[:200]
            if len(title) > 5:
                rules.append({
                    "title": title,
                    "content": title,
                    "source_excerpt": match.group(0),
                    "rule_group": "未分类"
                })

        return rules

    async def _save_rules(
        self,
        standard_id: int,
        rules: List[Dict[str, Any]]
    ):
        """保存规则到数据库"""
        # 先删除现有规则
        existing = await self.db.execute(
            select(Rule).where(Rule.standard_id == standard_id)
        )
        for r in existing.scalars().all():
            await self.db.delete(r)

        # 添加新规则
        for i, rule_data in enumerate(rules):
            rule = Rule(
                standard_id=standard_id,
                title=rule_data["title"],
                content=rule_data.get("content", rule_data["title"]),
                source_excerpt=rule_data.get("source_excerpt"),
                rule_group=rule_data.get("rule_group", "未分类"),
                rule_order=i
            )
            self.db.add(rule)

        await self.db.commit()

    async def _save_rules_from_classification(
        self,
        standard_id: int,
        classification: Dict[str, Any]
    ):
        """从 LLM 分类结果保存规则"""
        rules = []
        rule_groups = classification.get("rule_groups", [])

        for group in rule_groups:
            group_name = group.get("group_name", "未分类")
            for rule in group.get("rules", []):
                rules.append({
                    "title": rule.get("title", ""),
                    "content": rule.get("content", ""),
                    "source_excerpt": rule.get("source_excerpt"),
                    "source_page": rule.get("source_page"),
                    "rule_group": group_name
                })

        await self._save_rules(standard_id, rules)

    async def create_standard(
        self,
        name: str,
        content_mode: str = "pdf",
        pdf_path: Optional[str] = None,
        text_content: Optional[str] = None
    ) -> Standard:
        """创建新标准"""
        standard = Standard(
            name=name,
            content_mode=content_mode,
            status="draft"
        )

        if pdf_path and content_mode == "pdf":
            standard.raw_pdf_path = pdf_path

        self.db.add(standard)
        await self.db.commit()
        await self.db.refresh(standard)

        return standard

    async def update_standard_status(
        self,
        standard_id: int,
        status: str
    ) -> bool:
        """更新标准状态"""
        standard = await self.get_standard(standard_id)
        if not standard:
            return False

        standard.status = status
        await self.db.commit()
        return True


# 便捷函数
async def get_standard_service(db: AsyncSession, llm_service=None) -> StandardService:
    """获取 StandardService 实例"""
    return StandardService(db, llm_service)