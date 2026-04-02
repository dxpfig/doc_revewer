from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import Standard, Rule, ReviewTask, ReviewResult, ModelProvider, ExportRecord
from db.session import get_db
from api.v1.auth import get_current_user
from models.database import User
from config import STANDARDS_DIR
import pdfplumber
import os
import re
import uuid
import logging

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


# ─── Model Providers ─────────────────────────────────────
@router.get("/model-providers")
async def list_model_providers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    result = await db.execute(select(ModelProvider).order_by(ModelProvider.created_at.desc()))
    items = [
        {
            "id": str(p.id),
            "user_id": str(p.user_id),
            "name": p.name,
            "provider_type": p.provider_type,
            "base_url": p.base_url,
            "api_key": p.api_key,
            "llm_model": p.llm_model,
            "embedding_model": p.embedding_model,
            "ocr_model": p.ocr_model,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in result.scalars().all()
    ]
    return {"data": items}


@router.post("/model-providers")
async def create_model_provider(
    name: str = Form(...),
    provider_type: str = Form(...),
    base_url: str = Form(None),
    api_key: str = Form(None),
    llm_model: str = Form(None),
    embedding_model: str = Form(None),
    ocr_model: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    provider = ModelProvider(
        name=name,
        user_id=current_user.id,
        provider_type=provider_type,
        base_url=base_url,
        api_key=api_key,
        llm_model=llm_model,
        embedding_model=embedding_model,
        ocr_model=ocr_model,
    )
    db.add(provider)
    await db.commit()
    await db.refresh(provider)
    return {
        "data": {
            "id": str(provider.id),
            "user_id": str(provider.user_id),
            "name": provider.name,
            "provider_type": provider.provider_type,
            "base_url": provider.base_url,
            "api_key": provider.api_key,
            "llm_model": provider.llm_model,
            "embedding_model": provider.embedding_model,
            "ocr_model": provider.ocr_model,
            "is_active": provider.is_active,
            "created_at": provider.created_at.isoformat() if provider.created_at else None,
        }
    }


@router.post("/model-providers/discover-llm-models")
async def discover_llm_models(
    provider_type: str = Form(...),
    base_url: str = Form(None),
    api_key: str = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    models = []
    if provider_type == "openai":
        models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    elif provider_type == "anthropic":
        models = ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]
    elif provider_type == "deepseek":
        models = ["deepseek-chat", "deepseek-coder"]
    elif provider_type == "moonshot":
        models = ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-8k-vision-preview"]

    return {"data": {"models": models}}


@router.post("/model-providers/{provider_id}/test")
async def test_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        pid = int(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")
    result = await db.execute(select(ModelProvider).where(ModelProvider.id == pid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # 实际测试 LLM 连接（ReActAgent + ChatModelBase，与其它业务一致）
    try:
        from agents.react_llm_bridge import create_react_backend

        agent = create_react_backend(
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            api_key=provider.api_key,
            model=provider.llm_model,
        )
        response = agent.call_llm(
            system="你是一个有帮助的助手。",
            user="请回复 'OK' 如果你收到这条消息。",
            temperature=0.1,
            max_tokens=10
        )
        if response and "OK" in response.upper():
            return {"data": {"success": True, "message": "Connection successful", "model": provider.llm_model}}
        else:
            return {"data": {"success": False, "message": f"Unexpected response: {response[:100]}"}}
    except Exception as e:
        return {"data": {"success": False, "message": str(e)}}


@router.patch("/model-providers/{provider_id}")
async def update_model_provider(
    provider_id: str,
    name: str = Form(None),
    provider_type: str = Form(None),
    base_url: str = Form(None),
    api_key: str = Form(None),
    llm_model: str = Form(None),
    embedding_model: str = Form(None),
    ocr_model: str = Form(None),
    is_active: bool = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        pid = int(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")
    result = await db.execute(select(ModelProvider).where(ModelProvider.id == pid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if name is not None:
        provider.name = name
    if provider_type is not None:
        provider.provider_type = provider_type
    if base_url is not None:
        provider.base_url = base_url
    if api_key is not None:
        provider.api_key = api_key
    if llm_model is not None:
        provider.llm_model = llm_model
    if embedding_model is not None:
        provider.embedding_model = embedding_model
    if ocr_model is not None:
        provider.ocr_model = ocr_model
    if is_active is not None:
        provider.is_active = is_active

    await db.commit()
    await db.refresh(provider)
    return {
        "data": {
            "id": str(provider.id),
            "user_id": str(provider.user_id),
            "name": provider.name,
            "provider_type": provider.provider_type,
            "base_url": provider.base_url,
            "api_key": provider.api_key,
            "llm_model": provider.llm_model,
            "embedding_model": provider.embedding_model,
            "ocr_model": provider.ocr_model,
            "is_active": provider.is_active,
            "created_at": provider.created_at.isoformat() if provider.created_at else None,
        }
    }


@router.delete("/model-providers/{provider_id}")
async def delete_model_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        pid = int(provider_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider ID")
    result = await db.execute(select(ModelProvider).where(ModelProvider.id == pid))
    provider = result.scalar_one_or_none()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    await db.delete(provider)
    await db.commit()
    return {"message": f"Model provider {provider_id} deleted"}


# ─── Standards ──────────────────────────────────────────
@router.get("/standards")
async def admin_list_standards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    result = await db.execute(select(Standard).order_by(Standard.created_at.desc()))
    items = []
    for s in result.scalars().all():
        # Get rules count using a separate query
        rules_result = await db.execute(select(Rule).where(Rule.standard_id == s.id))
        rules_count = len(rules_result.scalars().all())
        items.append({
            "id": str(s.id),
            "name": s.name,
            "content_mode": s.content_mode,
            "status": s.status,
            "rules_count": rules_count,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })
    return {"data": items, "total": len(items)}


@router.post("/standards")
async def admin_create_standard(
    name: str = Form(...),
    content_mode: str = Form("pdf"),
    file: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    standard = Standard(name=name, content_mode=content_mode, status="draft")
    rules_count = 0

    # 临时文件目录
    import os
    temp_base_dir = "/home/figodxp/tmp"
    os.makedirs(temp_base_dir, exist_ok=True)

    # Process file for all content modes (pdf, summarize, format_only)
    if file:
        file_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename or ".pdf")[1] or ".pdf"
        file_path = STANDARDS_DIR / f"{file_id}{ext}"
        with open(file_path, "wb") as f:
            f.write(await file.read())
        standard.raw_pdf_path = str(file_path)

        # Parse PDF content - try Kimi OCR first for better results
        try:
            from config import KIMI_API_KEY, KIMI_VISION_MODEL, KIMI_TEXT_MODEL
            from agents.pdf_parser_agent import PDFParserAgent

            # Use Kimi OCR for better Chinese text recognition
            agent = PDFParserAgent(
                use_kimi_ocr=True,
                kimi_api_key=KIMI_API_KEY,
                kimi_vision_model=KIMI_VISION_MODEL,
                kimi_text_model=KIMI_TEXT_MODEL,
                format_markdown=True,
                temp_dir=temp_base_dir  # 使用 /home/figodxp/tmp
            )
            result = agent.parse(str(file_path))

            # 保存解析结果到临时目录
            import uuid as uuid_module
            run_id = str(uuid_module.uuid4())[:8]
            run_dir = os.path.join(temp_base_dir, f"import_{run_id}")
            os.makedirs(run_dir, exist_ok=True)

            # 保存每页 OCR 结果
            for i, page in enumerate(result['pages'], 1):
                with open(os.path.join(run_dir, f"page_{i}_ocr.txt"), 'w', encoding='utf-8') as f:
                    f.write(page.get('text', ''))

            # 保存完整文本
            with open(os.path.join(run_dir, "full_text.txt"), 'w', encoding='utf-8') as f:
                f.write(result['text'])

            parsed_text = result["text"]
            logger.info(f"Saved OCR results to {run_dir}")

            # 使用 LLM 提取规则（而不是简单的正则）
            try:
                from services.rule_extractor_service import create_extractor_service
                extractor_service = create_extractor_service()
                # 从 run_dir 中的 OCR 文件提取规则
                rules_list = extractor_service.extract_from_directory(run_dir)
                # 转换为 Rule 对象
                rules = []
                for r in rules_list:
                    rules.append(Rule(
                        title=r.get('title', ''),
                        content=r.get('content', ''),
                        source_excerpt=r.get('content', '')[:200],
                        source_page=r.get('source_page'),
                        rule_group=r.get('rule_group', '未分类'),
                        rule_order=len(rules),
                    ))
                rules_count = len(rules)
                logger.info(f"Extracted {rules_count} rules using LLM")
            except Exception as e:
                logger.warning(f"LLM rule extraction failed, falling back to regex: {e}")
                rules = parse_rules_from_text(parsed_text)
                rules_count = len(rules)

            standard.rules = rules

            # Save parsed content to standard
            standard.parsed_content = parsed_text

        except Exception as e:
            logger.warning(f"Kimi OCR failed, falling back to pdfplumber: {e}")
            try:
                parsed_text = ""
                with pdfplumber.open(file_path) as pdf:
                    page_count = len(pdf.pages)
                    for page in pdf.pages:
                        page_num = page.page_number
                        # Try regular text extraction first
                        text = page.extract_text()
                        if not text or not text.strip():
                            # If no text, try OCR with pytesseract
                            try:
                                from PIL import Image
                                import pytesseract
                                img = page.to_image(resolution=300)
                                text = pytesseract.image_to_string(img.original, lang='chi_sim+eng')
                            except Exception:
                                text = None
                        if text and text.strip():
                            parsed_text += f"\n--- Page {page_num} ---\n{text}"
                        else:
                            parsed_text += f"\n--- Page {page_num} ---\n[图片扫描页，内容需 OCR 识别]"
                # If still empty, mark as requiring OCR
                if not parsed_text.strip():
                    parsed_text = f"[PDF 包含 {page_count} 页，已上传但内容需要 OCR 识别]"
                standard.parsed_content = parsed_text

                # Extract rules from parsed content
                rules = parse_rules_from_text(parsed_text)
                standard.rules = rules
                rules_count = len(rules)
            except Exception as e2:
                # If PDF parsing fails, still save the file path
                standard.parsed_content = f"[文件已上传，但解析失败: {str(e2)}]"

    # Commit first to get the standard ID
    db.add(standard)
    await db.commit()
    await db.refresh(standard)
    # Then get rules count
    rules_result = await db.execute(select(Rule).where(Rule.standard_id == standard.id))
    actual_rules_count = len(rules_result.scalars().all())
    return {"data": {"standard": {"id": str(standard.id), "name": standard.name}, "rules": actual_rules_count}}


@router.post("/standards/{standard_id}/save-draft")
async def save_standard_draft(
    standard_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        sid = int(standard_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid standard ID")
    result = await db.execute(select(Standard).where(Standard.id == sid))
    standard = result.scalar_one_or_none()
    if not standard:
        raise HTTPException(status_code=404, detail="Standard not found")
    standard.status = "draft"
    await db.commit()
    return {"message": "Saved as draft"}


@router.post("/standards/{standard_id}/publish")
async def publish_standard(
    standard_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        sid = int(standard_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid standard ID")
    result = await db.execute(select(Standard).where(Standard.id == sid))
    standard = result.scalar_one_or_none()
    if not standard:
        raise HTTPException(status_code=404, detail="Standard not found")
    standard.status = "published"
    await db.commit()
    return {"message": "Published successfully"}


@router.delete("/standards/{standard_id}")
async def delete_standard(
    standard_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        sid = int(standard_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid standard ID")
    result = await db.execute(select(Standard).where(Standard.id == sid))
    standard = result.scalar_one_or_none()
    if not standard:
        raise HTTPException(status_code=404, detail="Standard not found")
    
    # Delete associated review tasks and their results FIRST (before rules)
    tasks_result = await db.execute(select(ReviewTask).where(ReviewTask.standard_id == sid))
    tasks = tasks_result.scalars().all()
    for task in tasks:
        # Delete associated review results (depends on rules via rule_id)
        results_result = await db.execute(select(ReviewResult).where(ReviewResult.task_id == task.id))
        for result in results_result.scalars().all():
            await db.delete(result)
        await db.delete(task)

    # Delete associated rules
    rules_result = await db.execute(select(Rule).where(Rule.standard_id == sid))
    rules = rules_result.scalars().all()
    for rule in rules:
        await db.delete(rule)

    await db.delete(standard)
    await db.commit()
    return {"message": f"Standard {standard_id} deleted"}


# ─── Rules ──────────────────────────────────────────────
@router.get("/rules")
async def admin_list_rules(
    standard_id: str = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    query = select(Rule)
    if standard_id:
        try:
            sid = int(standard_id)
            query = query.where(Rule.standard_id == sid)
        except ValueError:
            pass
    result = await db.execute(query.order_by(Rule.rule_order))
    items = [
        {
            "id": str(r.id),
            "standard_id": str(r.standard_id),
            "title": r.title,
            "content": r.content,
            "source_excerpt": r.source_excerpt,
            "source_page": r.source_page,
            "rule_group": r.rule_group,
            "rule_order": r.rule_order,
            "enabled": True,
        }
        for r in result.scalars().all()
    ]
    return {"data": items}


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    title: str = Form(None),
    content: str = Form(None),
    source_excerpt: str = Form(None),
    source_page: int = Form(None),
    enabled: bool = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        rid = int(rule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    result = await db.execute(select(Rule).where(Rule.id == rid))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    if title is not None:
        rule.title = title
    if content is not None:
        rule.content = content
    if source_excerpt is not None:
        rule.source_excerpt = source_excerpt
    if source_page is not None:
        rule.source_page = source_page
    await db.commit()
    return {"message": "Rule updated"}


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    try:
        rid = int(rule_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid rule ID")
    result = await db.execute(select(Rule).where(Rule.id == rid))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"message": f"Rule {rule_id} deleted"}


# ─── Tasks ──────────────────────────────────────────────
@router.get("/tasks")
async def admin_list_tasks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    result = await db.execute(select(ReviewTask).order_by(ReviewTask.created_at.desc()))
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
        for t in result.scalars().all()
    ]
    return {"data": items, "total": len(items)}


import uuid


def parse_rules_from_text(text: str):
    """从文本中提取规则，支持多种格式"""
    rules = []

    # 格式1: 传统格式 (1. xxx, 第1条, 第1章)
    pattern1 = re.compile(r'^(?:\d+\.|第[\d一二三四五六七八九十]+条|第[\d]+章)\s*(.+)$', re.MULTILINE)

    # 格式2: Markdown 标题 (### 1 范围, ## 1. xxx)
    pattern2 = re.compile(r'^#{1,6}\s*(?:\d+\.?|第[\d一二三四五六七八九十]+[条章]?)\s+(.+)$', re.MULTILINE)

    # 格式3: 带括号的编号 (（1）xxx, （一）xxx)
    pattern3 = re.compile(r'^[\（\(]([\d一二三四五六七八九十]+)[\）\)]\s*(.+)$', re.MULTILINE)

    # 合并所有匹配
    seen_titles = set()

    for pattern in [pattern1, pattern2, pattern3]:
        for i, match in enumerate(pattern.finditer(text)):
            title = match.group(1).strip()[:200]
            if len(title) > 3 and title not in seen_titles:
                seen_titles.add(title)
                rules.append(Rule(
                    title=title,
                    content=title,
                    source_excerpt=match.group(0)[:200],
                    rule_order=len(rules),
                    rule_group="未分类",
                ))

    return rules