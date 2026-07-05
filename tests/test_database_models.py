# 역할: SQLAlchemy ORM 모델의 컬럼, 제약조건, 관계 설정이 기대와 같은지 테스트합니다.
import importlib
import sys

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Text

from db.models import InspectionResult, InspectionRun


def get_constraint_names(table) -> set[str]:
    # SQLAlchemy Table 객체에서 CheckConstraint 이름만 뽑아 비교하기 쉽게 만듭니다.
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def get_index_names(table) -> set[str]:
    # 모델에 선언된 인덱스 이름을 집합으로 모읍니다.
    return {index.name for index in table.indexes}


def test_database_table_names_are_expected():
    # Alembic 마이그레이션과 ORM 모델이 같은 테이블 이름을 쓰는지 확인합니다.
    assert InspectionRun.__tablename__ == "inspection_runs"
    assert InspectionResult.__tablename__ == "inspection_results"


def test_inspection_runs_columns_and_types():
    columns = InspectionRun.__table__.c

    assert set(columns.keys()) == {
        "id",
        "source_filename",
        "file_sha256",
        "inspection_version",
        "total_products",
        "total_issues",
        "error_count",
        "warning_count",
        "created_at",
    }
    assert isinstance(columns.id.type, BigInteger)
    assert columns.id.primary_key
    assert isinstance(columns.source_filename.type, String)
    assert columns.source_filename.type.length == 255
    assert isinstance(columns.file_sha256.type, String)
    assert columns.file_sha256.type.length == 64
    assert columns.file_sha256.nullable is True
    assert isinstance(columns.inspection_version.type, String)
    assert columns.inspection_version.type.length == 20
    assert columns.inspection_version.nullable is False
    assert columns.inspection_version.server_default is None
    assert isinstance(columns.total_products.type, Integer)
    assert isinstance(columns.total_issues.type, Integer)
    assert isinstance(columns.error_count.type, Integer)
    assert isinstance(columns.warning_count.type, Integer)
    assert isinstance(columns.created_at.type, DateTime)
    assert columns.created_at.type.timezone is True
    assert columns.created_at.server_default is not None


def test_inspection_results_columns_and_types():
    columns = InspectionResult.__table__.c

    assert set(columns.keys()) == {
        "id",
        "inspection_run_id",
        "product_group_id",
        "product_id",
        "status",
        "error_field",
        "reason",
        "recommendation",
        "risk_level",
        "created_at",
    }
    assert isinstance(columns.id.type, BigInteger)
    assert columns.id.primary_key
    assert isinstance(columns.inspection_run_id.type, BigInteger)
    assert isinstance(columns.product_group_id.type, String)
    assert isinstance(columns.product_id.type, String)
    assert isinstance(columns.status.type, String)
    assert columns.status.type.length == 20
    assert isinstance(columns.error_field.type, String)
    assert columns.error_field.type.length == 100
    assert isinstance(columns.reason.type, Text)
    assert isinstance(columns.recommendation.type, Text)
    assert isinstance(columns.risk_level.type, String)
    assert columns.risk_level.type.length == 20
    assert isinstance(columns.created_at.type, DateTime)
    assert columns.created_at.type.timezone is True
    assert columns.created_at.server_default is not None


def test_nullable_settings_allow_missing_product_identifiers():
    columns = InspectionResult.__table__.c

    assert columns.product_group_id.nullable is True
    assert columns.product_id.nullable is True
    assert columns.inspection_run_id.nullable is False
    assert columns.status.nullable is False
    assert columns.error_field.nullable is False
    assert columns.reason.nullable is False
    assert columns.recommendation.nullable is False
    assert columns.risk_level.nullable is False


def test_foreign_key_points_to_inspection_runs_with_cascade_delete():
    # 상세 결과는 반드시 하나의 검수 실행에 속하고, 부모 삭제 시 같이 삭제됩니다.
    foreign_keys = list(InspectionResult.__table__.c.inspection_run_id.foreign_keys)

    assert len(foreign_keys) == 1
    foreign_key = foreign_keys[0]
    assert foreign_key.column.table.name == "inspection_runs"
    assert foreign_key.column.name == "id"
    assert foreign_key.ondelete == "CASCADE"


def test_orm_relationships_use_delete_orphan_cascade():
    run_relationship = InspectionRun.results.property
    result_relationship = InspectionResult.inspection_run.property

    assert run_relationship.back_populates == "inspection_run"
    assert result_relationship.back_populates == "results"
    assert "delete-orphan" in run_relationship.cascade
    assert run_relationship.passive_deletes is True


def test_expected_indexes_are_present():
    assert "ix_inspection_runs_created_at" in get_index_names(
        InspectionRun.__table__
    )
    assert "ux_inspection_runs_file_sha256_inspection_version" in get_index_names(
        InspectionRun.__table__
    )
    assert {
        "ix_inspection_results_inspection_run_id",
        "ix_inspection_results_product_id",
        "ix_inspection_results_status",
    }.issubset(get_index_names(InspectionResult.__table__))


def test_inspection_run_count_columns_have_non_negative_constraints():
    constraint_names = get_constraint_names(InspectionRun.__table__)

    assert {
        "ck_inspection_runs_total_products_non_negative",
        "ck_inspection_runs_total_issues_non_negative",
        "ck_inspection_runs_error_count_non_negative",
        "ck_inspection_runs_warning_count_non_negative",
        "ck_inspection_runs_file_sha256_length",
        "ck_inspection_runs_inspection_version_not_blank",
    }.issubset(constraint_names)


def test_file_identity_unique_index_is_partial_for_non_null_hashes():
    index = next(
        index
        for index in InspectionRun.__table__.indexes
        if index.name == "ux_inspection_runs_file_sha256_inspection_version"
    )

    assert index.unique is True
    assert [column.name for column in index.columns] == [
        "file_sha256",
        "inspection_version",
    ]
    where_clause = index.dialect_options["postgresql"]["where"]
    assert where_clause is not None
    assert "file_sha256 IS NOT NULL" in str(where_clause)


def test_existing_apps_and_database_models_import_without_database_url(monkeypatch):
    # DB URL이 없어도 앱 import 단계에서는 실패하지 않아야 배포/테스트가 편합니다.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("app", None)

    streamlit_app = importlib.import_module("app")
    api_module = importlib.import_module("api.main")
    db_models = importlib.import_module("db.models")

    assert streamlit_app is not None
    assert api_module.app.title == "CatalogGuard Lite API"
    assert db_models.InspectionRun.__tablename__ == "inspection_runs"
