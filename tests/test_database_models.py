import importlib
import sys

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Text

from db.models import InspectionResult, InspectionRun


def get_constraint_names(table) -> set[str]:
    return {
        constraint.name
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }


def get_index_names(table) -> set[str]:
    return {index.name for index in table.indexes}


def test_database_table_names_are_expected():
    assert InspectionRun.__tablename__ == "inspection_runs"
    assert InspectionResult.__tablename__ == "inspection_results"


def test_inspection_runs_columns_and_types():
    columns = InspectionRun.__table__.c

    assert set(columns.keys()) == {
        "id",
        "source_filename",
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
    }.issubset(constraint_names)


def test_existing_apps_and_database_models_import_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("app", None)

    streamlit_app = importlib.import_module("app")
    api_module = importlib.import_module("api.main")
    db_models = importlib.import_module("db.models")

    assert streamlit_app is not None
    assert api_module.app.title == "CatalogGuard Lite API"
    assert db_models.InspectionRun.__tablename__ == "inspection_runs"
