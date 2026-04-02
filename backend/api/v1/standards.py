from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import Standard, Rule
from db.session import get_db
import pdfplumber
import os
import uuid
import re
from config import STANDARDS_DIR

router = APIRouter(prefix="/standards", tags=["standards"])


@router.get("")
async def list_standards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Standard).where(Standard.status == "published").order_by(Standard.created_at.desc())
    )
    standards = result.scalars().all()
    return {
        "data": [
            {
                "id": str(s.id),
                "name": s.name,
                "content_mode": s.content_mode,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in standards
        ]
    }


@router.post("")
async def create_standard(
    name: str = Form(...),
    content_mode: str = Form("pdf"),
    file: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    standard = Standard(name=name, content_mode=content_mode)

    if file and content_mode == "pdf":
        file_id = str(uuid.uuid4())
        file_path = STANDARDS_DIR / f"{file_id}.pdf"
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        standard.raw_pdf_path = str(file_path)

        parsed_text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    parsed_text += f"\n--- Page {page.page_number} ---\n{text}"

        standard.parsed_content = parsed_text
        rules = parse_rules_from_text(parsed_text)
        standard.rules = rules

    db.add(standard)
    await db.commit()
    await db.refresh(standard)
    return {
        "data": {
            "id": str(standard.id),
            "name": standard.name,
            "content_mode": standard.content_mode,
            "status": standard.status,
            "created_at": standard.created_at.isoformat() if standard.created_at else None,
            "updated_at": standard.updated_at.isoformat() if standard.updated_at else None,
        }
    }


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


# ─── 规则提取相关 ───────────────────────────────────────────

@router.post("/extract-rules")
async def extract_rules_from_ocr(
    input_dir: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    从 OCR 文件目录提取规则
    使用 LLM 从文本中提取结构化规则条目
    """
    from services.rule_extractor_service import create_extractor_service

    try:
        service = create_extractor_service()
        rules = service.extract_from_directory(input_dir)

        return {
            "success": True,
            "count": len(rules),
            "rules": rules
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-rules/text")
async def extract_rules_from_text(
    text: str = Form(...),
    page_num: int = Form(None),
):
    """
    从文本内容提取规则
    直接使用 LLM 提取结构化规则
    """
    from services.rule_extractor_service import create_extractor_service

    try:
        service = create_extractor_service()
        rules = service.extract_from_text(text, page_num)

        return {
            "success": True,
            "count": len(rules),
            "rules": rules
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))