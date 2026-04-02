from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="user")
    created_at = Column(DateTime, default=datetime.utcnow)

    review_tasks = relationship("ReviewTask", back_populates="user")
    model_providers = relationship("ModelProvider", back_populates="user")


class ModelProvider(Base):
    __tablename__ = "model_providers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    provider_type = Column(String(50), nullable=False)  # openai, anthropic, deepseek, local, moonshot
    base_url = Column(String(500), nullable=True)
    api_key = Column(String(500), nullable=True)
    llm_model = Column(String(100), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    ocr_model = Column(String(100), nullable=True)  # 专门的 OCR 模型 (如 moonshot-v1-8k-vision-preview)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="model_providers")


class Standard(Base):
    __tablename__ = "standards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    content_mode = Column(String(20), default="pdf")  # pdf, text
    status = Column(String(20), default="draft")  # draft, published
    raw_pdf_path = Column(String(500), nullable=True)
    parsed_content = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    rules = relationship("Rule", back_populates="standard", cascade="all, delete-orphan")
    review_tasks = relationship("ReviewTask", back_populates="standard")


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    standard_id = Column(Integer, ForeignKey("standards.id"), nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    source_excerpt = Column(Text, nullable=True)
    source_page = Column(Integer, nullable=True)
    rule_group = Column(String(100), nullable=True)
    rule_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    standard = relationship("Standard", back_populates="rules")
    review_results = relationship("ReviewResult", back_populates="rule")


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    standard_id = Column(Integer, ForeignKey("standards.id"), nullable=True)
    doc_name = Column(String(255), nullable=True)
    doc_path = Column(String(500), nullable=True)
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    current_stage = Column(String(100), nullable=True)
    overall_progress = Column(Float, default=0.0)
    failed_rules = Column(Integer, default=0)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="review_tasks")
    standard = relationship("Standard", back_populates="review_tasks")
    results = relationship("ReviewResult", back_populates="task", cascade="all, delete-orphan")


class ReviewResult(Base):
    __tablename__ = "review_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("review_tasks.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("rules.id"), nullable=False)
    status = Column(String(20), default="pending")  # pending, passed, failed, error
    match_score = Column(Float, default=0.0)
    matched_text = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    task = relationship("ReviewTask", back_populates="results")
    rule = relationship("Rule", back_populates="review_results")


class ExportRecord(Base):
    __tablename__ = "export_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("review_tasks.id"), nullable=True)
    export_type = Column(String(50), nullable=False)  # review-pdf, review-json
    file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)