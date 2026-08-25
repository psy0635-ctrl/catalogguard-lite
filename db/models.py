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
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from config.settings import (
    ETL_INITIAL_SOURCE_REF_MAX_LENGTH,
    ETL_INITIAL_SOURCE_TYPE_MAX_LENGTH,
    ETL_INITIAL_SOURCE_TYPE_UNKNOWN,
    ETL_INITIAL_SOURCE_TYPES,
)

from db.base import Base


class User(Base):
    # 로그인 계정 하나를 나타냅니다. Authentication + RBAC MVP 범위의 최소 필드만 둡니다.
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('viewer', 'operator')",
            name="ck_users_role",
        ),
        CheckConstraint(
            "length(trim(username)) > 0",
            name="ck_users_username_not_blank",
        ),
        Index("ux_users_username", "username", unique=True),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    # 평문 비밀번호는 저장하지 않고 bcrypt hash 문자열만 저장합니다.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


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
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
        CheckConstraint(
            "initial_source_type IN ("
            + ", ".join(f"'{value}'" for value in ETL_INITIAL_SOURCE_TYPES)
            + ")",
            name="ck_etl_load_runs_initial_source_type",
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
    profile_definition_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
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
    # Source lineage: 이 배치를 "최초로" 만든 입력 경로입니다. actor(누가 실행했는가)와는 다른 개념이라,
    # 예를 들어 CLI 적재는 actor가 NULL이면서 initial_source_type은 'cli'가 됩니다.
    # server_default를 영구로 두지 않는 이유는, 새 유입 경로가 값을 넘기는 것을 잊었을 때
    # 조용히 'unknown'으로 저장되지 않고 드러나게 하기 위해서입니다.
    initial_source_type: Mapped[str] = mapped_column(
        String(ETL_INITIAL_SOURCE_TYPE_MAX_LENGTH),
        nullable=False,
        # ORM 기본값만 두고 DB server_default는 두지 않습니다. 실제 유입 경로는 모두 값을 명시하고,
        # 값을 주지 않는 쪽(과거 row를 흉내 내는 테스트 등)은 정직하게 unknown이 됩니다.
        default=ETL_INITIAL_SOURCE_TYPE_UNKNOWN,
    )
    # 비밀이 없는 최소 locator입니다. HTTP feed URL 원문·query·token은 절대 저장하지 않습니다.
    initial_source_ref: Mapped[str | None] = mapped_column(
        String(ETL_INITIAL_SOURCE_REF_MAX_LENGTH),
        nullable=True,
    )
    # Actor audit: 이 배치를 실행한 로그인 사용자입니다. 이 컬럼이 생기기 전(migration 이전) row와
    # CLI(etl.load_cli)로 적재된 row는 로그인 사용자가 없어 둘 다 NULL로 남습니다.
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
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
    promoted_products: Mapped[list[CatalogProduct]] = relationship(
        back_populates="source_etl_load_run",
        passive_deletes=True,
    )
    promotion_runs: Mapped[list[CatalogPromotionRun]] = relationship(
        back_populates="etl_load_run",
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


class CatalogProduct(Base):
    """An operational catalog product promoted from an ETL staging batch."""

    __tablename__ = "catalog_products"
    __table_args__ = (
        CheckConstraint(
            "stock >= 0",
            name="ck_catalog_products_stock_non_negative",
        ),
        CheckConstraint(
            "price >= 0",
            name="ck_catalog_products_price_non_negative",
        ),
        CheckConstraint(
            "sale_price IS NULL OR sale_price >= 0",
            name="ck_catalog_products_sale_price_non_negative",
        ),
        CheckConstraint(
            "length(trim(supplier_key)) > 0",
            name="ck_catalog_products_supplier_key_not_blank",
        ),
        CheckConstraint(
            "length(trim(external_product_id)) > 0",
            name="ck_catalog_products_external_product_id_not_blank",
        ),
        Index(
            "ux_catalog_products_supplier_external_product",
            "supplier_key",
            "external_product_id",
            unique=True,
        ),
        Index(
            "ix_catalog_products_source_etl_load_run_id",
            "source_etl_load_run_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    supplier_key: Mapped[str] = mapped_column(String(100), nullable=False)
    external_product_id: Mapped[str] = mapped_column(String(100), nullable=False)
    product_group_id: Mapped[str] = mapped_column(String(100), nullable=False)
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
    source_etl_load_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("etl_load_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    source_etl_load_run: Mapped[ETLLoadRun] = relationship(
        back_populates="promoted_products"
    )
    changes: Mapped[list[CatalogProductChange]] = relationship(
        back_populates="catalog_product",
        primaryjoin="CatalogProduct.id == foreign(CatalogProductChange.catalog_product_id)",
        passive_deletes=True,
    )


class CatalogPromotionRun(Base):
    """An attempted promotion of one ETL staging batch."""

    __tablename__ = "catalog_promotion_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('applying', 'succeeded', 'failed', 'blocked')",
            name="ck_catalog_promotion_runs_status",
        ),
        CheckConstraint(
            "preview_hash IS NULL OR length(preview_hash) = 64",
            name="ck_catalog_promotion_runs_preview_hash_length",
        ),
        CheckConstraint(
            "inserted_count >= 0",
            name="ck_catalog_promotion_runs_inserted_count_non_negative",
        ),
        CheckConstraint(
            "updated_count >= 0",
            name="ck_catalog_promotion_runs_updated_count_non_negative",
        ),
        CheckConstraint(
            "unchanged_count >= 0",
            name="ck_catalog_promotion_runs_unchanged_count_non_negative",
        ),
        CheckConstraint(
            "blocked_count >= 0",
            name="ck_catalog_promotion_runs_blocked_count_non_negative",
        ),
        CheckConstraint(
            "error_count >= 0",
            name="ck_catalog_promotion_runs_error_count_non_negative",
        ),
        CheckConstraint(
            "warning_count >= 0",
            name="ck_catalog_promotion_runs_warning_count_non_negative",
        ),
        CheckConstraint(
            """
            (status = 'applying' AND completed_at IS NULL)
            OR
            (status IN ('succeeded', 'failed', 'blocked') AND completed_at IS NOT NULL)
            """,
            name="ck_catalog_promotion_runs_completed_at_matches_status",
        ),
        Index(
            "ix_catalog_promotion_runs_etl_load_run_id",
            "etl_load_run_id",
        ),
        Index(
            "ux_catalog_promotion_runs_succeeded_etl_load_run",
            "etl_load_run_id",
            unique=True,
            postgresql_where=text("status = 'succeeded'"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    etl_load_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("etl_load_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    preview_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_schema_version: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    inspection_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    inserted_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    updated_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    unchanged_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    blocked_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    warning_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    # Actor audit: 이 promotion을 실행(시도)한 로그인 사용자입니다. migration 이전 row는 NULL입니다.
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)

    etl_load_run: Mapped[ETLLoadRun] = relationship(back_populates="promotion_runs")
    changes: Mapped[list[CatalogProductChange]] = relationship(
        back_populates="promotion_run",
        passive_deletes=True,
    )
    rollback_runs: Mapped[list[CatalogPromotionRollback]] = relationship(
        back_populates="target_promotion_run",
        passive_deletes=True,
    )


class CatalogProductChange(Base):
    """An append-only audit entry for one promoted catalog product change."""

    __tablename__ = "catalog_product_changes"
    __table_args__ = (
        CheckConstraint(
            "action IN ('insert', 'update')",
            name="ck_catalog_product_changes_action",
        ),
        CheckConstraint(
            "jsonb_typeof(changed_fields) = 'object'",
            name="ck_catalog_product_changes_changed_fields_object",
        ),
        CheckConstraint(
            "changed_fields <> '{}'::jsonb",
            name="ck_catalog_product_changes_changed_fields_non_empty",
        ),
        CheckConstraint(
            "before_data IS NULL OR jsonb_typeof(before_data) = 'object'",
            name="ck_catalog_product_changes_before_data_object",
        ),
        CheckConstraint(
            "jsonb_typeof(after_data) = 'object'",
            name="ck_catalog_product_changes_after_data_object",
        ),
        CheckConstraint(
            """
            (action = 'insert' AND before_data IS NULL)
            OR
            (action = 'update' AND before_data IS NOT NULL)
            """,
            name="ck_catalog_product_changes_before_data_matches_action",
        ),
        Index(
            "ix_catalog_product_changes_promotion_run_id",
            "promotion_run_id",
        ),
        Index(
            "ix_catalog_product_changes_promotion_run_created_at_id",
            "promotion_run_id",
            text("created_at DESC"),
            text("id DESC"),
        ),
        Index(
            "ix_catalog_product_changes_catalog_product_id",
            "catalog_product_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    promotion_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("catalog_promotion_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    catalog_product_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_fields: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    before_data: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
    )
    after_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    promotion_run: Mapped[CatalogPromotionRun] = relationship(
        back_populates="changes"
    )
    catalog_product: Mapped[CatalogProduct] = relationship(
        back_populates="changes",
        primaryjoin="CatalogProduct.id == foreign(CatalogProductChange.catalog_product_id)",
    )


class CatalogPromotionRollback(Base):
    """One atomic rollback attempt for a succeeded promotion run."""

    __tablename__ = "catalog_promotion_rollbacks"
    __table_args__ = (
        CheckConstraint("status IN ('applying', 'succeeded', 'failed', 'blocked')", name="ck_catalog_promotion_rollbacks_status"),
        CheckConstraint("preview_hash IS NULL OR length(preview_hash) = 64", name="ck_catalog_promotion_rollbacks_preview_hash_length"),
        CheckConstraint("restored_count >= 0", name="ck_catalog_promotion_rollbacks_restored_count_non_negative"),
        CheckConstraint("deleted_count >= 0", name="ck_catalog_promotion_rollbacks_deleted_count_non_negative"),
        CheckConstraint("conflict_count >= 0", name="ck_catalog_promotion_rollbacks_conflict_count_non_negative"),
        CheckConstraint("(status = 'applying' AND completed_at IS NULL) OR (status IN ('succeeded', 'failed', 'blocked') AND completed_at IS NOT NULL)", name="ck_catalog_promotion_rollbacks_completed_at_matches_status"),
        Index("ux_catalog_promotion_rollbacks_target_promotion_run", "target_promotion_run_id", unique=True, postgresql_where=text("status = 'succeeded'")),
        Index("ix_catalog_promotion_rollbacks_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    target_promotion_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog_promotion_runs.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    preview_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_schema_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    restored_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    deleted_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failure_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    safe_failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    # Actor audit: 이 rollback을 실행(시도)한 로그인 사용자입니다. migration 이전 row는 NULL입니다.
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)

    target_promotion_run: Mapped[CatalogPromotionRun] = relationship(back_populates="rollback_runs")
    changes: Mapped[list[CatalogPromotionRollbackChange]] = relationship(back_populates="rollback_run", passive_deletes=True)


class CatalogPromotionRollbackChange(Base):
    """Audit entry for one product changed by a rollback."""

    __tablename__ = "catalog_promotion_rollback_changes"
    __table_args__ = (
        CheckConstraint("action IN ('delete', 'restore')", name="ck_catalog_promotion_rollback_changes_action"),
        CheckConstraint("jsonb_typeof(changed_fields) = 'object'", name="ck_catalog_promotion_rollback_changes_changed_fields_object"),
        CheckConstraint("changed_fields <> '{}'::jsonb", name="ck_catalog_promotion_rollback_changes_changed_fields_non_empty"),
        CheckConstraint("jsonb_typeof(before_data) = 'object'", name="ck_catalog_promotion_rollback_changes_before_data_object"),
        CheckConstraint("after_data IS NULL OR jsonb_typeof(after_data) = 'object'", name="ck_catalog_promotion_rollback_changes_after_data_object"),
        CheckConstraint("(action = 'delete' AND after_data IS NULL) OR (action = 'restore' AND after_data IS NOT NULL)", name="ck_catalog_promotion_rollback_changes_after_data_matches_action"),
        Index("ix_catalog_promotion_rollback_changes_rollback_run_id", "rollback_run_id"),
        Index("ix_catalog_promotion_rollback_changes_catalog_product_id", "catalog_product_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rollback_run_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog_promotion_rollbacks.id", ondelete="RESTRICT"), nullable=False)
    original_audit_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("catalog_product_changes.id", ondelete="RESTRICT"), nullable=False)
    catalog_product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_fields: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    before_data: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    after_data: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    rollback_run: Mapped[CatalogPromotionRollback] = relationship(back_populates="changes")


class ETLProfileActivation(Base):
    """Runtime activation state for one allowlisted ETL profile.

    이 표는 프로필 **정의**를 담지 않습니다. source_columns/required_source_columns/
    defaults의 source of truth는 계속 config/etl의 버전별 archive와 코드 registry이며,
    Policy A(Published Version Immutable)에 따라 그 내용은 여기서 바뀌지 않습니다.
    여기 있는 것은 "이미 보존된 어떤 버전을 신규 실행에 쓸 것인가" 하나뿐입니다.

    row가 없는 것과 row가 있고 active_version이 NULL인 것은 **다른 상태**입니다.

    | 상태 | 뜻 |
    | --- | --- |
    | row 없음 | runtime override 없음. 배포 registry의 active_version을 그대로 쓴다 |
    | row 있음 + active_version = '2' | runtime override로 v2 활성 |
    | row 있음 + active_version = NULL | runtime override로 비활성(Policy G의 Deactivate) |

    두 상태를 하나로 합치면 "운영자가 명시적으로 내린 프로필"과 "아직 아무도 손대지
    않은 프로필"을 구분할 수 없게 되고, 배포 기본값이 바뀔 때 운영자의 결정이 조용히
    덮이거나 조용히 되살아납니다.

    profile_id에 FK를 걸지 않습니다. 프로필은 아직 DB entity가 아니라 코드 registry의
    key이므로, 존재하지 않는 대상을 가리키는 FK를 만들 수 없습니다. 대신 쓰기 경로가
    registry allowlist와 versions를 검증합니다.
    """

    __tablename__ = "etl_profile_activations"
    __table_args__ = (
        CheckConstraint(
            "length(trim(profile_id)) > 0",
            name="ck_etl_profile_activations_profile_id_not_blank",
        ),
        # 비활성을 뜻하는 값은 NULL 하나뿐입니다. ''나 '  '을 허용하면 Phase 5A가
        # registry에서 막아 둔 "placeholder 문자열은 비활성 표시가 아니다" 규칙이
        # DB 쪽으로 뚫립니다.
        CheckConstraint(
            "active_version IS NULL OR length(trim(active_version)) > 0",
            name="ck_etl_profile_activations_active_version_not_blank",
        ),
        # 한 프로필의 runtime 상태는 정확히 하나입니다. 중복 row가 생기면 어느 것이
        # 진짜인지 코드가 임의로 골라야 하므로 DB에서 막습니다.
        Index(
            "ux_etl_profile_activations_profile_id",
            "profile_id",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # NULL = 비활성. 값이 있으면 registry versions의 정확한 key여야 하며, 쓰기 경로가
    # 그것을 검증합니다. DB는 임의 문자열을 알지 못하므로 형식만 제약합니다.
    active_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Actor audit: 이 상태를 마지막으로 바꾼 로그인 사용자입니다. 요청 body가 아니라
    # 인증된 current_user에서만 채웁니다.
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ETLProfileActivationEvent(Base):
    """One successful operator activation command, kept forever.

    위의 ETLProfileActivation과 **역할이 다릅니다.** 그 표는 프로필당 current-state row
    하나이고, 이 표는 그 상태를 바꾼 명령의 append-only 기록입니다. 둘을 하나로 합치면
    "지금 무엇이 적용되는가"와 "지금까지 무엇을 했는가" 중 하나를 잃습니다.

    특히 reset(DELETE)은 current-state row 자체를 지우므로 actor_username과 updated_at도
    함께 사라집니다. 그 순간의 운영 기록이 남는 곳은 이 표뿐입니다.

    **기록 단위는 "상태가 실제로 달라진 순간"이 아니라 "서버가 성공으로 처리한 operator
    명령"입니다.** 같은 버전을 다시 PUT하거나 override가 없는 프로필에 DELETE를 다시
    보내도 상태는 그대로지만 운영자가 실제로 내린 명령이므로 event가 하나 생깁니다.
    state idempotency와 audit event idempotency는 다른 개념입니다. 실패한 요청(없는
    프로필/버전, 401/403)은 아무 event도 만들지 않습니다.

    append-only는 **애플리케이션 계약**입니다. UPDATE/DELETE/purge API를 두지 않고,
    쓰기 경로는 INSERT 하나뿐입니다. DB superuser가 직접 SQL을 실행하는 것까지 막는
    WORM 저장소는 이 Phase의 범위가 아닙니다.

    profile_id에 FK를 걸지 않는 이유는 ETLProfileActivation과 같습니다. 프로필은 아직
    DB entity가 아니라 코드 registry의 key입니다.
    """

    __tablename__ = "etl_profile_activation_events"
    __table_args__ = (
        CheckConstraint(
            "length(trim(profile_id)) > 0",
            name="ck_etl_profile_activation_events_profile_id_not_blank",
        ),
        CheckConstraint(
            "action IN ('activate', 'deactivate', 'reset')",
            name="ck_etl_profile_activation_events_action",
        ),
        # 버전 문자열의 형식만 봅니다. registry의 어떤 key인지는 DB가 알 수 없고,
        # ''나 '  '이 "비활성"으로 읽히지 않게 하는 것이 목적입니다.
        CheckConstraint(
            "deployment_active_version IS NULL"
            " OR length(trim(deployment_active_version)) > 0",
            name="ck_etl_profile_activation_events_deployment_version_not_blank",
        ),
        CheckConstraint(
            "runtime_active_version IS NULL"
            " OR length(trim(runtime_active_version)) > 0",
            name="ck_etl_profile_activation_events_runtime_version_not_blank",
        ),
        CheckConstraint(
            "effective_active_version IS NULL"
            " OR length(trim(effective_active_version)) > 0",
            name="ck_etl_profile_activation_events_effective_version_not_blank",
        ),
        # 명령과 그 직후 상태가 서로 모순되는 event를 남기지 않습니다. 모순된 기록은
        # 없는 기록보다 나쁩니다 — 나중에 읽는 사람이 그것을 사실로 믿습니다.
        #
        # reset은 override를 지운 상태이므로 effective가 배포 기본값과 같아야 합니다.
        # 둘 다 NULL일 수 있어 '='이 아니라 IS NOT DISTINCT FROM으로 비교합니다.
        # PostgreSQL에서 NULL = NULL은 참이 아니라 NULL이고, CHECK는 NULL을 통과시켜
        # 제약이 조용히 무력화되기 때문입니다.
        CheckConstraint(
            "("
            "action = 'activate'"
            " AND runtime_override_exists"
            " AND runtime_active_version IS NOT NULL"
            " AND effective_active_version = runtime_active_version"
            ") OR ("
            "action = 'deactivate'"
            " AND runtime_override_exists"
            " AND runtime_active_version IS NULL"
            " AND effective_active_version IS NULL"
            ") OR ("
            "action = 'reset'"
            " AND NOT runtime_override_exists"
            " AND runtime_active_version IS NULL"
            " AND effective_active_version IS NOT DISTINCT FROM deployment_active_version"
            ")",
            name="ck_etl_profile_activation_events_state_matches_action",
        ),
        # 주 조회는 "한 프로필의 최신 event부터"입니다. PostgreSQL은 B-tree를 역방향
        # 으로도 훑을 수 있으므로 내림차순 전용 index를 따로 만들지 않습니다.
        Index(
            "ix_etl_profile_activation_events_profile_created_at_id",
            "profile_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    # 아래 네 값은 모두 "명령이 성공한 직후"의 snapshot입니다. 지금 registry를 다시
    # 읽어 계산하면 배포 기본값이 바뀐 뒤에 과거 기록의 뜻이 조용히 달라집니다.
    deployment_active_version: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    runtime_override_exists: Mapped[bool] = mapped_column(nullable=False)
    runtime_active_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    effective_active_version: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    # Actor audit: 인증된 current_user에서만 채웁니다. 요청 body는 actor를 보낼 수
    # 없습니다. 사용자가 삭제되면 FK만 NULL이 되고 actor_username snapshot은 남습니다.
    actor_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_username: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
