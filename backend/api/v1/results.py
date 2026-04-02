from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import ReviewTask, ReviewResult, Rule
from models.schemas import ReviewResultResponse, NonComplianceItem
from db.session import get_db
from api.v1.auth import get_current_user
from models.database import User

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{task_id}", response_model=ReviewResultResponse)
async def get_result(
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

    # Get review results
    results = await db.execute(
        select(ReviewResult).where(ReviewResult.task_id == tid)
    )
    review_results = results.scalars().all()

    total = len(review_results)
    passed = sum(1 for r in review_results if r.status == "passed")
    failed = sum(1 for r in review_results if r.status == "failed")

    non_compliance_items = []
    for r in review_results:
        if r.status == "failed":
            rule_result = await db.execute(select(Rule).where(Rule.id == r.rule_id))
            rule = rule_result.scalar_one_or_none()
            non_compliance_items.append(NonComplianceItem(
                rule_id=r.rule_id,
                rule_title=rule.title if rule else "Unknown Rule",
                rule_group=rule.rule_group if rule else None,
                match_score=r.match_score,
                matched_text=r.matched_text,
                page=None,
            ))

    return ReviewResultResponse(
        task_id=str(task.id),
        status=task.status,
        total_rules=total,
        passed_rules=passed,
        failed_rules=failed,
        non_compliance_items=non_compliance_items,
        reviewed_at=task.updated_at,
    )