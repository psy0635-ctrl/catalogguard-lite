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
)
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
        Index("ix_inspection_runs_created_at", "created_at"),
    )

    # PostgreSQL에서 자동 증가하는 기본키입니다.
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
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
