from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import ReviewTask, Standard, Rule, ReviewResult
from db.session import get_db
from api.v1.auth import get_current_user
from models.database import User
import logging
import os
import uuid
from config import UPLOADS_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review-tasks", tags=["review-tasks"])


@router.post("")
async def create_review_task(
    standard_id: int = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc_name = file.filename or "未命名文档"

    task = ReviewTask(
        user_id=current_user.id,
        standard_id=standard_id,
        doc_name=doc_name,
        status="pending",
    )

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or ".pdf")[1] or ".pdf"
    file_path = UPLOADS_DIR / f"{file_id}{ext}"
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    task.doc_path = str(file_path)

    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Process asynchronously（禁止传入请求内的 Session，后台任务使用独立会话）
    import asyncio

    asyncio.create_task(process_review_task(task.id))

    return {
        "data": {
            "task_id": str(task.id),
            "doc_name": task.doc_name,
            "standard_id": task.standard_id,
            "status": task.status,
            "current_stage": task.current_stage,
            "overall_progress": task.overall_progress,
            "failed_rules": task.failed_rules,
        }
    }


@router.get("")
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ReviewTask)
        .where(ReviewTask.user_id == current_user.id)
        .order_by(ReviewTask.created_at.desc())
    )
    tasks = result.scalars().all()
    items = [
        {
            "task_id": str(t.id),
            "doc_name": t.doc_name,
            "standard_id": t.standard_id,
            "status": t.status,
            "current_stage": t.current_stage,
            "overall_progress": t.overall_progress,
            "failed_rules": t.failed_rules,
        }
        for t in tasks
    ]
    return {"data": items}


@router.get("/{task_id}")
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        tid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    result = await db.execute(
        select(ReviewTask).where(ReviewTask.id == tid, ReviewTask.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "data": {
            "task_id": str(task.id),
            "doc_name": task.doc_name,
            "standard_id": task.standard_id,
            "status": task.status,
            "current_stage": task.current_stage,
            "overall_progress": task.overall_progress,
            "failed_rules": task.failed_rules,
        }
    }


@router.get("/{task_id}/result")
async def get_task_result(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        tid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    result = await db.execute(
        select(ReviewTask).where(ReviewTask.id == tid, ReviewTask.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get review results - prefer result_json (complete data from incremental processing)
    # Fallback to ReviewResult table only if result_json is empty
    review_results = []
    total = 0
    passed = 0
    failed = 0

    if task.result_json:
        # Use result_json (complete data from incremental processing)
        import json
        result_data = json.loads(task.result_json)
        results_list = result_data.get("results", [])
        summary = result_data.get("summary", {})
        total = summary.get("total", len(results_list))
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        # Convert to similar format as ReviewResult
        review_results = results_list
    else:
        # Fallback to ReviewResult table
        rr_result = await db.execute(
            select(ReviewResult).where(ReviewResult.task_id == tid)
        )
        db_results = rr_result.scalars().all()
        if db_results:
            total = len(db_results)
            passed = sum(1 for r in db_results if r.status == "passed")
            failed = sum(1 for r in db_results if r.status == "failed")
            review_results = db_results
        # Fallback to result_json
        import json
        result_data = json.loads(task.result_json)
        results_list = result_data.get("results", [])
        summary = result_data.get("summary", {})
        total = summary.get("total", len(results_list))
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        # Convert to similar format as ReviewResult
        review_results = results_list

    non_compliance_items = []
    for r in review_results:
        # Handle both ReviewResult objects and dicts from result_json
        status = r.status if hasattr(r, 'status') else r.get('status', '')
        rule_id = r.rule_id if hasattr(r, 'rule_id') else r.get('rule_id', 0)
        match_score = r.match_score if hasattr(r, 'match_score') else r.get('match_score', 0.0)
        matched_text = r.matched_text if hasattr(r, 'matched_text') else r.get('matched_text', '')
        error_message = r.error_message if hasattr(r, 'error_message') else r.get('evidence', '')

        if status == "failed":
            rule_res = await db.execute(select(Rule).where(Rule.id == int(rule_id)))
            rule = rule_res.scalar_one_or_none()
            non_compliance_items.append({
                "rule_id": rule_id,
                "rule_title": rule.title if rule else "Unknown Rule",
                "rule_group": rule.rule_group if rule else None,
                "match_score": match_score,
                "matched_text": matched_text,
                "evidence": error_message,
                "evidence_section_title": rule.title if rule else "Unknown",
                "page": None,
            })

    return {
        "data": {
            "task_id": str(task.id),
            "status": task.status,
            "total_rules": total,
            "passed_rules": passed,
            "failed_rules": failed,
            "ai_conclusion": f"审查完成，共 {total} 条规则，{passed} 条通过，{failed} 条不符合",
            "disclaimer": "AI 审查结果仅供参考，需人工复核",
            "non_compliance_items": non_compliance_items,
            "rule_failure_items": [],
            "reviewed_at": task.updated_at.isoformat() if task.updated_at else None,
        }
    }


@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除任务"""
    try:
        tid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    result = await db.execute(
        select(ReviewTask).where(ReviewTask.id == tid, ReviewTask.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # 删除关联的审查结果
    rr_result = await db.execute(
        select(ReviewResult).where(ReviewResult.task_id == tid)
    )
    for r in rr_result.scalars().all():
        await db.delete(r)

    # 删除任务
    await db.delete(task)
    await db.commit()

    return {"data": {"deleted": True, "task_id": task_id}}


@router.post("/{task_id}/exports/review-pdf")
async def export_review_pdf(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from models.database import ExportRecord
    import json

    try:
        tid = int(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task ID")

    # Get task and results
    result = await db.execute(
        select(ReviewTask).where(ReviewTask.id == tid, ReviewTask.user_id == current_user.id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Get review results
    if task.result_json:
        result_data = json.loads(task.result_json)
        results_list = result_data.get("results", [])
        summary = result_data.get("summary", {})
    else:
        results_list = []
        summary = {}

    # Generate PDF
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib import colors

    # Create PDF - use export ID as filename to make it unique
    export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "exports")
    os.makedirs(export_dir, exist_ok=True)

    # First save export record to get ID
    export = ExportRecord(task_id=tid, export_type="review-pdf")
    db.add(export)
    await db.commit()
    await db.refresh(export)

    pdf_path = os.path.join(export_dir, f"review_{export.id}.pdf")
    doc = SimpleDocTemplate(pdf_path, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, spaceAfter=20)
    story.append(Paragraph(f"文档审查报告", title_style))
    story.append(Spacer(1, 0.5*cm))

    # Summary
    story.append(Paragraph("审查汇总", styles['Heading2']))
    summary_text = f"""
    文档：{task.doc_name or '未命名'}<br/>
    审查标准：{task.standard_id or '未指定'}<br/>
    状态：{task.status}<br/>
    总规则数：{summary.get('total', len(results_list))}<br/>
    通过：{summary.get('passed', 0)}<br/>
    不符合：{summary.get('failed', 0)}<br/>
    整体评分：{summary.get('overall_score', 0) * 100:.0f}%
    """
    story.append(Paragraph(summary_text, styles['Normal']))
    story.append(Spacer(1, 0.5*cm))

    # Failed items
    failed_items = [r for r in results_list if r.get('status') == 'failed']
    if failed_items:
        story.append(Paragraph("不符合项详情", styles['Heading2']))
        story.append(Spacer(1, 0.3*cm))

        for idx, item in enumerate(failed_items, 1):
            rule_id = item.get('rule_id', 'N/A')
            rule_title = item.get('rule_title', 'Unknown')
            matched_text = item.get('matched_text', '')
            evidence = item.get('evidence', '')

            story.append(Paragraph(f"{idx}. 规则 {rule_id} - {rule_title}", styles['Heading3']))
            if matched_text:
                story.append(Paragraph(f"<b>文档匹配内容：</b><br/>{matched_text[:500]}", styles['Normal']))
            if evidence:
                story.append(Paragraph(f"<b>AI 证据：</b><br/>{evidence[:500]}", styles['Normal']))
            story.append(Spacer(1, 0.3*cm))

    # Passed items
    passed_items = [r for r in results_list if r.get('status') == 'passed']
    if passed_items:
        story.append(PageBreak())
        story.append(Paragraph("通过项清单", styles['Heading2']))
        story.append(Spacer(1, 0.3*cm))

        passed_data = [[f"规则 {r.get('rule_id')}", r.get('rule_title', 'Unknown')[:50]] for r in passed_items[:20]]
        if passed_data:
            t = Table(passed_data, colWidths=[2*cm, 13*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
            ]))
            story.append(t)

    # Disclaimer
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("免责声明：AI 审查结果仅供参考，需人工复核。", styles['Normal']))

    # Build PDF
    doc.build(story)

    download_url = f"/api/v1/review-tasks/exports-file/{export.id}/review.pdf"
    return {"data": {"download_url": download_url}}


# Export file download endpoint
@router.get("/exports-file/{export_id}/review.pdf")
async def download_review_pdf(
    export_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Download exported PDF"""
    from fastapi.responses import FileResponse

    export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "exports")
    pdf_path = os.path.join(export_dir, f"review_{export_id}.pdf")

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="Export file not found")

    return FileResponse(pdf_path, media_type="application/pdf", filename=f"review_{export_id}.pdf")


async def process_review_task(task_id: int):
    """Background review processing using LLM-based review service."""
    from db.session import async_session_maker
    from agentscope_runtime import (
        is_agentscope_initialized,
        ensure_agentscope_trace_for_worker,
        flush_agentscope_traces,
        register_agentscope_task_run,
        stop_agentscope_run,
    )
    from services import get_review_service

    # 在第一个 await 之前写入本 Task 的 ContextVar（与 lifespan / HTTP 请求上下文隔离）
    ensure_agentscope_trace_for_worker()
    if not is_agentscope_initialized():
        logger.warning(
            "AgentScope 未初始化（启动时 full init 与 OTLP 降级均失败）；"
            "本次审查不会产生 Studio TRACE。请先启动 Studio 再启后端，或检查 AGENTSCOPE_STUDIO_URL。"
        )

    try:
        async with async_session_maker() as db:
            result = await db.execute(select(ReviewTask).where(ReviewTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return

            task.status = "processing"
            task.current_stage = "初始化"
            await db.commit()

            if not task.doc_path or not os.path.exists(task.doc_path):
                task.status = "failed"
                task.current_stage = "文档加载失败"
                await db.commit()
                return

            # Check if standard is set
            if not task.standard_id:
                task.status = "completed"
                task.current_stage = "完成（无标准）"
                task.overall_progress = 100.0
                await db.commit()
                return

            # Check if rules exist
            rules_result = await db.execute(
                select(Rule).where(Rule.standard_id == task.standard_id)
            )
            rules = rules_result.scalars().all()

            if not rules:
                task.status = "completed"
                task.current_stage = "完成（无规则）"
                task.overall_progress = 100.0
                await db.commit()
                return

            # Try LLM-based review (ReActAgent + KimiHTTPChatModel)
            try:
                # 须在**本后台任务**内注册 run 并打开 trace_enabled（与 lifespan 不同 ContextVar）
                register_agentscope_task_run(str(task_id))
                review_service = await get_review_service(db)
                await review_service.run_review(task_id, use_llm=True)
                return
            except Exception as e:
                logger.error("LLM review failed, falling back to simple: %s", str(e))
                await _simple_review_task(task_id, db, task, rules)
    finally:
        flush_agentscope_traces()
        stop_agentscope_run()


async def _simple_review_task(task_id: int, db: AsyncSession, task: ReviewTask, rules):
    """Simple keyword-based review (fallback when no LLM provider)."""
    import pdfplumber

    doc_text = ""
    with pdfplumber.open(task.doc_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            if text:
                doc_text += f"\n--- Page {i+1} ---\n{text}"

    total = len(rules)
    failed = 0
    passed = 0

    for idx, rule in enumerate(rules):
        task.current_stage = f"审查规则 {idx+1}/{total}: {rule.title[:30]}"
        task.overall_progress = round((idx / total) * 100, 1)
        await db.commit()

        rule_keywords = rule.title.lower().split()
        matched = False
        matched_text = None
        score = 0.0

        for kw in rule_keywords:
            if len(kw) > 3 and kw in doc_text.lower():
                matched = True
                score = min(1.0, score + 0.4)
                idx_lower = doc_text.lower().find(kw)
                start = max(0, idx_lower - 80)
                end = min(len(doc_text), idx_lower + 150)
                matched_text = doc_text[start:end]

        status = "passed" if score >= 0.4 else "failed"
        if matched:
            passed += 1
        else:
            failed += 1

        review_result = ReviewResult(
            task_id=task.id,
            rule_id=rule.id,
            status=status,
            match_score=score,
            matched_text=matched_text,
        )
        db.add(review_result)

    task.status = "completed"
    task.current_stage = "完成"
    task.overall_progress = 100.0
    task.failed_rules = failed
    await db.commit()