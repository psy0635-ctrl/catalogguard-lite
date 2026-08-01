from streamlit.testing.v1 import AppTest

from clients import catalogguard_api
from tests.test_etl_load_history_ui import (
    FakeEtlApiClient,
    make_promotion_audit,
)
from ui import etl_load_history


def _patch_api_client(monkeypatch, api_client):
    monkeypatch.setattr(
        etl_load_history,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )


def test_catalog_promotion_success_invalidates_only_history_cache():
    state = {}
    etl_load_history.initialize_etl_load_state(state)
    state["catalog_promotion_history_response"] = {
        "items": [],
        "total": 0,
        "limit": 10,
        "offset": 0,
    }
    state["catalog_promotion_history_error"] = RuntimeError("old error")
    state["catalog_promotion_history_status"] = "전체"

    etl_load_history.store_catalog_promotion_success(
        state,
        {"promotion_run_id": 31, "status": "succeeded"},
    )

    assert state["catalog_promotion_history_response"] is None
    assert state["catalog_promotion_history_error"] is None
    assert state["catalog_promotion_history_status"] == "전체"
    assert state["catalog_promotion_result"]["promotion_run_id"] == 31


def test_catalog_promotion_history_apptest_shows_cached_list(monkeypatch):
    api_client = FakeEtlApiClient()
    _patch_api_client(monkeypatch, api_client)

    app = AppTest.from_file("app.py").run(timeout=10)

    assert len(app.exception) == 0
    assert any(
        subheader.value == "Promotion 실행 이력" for subheader in app.subheader
    )
    assert any(
        set(dataframe.value.columns)
        == set(etl_load_history.PROMOTION_HISTORY_DISPLAY_COLUMNS)
        for dataframe in app.dataframe
    )
    assert api_client.promotion_history_calls == [{"limit": 10, "offset": 0}]
    assert api_client.promotion_history_detail_calls == []
    assert api_client.promotion_audit_calls == []

    app.run(timeout=10)

    assert api_client.promotion_history_calls == [{"limit": 10, "offset": 0}]


def test_catalog_promotion_history_apptest_selects_detail_and_flattens_audit(
    monkeypatch,
):
    api_client = FakeEtlApiClient()
    _patch_api_client(monkeypatch, api_client)
    app = AppTest.from_file("app.py").run(timeout=10)

    next(
        selectbox
        for selectbox in app.selectbox
        if selectbox.key == "catalog_promotion_history_run_id"
    ).select(31).run(timeout=10)
    next(
        button
        for button in app.button
        if button.key == "catalog_promotion_history_show_detail"
    ).click().run(timeout=10)

    assert api_client.promotion_history_detail_calls == [31]
    assert api_client.promotion_audit_calls == [
        {"promotion_run_id": 31, "limit": 10, "offset": 0}
    ]
    assert any(metric.label == "신규 상품" and metric.value == "1" for metric in app.metric)
    audit_frame = next(
        dataframe.value
        for dataframe in app.dataframe
        if set(dataframe.value.columns)
        == set(etl_load_history.PROMOTION_AUDIT_DISPLAY_COLUMNS)
    )
    assert audit_frame["외부 상품 ID"].tolist() == ["SKU-UPDATE", "SKU-UPDATE"]
    assert audit_frame["변경 필드"].tolist() == ["price", "stock"]
    assert audit_frame["변경 전"].tolist() == [19900, 10]
    assert audit_frame["변경 후"].tolist() == [20900, 8]

    app.run(timeout=10)
    assert api_client.promotion_history_detail_calls == [31]
    assert len(api_client.promotion_audit_calls) == 1


def test_catalog_promotion_history_apptest_paginates_audits(monkeypatch):
    api_client = FakeEtlApiClient(
        promotion_audit_pages={
            0: [make_promotion_audit(audit_id=index) for index in range(1, 11)],
            10: [make_promotion_audit(audit_id=11)],
        }
    )
    _patch_api_client(monkeypatch, api_client)
    app = AppTest.from_file("app.py").run(timeout=10)
    next(
        selectbox
        for selectbox in app.selectbox
        if selectbox.key == "catalog_promotion_history_run_id"
    ).select(31).run(timeout=10)
    next(
        button
        for button in app.button
        if button.key == "catalog_promotion_history_show_detail"
    ).click().run(timeout=10)

    next(
        button
        for button in app.button
        if button.key == "catalog_promotion_audit_next"
    ).click().run(timeout=10)

    assert api_client.promotion_audit_calls[-1] == {
        "promotion_run_id": 31,
        "limit": 10,
        "offset": 10,
    }
    assert app.session_state["catalog_promotion_audit_offset"] == 10


def test_catalog_promotion_history_apptest_handles_empty_and_safe_api_error(
    monkeypatch,
):
    empty_client = FakeEtlApiClient(promotion_history_items=[])
    _patch_api_client(monkeypatch, empty_client)
    empty_app = AppTest.from_file("app.py").run(timeout=10)

    assert "Promotion 실행 이력이 없습니다." in [
        info.value for info in empty_app.info
    ]

    error_client = FakeEtlApiClient(
        promotion_history_error=catalogguard_api.CatalogGuardApiResponseError(
            "postgresql://private",
            request_id="a29ae9a1c62f4152bb96f6513c323d96",
        )
    )
    _patch_api_client(monkeypatch, error_client)
    error_app = AppTest.from_file("app.py").run(timeout=10)

    messages = [error.value for error in error_app.error]
    assert any("Promotion 실행 이력을 불러오지 못했습니다." in value for value in messages)
    assert any("a29ae9a1c62f4152bb96f6513c323d96" in value for value in messages)
    assert all("postgresql" not in value.lower() for value in messages)
