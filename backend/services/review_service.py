"""
Review Service - 文档审查服务
调用 document_reviewer agent，支持异步任务处理
"""
import logging
import os
import json
import asyncio
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import ReviewTask, ReviewResult, Rule, Standard
from agents.agentscope_agent import (
    create_document_review_react_agent,
    msg_to_text,
)
from agents.pdf_parser_agent import PDFParserAgent
from services.vector_service import VectorService

logger = logging.getLogger(__name__)


def parse_docx(docx_path: str) -> str:
    """解析 docx 文件返回纯文本"""
    try:
        from docx import Document
        doc = Document(docx_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as e:
        logger.error(f"Failed to parse docx: {e}")
        raise ValueError(f"无法解析 docx 文件: {e}")


def parse_document(doc_path: str) -> str:
    """根据文件类型解析文档"""
    ext = os.path.splitext(doc_path)[1].lower()
    if ext == '.docx':
        return parse_docx(doc_path)
    else:
        # 默认使用 PDF 解析
        parser = PDFParserAgent()
        return parser.parse_to_text(doc_path)


class ReviewService:
    """Service for managing document review tasks"""

    def __init__(self, db: AsyncSession, llm_service=None):
        self.db = db
        self.llm_service = llm_service
        self.pdf_parser = PDFParserAgent()

    async def _llm_review(
        self,
        doc_content: str,
        rules: List[Rule],
        batch_size: int = 5
    ) -> Dict[str, Any]:
        """
        使用 ReActAgent + KimiHTTPChatModel 进行文档审查（AgentScope 内置 Agent / trace_llm）

        Args:
            doc_content: 文档内容
            rules: 规则列表
            batch_size: 每批处理规则数

        Returns:
            审查结果
        """
        import re

        api_key = os.environ.get("KIMI_API_KEY")
        if not api_key:
            raise ValueError("KIMI_API_KEY not set")

        # 截断文档内容
        truncated_doc = doc_content[:15000] if len(doc_content) > 15000 else doc_content

        all_results = []

        # 分批处理
        for i in range(0, len(rules), batch_size):
            batch = rules[i:i + batch_size]

            # 格式化规则
            rules_text = "\n".join([
                f"{j+1}. 【{r.title}】{r.content}"
                for j, r in enumerate(batch)
            ])

            system_prompt = """你是一个专业的文档审查助手。你的任务是根据给定的审查规则，对文档进行严格审查，并给出明确的通过/失败判定及证据。

## 输出格式要求
返回有效的 JSON 格式，包含以下字段：
- results: 审查结果列表，每项包含 rule_id, rule_title, status, match_score, matched_text, evidence, suggestion
- summary: 汇总信息，包含 total, passed, failed, overall_score

## 审查原则
1. 严格按规则审查，不放过任何违规点
2. 证据必须具体，引用文档中的实际内容
3. 对于不明确的点，倾向于判定为通过但需说明
4. 如果文档中未提供足够信息判断，标记为 passed 并说明原因

## 评分标准
- match_score: 0.0-1.0，1.0 表示完全符合
- 整体评分 = 通过数 / 总数"""

            user_prompt = f"""请审查以下文档是否符合标准规则。

## 文档内容
---
{truncated_doc}
---

## 审查规则
---
{rules_text}
---

请返回 JSON 格式的审查结果。"""

            # ReActAgent（与 game/werewolves/test_kimi 一致），每批新实例避免 memory 串话
            from agentscope.message import Msg

            agent = create_document_review_react_agent(
                api_key=api_key,
                sys_prompt=system_prompt,
                name="DocReviewer",
                max_iters=5,
            )

            try:
                reply_msg = await agent(Msg("user", user_prompt, "user"))
                response = msg_to_text(reply_msg)

                # 解析 JSON
                try:
                    json_match = re.search(r"\{[\s\S]*\}", response)
                    if json_match:
                        data = json.loads(json_match.group(0))
                        batch_results = data.get("results", [])
                        all_results.extend(batch_results)
                    else:
                        raise ValueError("No JSON found")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse batch {i//batch_size}: {e}")
                    # 返回降级结果
                    for j, r in enumerate(batch):
                        all_results.append({
                            "rule_id": str(r.id),
                            "rule_title": r.title,
                            "status": "passed",
                            "match_score": 0.5,
                            "matched_text": "",
                            "evidence": "未能完成审查",
                            "suggestion": "请人工复查"
                        })

            except Exception as e:
                logger.error(f"LLM call failed for batch {i//batch_size}: {e}")
                # 返回降级结果
                for j, r in enumerate(batch):
                    all_results.append({
                        "rule_id": str(r.id),
                        "rule_title": r.title,
                        "status": "passed",
                        "match_score": 0.5,
                        "matched_text": "",
                        "evidence": str(e),
                        "suggestion": "请重试"
                    })

        # 计算汇总
        passed = sum(1 for r in all_results if r.get("status") == "passed")
        failed = sum(1 for r in all_results if r.get("status") == "failed")
        total = len(all_results)
        overall_score = round(passed / total if total > 0 else 0, 2)

        return {
            "results": all_results,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "overall_score": overall_score
            }
        }

    async def create_task(
        self,
        user_id: int,
        doc_name: str,
        doc_path: str,
        standard_id: Optional[int] = None
    ) -> ReviewTask:
        """创建审查任务"""
        task = ReviewTask(
            user_id=user_id,
            doc_name=doc_name,
            doc_path=doc_path,
            standard_id=standard_id,
            status="pending",
            current_stage="created",
            overall_progress=0.0
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def get_task(self, task_id: int) -> Optional[ReviewTask]:
        """获取任务详情"""
        result = await self.db.execute(
            select(ReviewTask).where(ReviewTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def get_user_tasks(self, user_id: int) -> List[ReviewTask]:
        """获取用户的所有任务"""
        result = await self.db.execute(
            select(ReviewTask)
            .where(ReviewTask.user_id == user_id)
            .order_by(ReviewTask.created_at.desc())
        )
        return result.scalars().all()

    async def update_task_progress(
        self,
        task_id: int,
        stage: str,
        progress: float,
        status: Optional[str] = None
    ):
        """更新任务进度"""
        task = await self.get_task(task_id)
        if not task:
            return

        task.current_stage = stage
        task.overall_progress = progress
        if status:
            task.status = status
        task.updated_at = datetime.utcnow()

        await self.db.commit()

    async def _fetch_rules(self, standard_id: int) -> List[Rule]:
        """获取标准下的规则"""
        rules_result = await self.db.execute(
            select(Rule).where(Rule.standard_id == standard_id)
        )
        return rules_result.scalars().all()

    async def run_review(
        self,
        task_id: int,
        use_llm: bool = True,
        incremental: bool = True
    ) -> Dict[str, Any]:
        """
        执行文档审查

        Args:
            task_id: 任务 ID
            use_llm: 是否使用 LLM 审查
            incremental: 是否使用增量分组处理（推荐用于大量规则/大文档）

        Returns:
            审查结果
        """
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        try:
            # 更新状态
            await self.update_task_progress(task_id, "initializing", 0, "processing")

            # 检查文档是否存在
            if not task.doc_path or not os.path.exists(task.doc_path):
                raise ValueError(f"Document not found: {task.doc_path}")

            # 获取规则
            rules = []
            if task.standard_id:
                rules = await self._fetch_rules(task.standard_id)

            if not rules:
                raise ValueError("No rules available for review")

            # 根据规则数量和 incremental 标志决定处理方式
            if incremental and len(rules) > 10:
                # 使用增量分组处理（适用于大量规则）
                logger.info(f"使用增量分组处理: {len(rules)} 条规则")
                return await self._incremental_review(task_id)
            else:
                # 使用传统批量处理
                logger.info(f"使用传统批量处理: {len(rules)} 条规则")
                return await self._run_review_batch(task_id)

        except Exception as e:
            logger.error(f"Review failed: {str(e)}")
            # 确保 task 对象存在
            task = await self.get_task(task_id)
            if task:
                task.status = "failed"
                task.current_stage = "failed"
                task.result_json = json.dumps({"error": str(e)}, ensure_ascii=False)
                await self.db.commit()

            return {
                "task_id": task_id,
                "status": "failed",
                "error": str(e)
            }

    async def _run_review_batch(self, task_id: int) -> Dict[str, Any]:
        """
        传统批量审查模式（兼容少量规则场景）
        """
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        try:
            # 解析文档
            await self.update_task_progress(task_id, "parsing", 10, "processing")
            doc_content = parse_document(task.doc_path)
            await self.update_task_progress(task_id, "parsing", 30)

            # 获取规则
            rules = []
            if task.standard_id:
                rules = await self._fetch_rules(task.standard_id)

            if not rules:
                raise ValueError("No rules available for review")

            await self.update_task_progress(task_id, "preparing", 50)

            # 使用 ReActAgent 审查
            try:
                review_result = await self._llm_review(doc_content, rules)
                await self._save_review_results(task_id, review_result)

                summary = review_result.get("summary", {})
                failed = summary.get("failed", 0)

                task.status = "completed"
                task.current_stage = "completed"
                task.overall_progress = 100.0
                task.failed_rules = failed
                task.result_json = json.dumps(review_result, ensure_ascii=False)
                task.updated_at = datetime.utcnow()
                await self.db.commit()

                return {
                    "task_id": task_id,
                    "status": "completed",
                    "results": review_result.get("results", []),
                    "summary": summary
                }
            except Exception as e:
                logger.error(f"LLM review failed: {str(e)}")

            # 降级到简单匹配
            await self.update_task_progress(task_id, "reviewing", 70)
            simple_results = self._simple_review(doc_content, rules)
            await self._save_review_results(task_id, simple_results)

            task.status = "completed"
            task.current_stage = "completed"
            task.overall_progress = 100.0
            task.failed_rules = simple_results.get("summary", {}).get("failed", 0)
            task.result_json = json.dumps(simple_results, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            await self.db.commit()

            return {
                "task_id": task_id,
                "status": "completed",
                "results": simple_results.get("results", []),
                "summary": simple_results.get("summary", {})
            }
        except Exception as e:
            raise

    def _simple_review(
        self,
        doc_content: str,
        rules: List[Rule]
    ) -> Dict[str, Any]:
        """简单的规则匹配（关键词匹配）"""
        results = []
        passed = 0
        failed = 0

        doc_lower = doc_content.lower()

        for rule in rules:
            # 简单关键词匹配
            keywords = rule.title.split()[:3]  # 取标题前3个词
            matched = any(kw.lower() in doc_lower for kw in keywords if len(kw) > 2)

            if matched:
                passed += 1
                status = "passed"
                match_score = 1.0
            else:
                failed += 1
                status = "failed"
                match_score = 0.0

            results.append({
                "rule_id": str(rule.id),
                "rule_title": rule.title,
                "status": status,
                "match_score": match_score,
                "matched_text": "",
                "evidence": "简单匹配" if matched else "未找到匹配内容",
                "suggestion": "请使用 LLM 审查以获得更准确的结果"
            })

        total = len(rules)
        return {
            "results": results,
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "overall_score": round(passed / total if total > 0 else 0, 2)
            }
        }

    async def _save_review_results(
        self,
        task_id: int,
        review_result: Dict[str, Any]
    ):
        """保存审查结果到数据库"""
        # 先删除旧结果
        existing = await self.db.execute(
            select(ReviewResult).where(ReviewResult.task_id == task_id)
        )
        for r in existing.scalars().all():
            await self.db.delete(r)

        # 添加新结果
        for result in review_result.get("results", []):
            review_result_db = ReviewResult(
                task_id=task_id,
                rule_id=int(result.get("rule_id", 0)),
                status=result.get("status", "pending"),
                match_score=result.get("match_score", 0.0),
                matched_text=result.get("matched_text"),
                error_message=result.get("evidence")
            )
            self.db.add(review_result_db)

        await self.db.commit()

    async def get_task_results(self, task_id: int) -> Optional[Dict[str, Any]]:
        """获取任务的审查结果"""
        task = await self.get_task(task_id)
        if not task:
            return None

        # 从数据库获取详细结果
        results = await self.db.execute(
            select(ReviewResult).where(ReviewResult.task_id == task_id)
        )

        return {
            "task_id": task_id,
            "doc_name": task.doc_name,
            "status": task.status,
            "current_stage": task.current_stage,
            "overall_progress": task.overall_progress,
            "failed_rules": task.failed_rules,
            "results": [
                {
                    "id": r.id,
                    "rule_id": r.rule_id,
                    "status": r.status,
                    "match_score": r.match_score,
                    "matched_text": r.matched_text,
                    "error_message": r.error_message
                }
                for r in results.scalars().all()
            ],
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None
        }

    async def delete_task(self, task_id: int) -> bool:
        """删除任务及其结果"""
        task = await self.get_task(task_id)
        if not task:
            return False

        # 删除关联的结果
        results = await self.db.execute(
            select(ReviewResult).where(ReviewResult.task_id == task_id)
        )
        for r in results.scalars().all():
            await self.db.delete(r)

        # 删除任务
        await self.db.delete(task)
        await self.db.commit()

        return True

    # ========== 增量分组处理方法 ==========

    def _group_rules(self, rules: List[Rule], group_size: int = 10) -> List[List[Rule]]:
        """
        将规则按组划分，每组最多 group_size 条

        Args:
            rules: 规则列表
            group_size: 每组规则数量

        Returns:
            分组后的规则列表
        """
        groups = []
        for i in range(0, len(rules), group_size):
            groups.append(rules[i:i + group_size])
        logger.info(f"将 {len(rules)} 条规则分成 {len(groups)} 组，每组 {group_size} 条")
        return groups

    def _extract_rule_keywords(self, rule: Rule) -> List[str]:
        """
        从规则中提取关键词用于文档搜索

        Args:
            rule: 规则对象

        Returns:
            关键词列表
        """
        keywords = set()

        # 从标题提取
        title = rule.title or ""
        # 提取中文词和英文词
        chinese_words = re.findall(r'[\u4e00-\u9fff]+', title)
        english_words = re.findall(r'[a-zA-Z]+', title)

        for word in chinese_words + english_words:
            if len(word) >= 2:  # 过滤单字
                keywords.add(word)

        # 从内容提取前5个关键词
        content = rule.content or ""
        content_chinese = re.findall(r'[\u4e00-\u9fff]{2,}', content)
        content_english = re.findall(r'[a-zA-Z]{3,}', content)

        for word in (content_chinese + content_english)[:5]:
            keywords.add(word)

        return list(keywords)[:10]  # 最多返回10个关键词

    async def _build_doc_chunks(
        self,
        doc_path: str,
        chunk_size: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        将文档分成 chunks，建立索引

        Args:
            doc_path: 文档路径
            chunk_size: 每个 chunk 的字符数

        Returns:
            chunks 列表
        """
        logger.info(f"开始构建文档 chunks: {doc_path}")

        # 根据文件类型选择解析方法
        ext = os.path.splitext(doc_path)[1].lower()
        if ext == '.docx':
            full_text = parse_docx(doc_path)
        else:
            # 默认使用 PDF 解析
            full_text = parse_document(doc_path)

        chunks = []
        start = 0
        chunk_idx = 0

        while start < len(full_text):
            end = min(start + chunk_size, len(full_text))
            chunk_text = full_text[start:end]

            chunks.append({
                "chunk_id": chunk_idx,
                "text": chunk_text,
                "start": start,
                "end": end,
                "tokens": self._tokenize_text(chunk_text)
            })

            start = end
            chunk_idx += 1

        logger.info(f"文档分成 {len(chunks)} 个 chunks")
        return chunks

    def _tokenize_text(self, text: str) -> List[str]:
        """简单分词"""
        text_lower = text.lower()
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text_lower)
        # 过滤停用词和过短的词
        stopwords = {'的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好', '自己', '这'}
        return [t for t in tokens if t not in stopwords and len(t) > 1]

    async def _search_relevant_chunks(
        self,
        keywords: List[str],
        chunks: List[Dict[str, Any]],
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        搜索与关键词相关的文档 chunks

        Args:
            keywords: 关键词列表
            chunks: 文档 chunks
            top_k: 返回前 k 个最相关的 chunk

        Returns:
            相关的 chunks 列表
        """
        if not keywords or not chunks:
            return chunks[:top_k] if chunks else []

        # 计算每个 chunk 与关键词的相似度
        keyword_set = set(keywords)
        scored_chunks = []

        for chunk in chunks:
            chunk_tokens = set(chunk.get("tokens", []))
            # 计算交集
            intersection = len(keyword_set & chunk_tokens)
            score = intersection / len(keyword_set) if keyword_set else 0

            scored_chunks.append({
                "chunk": chunk,
                "score": score
            })

        # 按分数排序
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)

        # 返回 top_k
        relevant_chunks = [item["chunk"] for item in scored_chunks[:top_k]]
        logger.info(f"关键词 '{keywords[:3]}...' 找到 {len(relevant_chunks)} 个相关 chunks")

        return relevant_chunks

    async def _incremental_review(
        self,
        task_id: int,
        group_size: int = 10,
        chunk_size: int = 1000,
        max_chunks_per_group: int = 10
    ) -> Dict[str, Any]:
        """
        增量分组审查主函数

        Args:
            task_id: 任务 ID
            group_size: 每组规则数量
            chunk_size: 每个 chunk 的字符数
            max_chunks_per_group: 每组最多加载的 chunk 数量

        Returns:
            审查结果
        """
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        logger.info(f"开始增量分组审查: task_id={task_id}")

        # 1. 获取规则
        rules = []
        if task.standard_id:
            rules = await self._fetch_rules(task.standard_id)

        if not rules:
            raise ValueError("No rules available for review")

        # 2. 规则分组
        rule_groups = self._group_rules(rules, group_size=group_size)

        # 3. 预处理文档 chunks（如果文档存在）
        doc_chunks = []
        if task.doc_path and os.path.exists(task.doc_path):
            await self.update_task_progress(
                task_id, "building_chunks", 5, "processing"
            )
            doc_chunks = await self._build_doc_chunks(task.doc_path, chunk_size)

        all_results = []

        # 4. 逐组处理
        total_groups = len(rule_groups)
        for group_idx, group in enumerate(rule_groups):
            group_num = group_idx + 1
            progress_start = 5 + (group_idx / total_groups) * 90
            progress_end = 5 + ((group_idx + 1) / total_groups) * 90

            await self.update_task_progress(
                task_id,
                f"审查第 {group_num}/{total_groups} 组 ({len(group)} 条规则)",
                progress_start,
                "processing"
            )

            # 4.1 提取该组规则的关键词
            keywords = []
            for rule in group:
                keywords.extend(self._extract_rule_keywords(rule))

            # 去重
            keywords = list(set(keywords))[:20]

            # 4.2 搜索相关 chunks
            relevant_chunks = []
            if doc_chunks:
                relevant_chunks = await self._search_relevant_chunks(
                    keywords, doc_chunks, top_k=max_chunks_per_group
                )

            # 4.3 构建审查内容
            if relevant_chunks:
                review_content = "\n\n---\n\n".join([
                    f"【文档段落 {i+1}】\n{chunk['text']}"
                    for i, chunk in enumerate(relevant_chunks)
                ])
            else:
                # 如果没有相关 chunks，使用文档前一部分
                review_content = doc_chunks[0]["text"] if doc_chunks else ""

            # 4.4 创建 Worker Agent 并审查
            if review_content:
                result = await self._review_with_agent(
                    group, review_content, group_idx
                )
                all_results.extend(result)
            else:
                # 没有内容，跳过该组
                logger.warning(f"组 {group_num} 无审查内容")
                for rule in group:
                    all_results.append({
                        "rule_id": str(rule.id),
                        "rule_title": rule.title,
                        "status": "passed",
                        "match_score": 0.5,
                        "matched_text": "",
                        "evidence": "文档内容为空",
                        "suggestion": "请检查文档"
                    })

            # 4.5 保存该组结果
            await self._save_group_results(task_id, group, all_results[-len(group):])

            # 4.6 更新进度
            current_progress = progress_end
            await self.update_task_progress(
                task_id,
                f"完成第 {group_num}/{total_groups} 组",
                current_progress
            )

        # 5. 完成审查
        await self._finalize_review(task_id, all_results)

        return {
            "task_id": task_id,
            "status": "completed",
            "results": all_results,
            "summary": self._calculate_summary(all_results)
        }

    async def _review_with_agent(
        self,
        rules: List[Rule],
        doc_content: str,
        group_idx: int
    ) -> List[Dict[str, Any]]:
        """
        使用 ReActAgent 审查一组规则

        Args:
            rules: 规则列表
            doc_content: 文档内容
            group_idx: 组索引

        Returns:
            审查结果列表
        """
        import re as re_module

        api_key = os.environ.get("KIMI_API_KEY")
        if not api_key:
            raise ValueError("KIMI_API_KEY not set")

        # 截断内容
        truncated_doc = doc_content[:15000] if len(doc_content) > 15000 else doc_content

        # 格式化规则
        rules_text = "\n".join([
            f"{j+1}. 【{r.title}】{r.content}"
            for j, r in enumerate(rules)
        ])

        system_prompt = """你是一个专业的文档审查助手。你的任务是根据给定的审查规则，对文档进行严格审查，并给出明确的通过/失败判定及证据。

## 输出格式要求
返回有效的 JSON 格式，包含以下字段：
- results: 审查结果列表，每项包含 rule_id, rule_title, status, match_score, matched_text, evidence, suggestion

## 审查原则
1. 严格按规则审查，不放过任何违规点
2. 证据必须具体，引用文档中的实际内容
3. 对于不明确的点，倾向于判定为通过但需说明
4. 如果文档中未提供足够信息判断，标记为 passed 并说明原因"""

        user_prompt = f"""请审查以下文档是否符合标准规则。

## 文档内容
---
{truncated_doc}
---

## 审查规则
---
{rules_text}
---

请返回 JSON 格式的审查结果，格式如下：
{{"results": [{{"rule_id": "1", "rule_title": "规则标题", "status": "passed/failed", "match_score": 0.8, "matched_text": "匹配的文本", "evidence": "证据", "suggestion": "建议"}}]}}"""

        from agentscope.message import Msg

        agent = create_document_review_react_agent(
            api_key=api_key,
            sys_prompt=system_prompt,
            name=f"Reviewer-Group-{group_idx}",
            max_iters=5,
        )

        try:
            reply_msg = await agent(Msg("user", user_prompt, "user"))
            response = msg_to_text(reply_msg)

            # 解析 JSON
            json_match = re_module.search(r"\{[\s\S]*\}", response)
            if json_match:
                data = json.loads(json_match.group(0))
                return data.get("results", [])
            else:
                raise ValueError("No JSON found")
        except Exception as e:
            logger.error(f"LLM call failed for group {group_idx}: {e}")
            # 返回降级结果
            return [{
                "rule_id": str(r.id),
                "rule_title": r.title,
                "status": "passed",
                "match_score": 0.5,
                "matched_text": "",
                "evidence": str(e),
                "suggestion": "请重试"
            } for r in rules]

    async def _save_group_results(
        self,
        task_id: int,
        group: List[Rule],
        results: List[Dict[str, Any]]
    ):
        """
        保存一组规则的结果（增量保存）

        Args:
            task_id: 任务 ID
            group: 规则组
            results: 审查结果
        """
        for result in results:
            rule_id = int(result.get("rule_id", 0))

            # 检查是否已存在
            existing = await self.db.execute(
                select(ReviewResult).where(
                    ReviewResult.task_id == task_id,
                    ReviewResult.rule_id == rule_id
                )
            )
            db_result = existing.scalar_one_or_none()

            if db_result:
                # 更新
                db_result.status = result.get("status", "pending")
                db_result.match_score = result.get("match_score", 0.0)
                db_result.matched_text = result.get("matched_text")
                db_result.error_message = result.get("evidence")
            else:
                # 新增
                review_result_db = ReviewResult(
                    task_id=task_id,
                    rule_id=rule_id,
                    status=result.get("status", "pending"),
                    match_score=result.get("match_score", 0.0),
                    matched_text=result.get("matched_text"),
                    error_message=result.get("evidence")
                )
                self.db.add(review_result_db)

        await self.db.commit()

    def _calculate_summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """计算汇总信息"""
        passed = sum(1 for r in results if r.get("status") == "passed")
        failed = sum(1 for r in results if r.get("status") == "failed")
        total = len(results)
        overall_score = round(passed / total if total > 0 else 0, 2)

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "overall_score": overall_score
        }

    async def _finalize_review(self, task_id: int, results: List[Dict[str, Any]]):
        """完成审查，更新任务状态"""
        task = await self.get_task(task_id)
        if not task:
            return

        summary = self._calculate_summary(results)

        task.status = "completed"
        task.current_stage = "completed"
        task.overall_progress = 100.0
        task.failed_rules = summary["failed"]
        task.result_json = json.dumps({
            "results": results,
            "summary": summary
        }, ensure_ascii=False)
        task.updated_at = datetime.utcnow()

        await self.db.commit()


# 后台任务处理
class ReviewTaskRunner:
    """后台任务运行器"""

    def __init__(self, db: AsyncSession, llm_service=None):
        self.db = db
        self.llm_service = llm_service
        self._running = False

    async def start(self):
        """启动任务处理器"""
        self._running = True
        while self._running:
            await self._process_pending_tasks()
            await asyncio.sleep(5)  # 每5秒检查一次

    def stop(self):
        """停止任务处理器"""
        self._running = False

    async def _process_pending_tasks(self):
        """处理待处理的任务"""
        result = await self.db.execute(
            select(ReviewTask)
            .where(ReviewTask.status == "pending")
            .order_by(ReviewTask.created_at)
            .limit(1)
        )
        task = result.scalar_one_or_none()

        if task:
            service = ReviewService(self.db, self.llm_service)
            await service.run_review(task.id)


# 便捷函数
async def get_review_service(db: AsyncSession, llm_service=None) -> ReviewService:
    """获取 ReviewService 实例"""
    return ReviewService(db, llm_service)