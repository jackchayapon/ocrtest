from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
test_case_categories = Table(
    "test_case_categories",
    Base.metadata,
    Column(
        "test_case_id",
        Uuid(as_uuid=False),
        ForeignKey("test_cases.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "category_id",
        Uuid(as_uuid=False),
        ForeignKey("categories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    document_type: Mapped[str] = mapped_column(String(10), default="image", server_default="image")
    page_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    pdf_render_dpi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TestCase(Base):
    __tablename__ = "test_cases"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roi: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    ground_truth_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    ground_truth_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    document: Mapped[Document] = relationship(lazy="selectin")
    categories: Mapped[list["Category"]] = relationship(
        secondary=test_case_categories, lazy="selectin"
    )
    runs: Mapped[list["PipelineRun"]] = relationship(
        back_populates="test_case",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="PipelineRun.created_at",
    )


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    test_case_id: Mapped[str] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), index=True
    )
    pipeline_id: Mapped[str] = mapped_column(String(50), index=True)
    pipeline_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20))
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    boxes: Mapped[list] = mapped_column(JSON_TYPE, default=list)
    raw_response: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gateway_request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gateway_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    gateway_service: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gateway_model: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detector_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recognizer_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roi: Mapped[dict | None] = mapped_column(JSON_TYPE, nullable=True)
    crop_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crop_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crop_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_format: Mapped[str | None] = mapped_column(String(30), nullable=True)
    input_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crop_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    test_case: Mapped[TestCase] = relationship(back_populates="runs")
    metric_records: Mapped[list["Metric"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("pipeline_run_id", "text_kind", name="uq_metrics_run_kind"),)
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    pipeline_run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    text_kind: Mapped[str] = mapped_column(String(10))
    cer: Mapped[float | None] = mapped_column(Float, nullable=True)
    wer: Mapped[float | None] = mapped_column(Float, nullable=True)
    exact_match: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))


class PipelineConfig(Base):
    __tablename__ = "pipeline_configs"
    id: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True, default=new_id)
    pipeline_id: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    base_url: Mapped[str] = mapped_column(String(500), default="")
    endpoint: Mapped[str] = mapped_column(String(500), default="")
    http_method: Mapped[str] = mapped_column(String(10), default="POST")
    request_format: Mapped[str] = mapped_column(String(30), default="multipart")
    file_field_name: Mapped[str] = mapped_column(String(100), default="image")
    query_params: Mapped[dict] = mapped_column(JSON_TYPE, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    engine: Mapped[str | None] = mapped_column(String(100), nullable=True)
    include_roi: Mapped[bool] = mapped_column(Boolean, default=False)
    last_connection_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
