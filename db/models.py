# 역할: inspection_runs와 inspection_results PostgreSQL 테이블의 ORM 모델을 정의합니다.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base


class InspectionRun(Base):
    # CSV 파일 하나를 검수한 "실행 기록"을 저장합니다.
    __tablename__ = "inspection_runs"
    __table_args__ = (
        # 음수 요약 값이 DB에 들어가지 않도록 DB 레벨에서도 막습니다.
        CheckConstraint(
            "total_products >= 0",
            name="ck_inspection_runs_total_products_non_negative",
        ),
        CheckConstraint(
            "total_issues >= 0",
            name="ck_inspection_runs_total_issues_non_negative",
        ),
        CheckConstraint(
            "error_count >= 0",
            name="ck_inspection_runs_error_count_non_negative",
        ),
        CheckConstraint(
            "warning_count >= 0",
            name="ck_inspection_runs_warning_count_non_negative",
        ),
        CheckConstraint(
            "file_sha256 IS NULL OR length(file_sha256) = 64",
            name="ck_inspection_runs_file_sha256_length",
        ),
        CheckConstraint(
            "length(trim(inspection_version)) > 0",
            name="ck_inspection_runs_inspection_version_not_blank",
        ),
        Index("ix_inspection_runs_created_at", "created_at"),
        Index(
            # file_sha256이 있는 신규 이력만 중복 저장을 막습니다.
            # migration 이전 기존 이력은 file_sha256이 NULL이라 이 unique index 대상에서 빠집니다.
            "ux_inspection_runs_file_sha256_inspection_version",
            "file_sha256",
            "inspection_version",
            unique=True,
            postgresql_where=text("file_sha256 IS NOT NULL"),
        ),
    )

    # PostgreSQL에서 자동 증가하는 기본키입니다.
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # 원본 CSV bytes는 저장하지 않고, 동일성 비교용 SHA-256 문자열만 저장합니다.
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # DB 기본값을 두지 않고 애플리케이션이 명시적으로 검수 규칙 버전을 넣습니다.
    inspection_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    total_products: Mapped[int] = mapped_column(Integer, nullable=False)
    total_issues: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # 생성 시각은 애플리케이션이 아니라 DB 서버 시간이 자동으로 채웁니다.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    results: Mapped[list[InspectionResult]] = relationship(
        # 실행 기록을 삭제하면 연결된 상세 결과도 함께 삭제되도록 묶어 둡니다.
        back_populates="inspection_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class InspectionResult(Base):
    # 검수 실행에서 발견된 문제 한 건을 저장합니다.
    __tablename__ = "inspection_results"
    __table_args__ = (
        # 조회가 자주 일어날 수 있는 컬럼에 인덱스를 미리 둡니다.
        Index("ix_inspection_results_inspection_run_id", "inspection_run_id"),
        Index("ix_inspection_results_product_id", "product_id"),
        Index("ix_inspection_results_status", "status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    inspection_run_id: Mapped[int] = mapped_column(
        BigInteger,
        # 부모 실행 기록이 삭제되면 DB에서도 상세 결과가 같이 지워집니다.
        ForeignKey("inspection_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_group_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    product_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_field: Mapped[str] = mapped_column(String(100), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    inspection_run: Mapped[InspectionRun] = relationship(back_populates="results")


class ETLLoadRun(Base):
    """A batch of standard ETL rows loaded into the staging tables."""

    __tablename__ = "etl_load_runs"
    __table_args__ = (
        CheckConstraint(
            "loaded_rows >= 0",
            name="ck_etl_load_runs_loaded_rows_non_negative",
        ),
        CheckConstraint(
            "total_rows IS NULL OR total_rows >= 0",
            name="ck_etl_load_runs_total_rows_non_negative",
        ),
        CheckConstraint(
            "rejected_rows IS NULL OR rejected_rows >= 0",
            name="ck_etl_load_runs_rejected_rows_non_negative",
        ),
        CheckConstraint(
            """
            (
                total_rows IS NULL
                AND rejected_rows IS NULL
                AND error_counts IS NULL
            )
            OR
            (
                total_rows IS NOT NULL
                AND rejected_rows IS NOT NULL
                AND error_counts IS NOT NULL
            )
            """,
            name="ck_etl_load_runs_quality_summary_all_or_none",
        ),
        CheckConstraint(
            "total_rows IS NULL OR total_rows = loaded_rows + rejected_rows",
            name="ck_etl_load_runs_total_rows_matches_loaded_and_rejected",
        ),
        CheckConstraint(
            "error_counts IS NULL OR jsonb_typeof(error_counts) = 'object'",
            name="ck_etl_load_runs_error_counts_object",
        ),
        CheckConstraint(
            """
            (
                reject_details_stored = false
                AND rejects_file_sha256 IS NULL
            )
            OR
            (
                reject_details_stored = true
                AND rejects_file_sha256 IS NOT NULL
                AND length(rejects_file_sha256) = 64
            )
            """,
            name="ck_etl_load_runs_reject_details_state",
        ),
        Index(
            "ux_etl_load_runs_input_profile_version",
            "input_file_sha256",
            "profile_name",
            "profile_version",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(100), nullable=False)
    profile_version: Mapped[str] = mapped_column(String(20), nullable=False)
    input_file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    loaded_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    total_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_counts: Mapped[dict[str, int] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    reject_details_stored: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("false"),
    )
    rejects_file_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    products: Mapped[list[CatalogProductStaging]] = relationship(
        back_populates="etl_load_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reject_items: Mapped[list[ETLRejectedRow]] = relationship(
        back_populates="etl_load_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ETLRejectedRow(Base):
    """A validated, privacy-masked reject row belonging to one ETL batch."""

    __tablename__ = "etl_rejected_rows"
    __table_args__ = (
        CheckConstraint(
            "source_row_number >= 2",
            name="ck_etl_rejected_rows_source_row_number_min",
        ),
        CheckConstraint(
            "jsonb_typeof(errors) = 'array'",
            name="ck_etl_rejected_rows_errors_array",
        ),
        CheckConstraint(
            "jsonb_array_length(errors) > 0",
            name="ck_etl_rejected_rows_errors_non_empty",
        ),
        CheckConstraint(
            "jsonb_typeof(masked_source_data) = 'object'",
            name="ck_etl_rejected_rows_masked_source_data_object",
        ),
        Index("ix_etl_rejected_rows_etl_load_run_id", "etl_load_run_id"),
        Index(
            "ux_etl_rejected_rows_load_run_source_row",
            "etl_load_run_id",
            "source_row_number",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    etl_load_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("etl_load_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    errors: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    masked_source_data: Mapped[dict[str, str]] = mapped_column(
        JSONB,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    etl_load_run: Mapped[ETLLoadRun] = relationship(
        back_populates="reject_items"
    )


class CatalogProductStaging(Base):
    """A validated product row waiting for downstream catalog processing."""

    __tablename__ = "catalog_products_staging"
    __table_args__ = (
        CheckConstraint(
            "stock >= 0",
            name="ck_catalog_products_staging_stock_non_negative",
        ),
        CheckConstraint(
            "price >= 0",
            name="ck_catalog_products_staging_price_non_negative",
        ),
        CheckConstraint(
            "sale_price IS NULL OR sale_price >= 0",
            name="ck_catalog_products_staging_sale_price_non_negative",
        ),
        Index("ix_catalog_products_staging_etl_load_run_id", "etl_load_run_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    etl_load_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("etl_load_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_group_id: Mapped[str] = mapped_column(String(100), nullable=False)
    product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[str] = mapped_column(String(100), nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sale_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    image_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    etl_load_run: Mapped[ETLLoadRun] = relationship(back_populates="products")
