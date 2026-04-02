from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─── Auth ───────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str


class UserInfo(BaseModel):
    user_id: int
    username: str
    role: str


# ─── Model Providers ────────────────────────────────────
class ModelProviderBase(BaseModel):
    name: str
    provider_type: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_model: Optional[str] = None
    ocr_model: Optional[str] = None  # 专门的 OCR 模型


class ModelProviderCreate(ModelProviderBase):
    pass


class ModelProviderUpdate(BaseModel):
    name: Optional[str] = None
    provider_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    llm_model: Optional[str] = None
    embedding_model: Optional[str] = None
    ocr_model: Optional[str] = None
    is_active: Optional[bool] = None


class ModelProviderResponse(ModelProviderBase):
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class DiscoverLLMRequest(BaseModel):
    provider_type: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None


class DiscoverLLMResponse(BaseModel):
    models: List[str]


class TestProviderRequest(BaseModel):
    provider_type: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    llm_model: Optional[str] = None


class TestProviderResponse(BaseModel):
    success: bool
    message: str
    model: Optional[str] = None


# ─── Standards ──────────────────────────────────────────
class StandardBase(BaseModel):
    name: str
    content_mode: Optional[str] = "pdf"


class StandardResponse(StandardBase):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─── Rules ──────────────────────────────────────────────
class RuleBase(BaseModel):
    title: str
    content: str
    source_excerpt: Optional[str] = None
    source_page: Optional[int] = None
    rule_group: Optional[str] = None


class RuleResponse(RuleBase):
    id: int
    standard_id: int
    rule_order: int

    class Config:
        from_attributes = True


# ─── Review Tasks ────────────────────────────────────────
class ReviewTaskCreate(BaseModel):
    doc_name: str
    standard_id: Optional[int] = None


class ReviewTaskResponse(BaseModel):
    task_id: str
    doc_name: Optional[str] = None
    standard_id: Optional[int] = None
    status: str
    current_stage: Optional[str] = None
    overall_progress: float
    failed_rules: int

    class Config:
        from_attributes = True


class TaskListResponse(BaseModel):
    items: List[ReviewTaskResponse]
    total: int


# ─── Review Results ──────────────────────────────────────
class NonComplianceItem(BaseModel):
    rule_id: int
    rule_title: str
    rule_group: Optional[str] = None
    match_score: float
    matched_text: Optional[str] = None
    page: Optional[int] = None


class ReviewResultResponse(BaseModel):
    task_id: str
    status: str
    total_rules: int
    passed_rules: int
    failed_rules: int
    non_compliance_items: List[NonComplianceItem]
    reviewed_at: datetime


# ─── Admin ──────────────────────────────────────────────
class AdminStandardListResponse(BaseModel):
    items: List[StandardResponse]
    total: int


class AdminRuleListResponse(BaseModel):
    items: List[RuleResponse]
    total: int


class AdminTaskListResponse(BaseModel):
    items: List[ReviewTaskResponse]
    total: int


class ExportRequest(BaseModel):
    task_id: int
    export_type: str = "review-pdf"