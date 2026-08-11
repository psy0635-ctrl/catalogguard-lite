from clients import catalogguard_api
from conftest import run_authenticated_app_test
from tests.test_etl_load_history_ui import FakeEtlApiClient
from ui import etl_load_history


def make_rollback_run(
    rollback_run_id=71,
    *,
    target_promotion_run_id=31,
    status="succeeded",
    actor_username="rollback_operator",
):
    failed = status in {"failed", "blocked"}
    return {
        "rollback_run_id": rollback_run_id,
        "target_promotion_run_id": target_promotion_run_id,
        "status": status,
        "restored_count": 2,
        "deleted_count": 1,
        "conflict_count": 0,
        "failure_code": "preview_stale" if failed else None,
        "safe_failure_message": (
            "상품 상태가 변경되어 Rollback을 실행하지 않았습니다."
            if failed
            else None
        ),
        "started_at": "2026-08-11T05:20:00Z",
        "completed_at": "2026-08-11T05:20:01Z",
        "created_at": "2026-08-11T05:20:00Z",
        "actor_username": actor_username,
    }


def make_rollback_change(
    rollback_change_id=101,
    *,
    rollback_run_id=71,
    original_audit_id=41,
    catalog_product_id=25,
    action="delete",
    external_product_id="P-25",
):
    restore = action == "restore"
    before_name = "Product B+" if restore else "Product A"
    after_name = "Product B" if restore else None
    return {
        "rollback_change_id": rollback_change_id,
        "rollback_run_id": rollback_run_id,
        "original_audit_id": original_audit_id,
        "catalog_product_id": catalog_product_id,
        "action": action,
        "changed_fields": {
            "product_name": {"before": before_name, "after": after_name}
        },
        "before_data": {
            "external_product_id": external_product_id,
            "product_name": before_name,
        },
        "after_data": (
            {
                "external_product_id": external_product_id,
                "product_name": after_name,
            }
            if restore
            else None
        ),
        "created_at": "2026-08-11T05:20:01Z",
    }


class FakeRollbackHistoryApiClient(FakeEtlApiClient):
    def __init__(
        self,
        *,
        rollback_items=None,
        rollback_pages=None,
        rollback_total=None,
        rollback_history_error=None,
        rollback_detail_error=None,
        rollback_change_items=None,
        rollback_change_pages=None,
        rollback_change_total=None,
        rollback_change_error=None,
    ):
        super().__init__()
        self.rollback_items = (
            [make_rollback_run(), make_rollback_run(72, target_promotion_run_id=32)]
            if rollback_items is None
            else rollback_items
        )
        self.rollback_pages = rollback_pages
        self.rollback_total = (
            len(self.rollback_items) if rollback_total is None else rollback_total
        )
        self.rollback_history_error = rollback_history_error
        self.rollback_detail_error = rollback_detail_error
        self.rollback_change_items = (
            [make_rollback_change(), make_rollback_change(102, action="restore")]
            if rollback_change_items is None
            else rollback_change_items
        )
        self.rollback_change_pages = rollback_change_pages
        self.rollback_change_total = (
            len(self.rollback_change_items)
            if rollback_change_total is None
            else rollback_change_total
        )
        self.rollback_change_error = rollback_change_error
        self.rollback_history_calls = []
        self.rollback_detail_calls = []
        self.rollback_change_calls = []
        self.rollback_preview_calls = []
        self.rollback_execution_calls = []

    def list_catalog_promotion_rollbacks(self, **params):
        self.rollback_history_calls.append(params)
        if self.rollback_history_error is not None:
            raise self.rollback_history_error
        items = (
            self.rollback_pages.get(params["offset"], [])
            if self.rollback_pages is not None
            else self.rollback_items
        )
        return {
            "items": items,
            "total": self.rollback_total,
            "limit": params["limit"],
            "offset": params["offset"],
        }

    def get_catalog_promotion_rollback_detail(self, rollback_run_id):
        self.rollback_detail_calls.append(rollback_run_id)
        if self.rollback_detail_error is not None:
            raise self.rollback_detail_error
        matching = next(
            (
                item
                for item in self.rollback_items
                if item["rollback_run_id"] == rollback_run_id
            ),
            make_rollback_run(rollback_run_id),
        )
        return {
            **matching,
            "preview_hash": "b" * 64,
            "preview_schema_version": "1",
        }

    def list_catalog_promotion_rollback_changes(
        self,
        rollback_run_id,
        *,
        limit,
        offset,
    ):
        self.rollback_change_calls.append(
            {
                "rollback_run_id": rollback_run_id,
                "limit": limit,
                "offset": offset,
            }
        )
        if self.rollback_change_error is not None:
            raise self.rollback_change_error
        items = (
            self.rollback_change_pages.get(offset, [])
            if self.rollback_change_pages is not None
            else self.rollback_change_items
        )
        return {
            "items": items,
            "total": self.rollback_change_total,
            "limit": limit,
            "offset": offset,
        }

    def get_catalog_promotion_rollback_preview(self, promotion_run_id):
        self.rollback_preview_calls.append(promotion_run_id)
        return {
            "target_promotion_run_id": promotion_run_id,
            "preview_schema_version": "1",
            "preview_hash": "c" * 64,
            "rollback_eligible": True,
            "blocked_reasons": [],
            "restore_count": 2,
            "delete_count": 1,
            "conflict_count": 0,
            "items": [],
        }

    def create_catalog_promotion_rollback(
        self,
        promotion_run_id,
        *,
        confirmation,
        expected_preview_hash,
    ):
        self.rollback_execution_calls.append(
            {
                "promotion_run_id": promotion_run_id,
                "confirmation": confirmation,
                "expected_preview_hash": expected_preview_hash,
            }
        )
        new_run = make_rollback_run(
            73,
            target_promotion_run_id=promotion_run_id,
            actor_username="test_operator",
        )
        self.rollback_items = [new_run, *self.rollback_items]
        self.rollback_total = len(self.rollback_items)
        return {
            **new_run,
            "created": True,
            "preview_hash": expected_preview_hash,
            "preview_schema_version": "1",
        }


def _patch_api_client(monkeypatch, api_client):
    monkeypatch.setattr(
        etl_load_history,
        "get_authenticated_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )


def _find_selectbox(app, key):
    return next(selectbox for selectbox in app.selectbox if selectbox.key == key)


def _find_button(app, key):
    return next(button for button in app.button if button.key == key)


def test_rollback_history_dataframe_formats_actor_and_keeps_run_identity():
    frame = etl_load_history.build_catalog_promotion_rollback_history_dataframe(
        [
            make_rollback_run(actor_username="rollback_operator"),
            make_rollback_run(72, actor_username=None),
        ]
    )

    assert frame.columns.tolist() == etl_load_history.ROLLBACK_HISTORY_DISPLAY_COLUMNS
    assert frame["Rollback ID"].tolist() == [71, 72]
    assert frame["대상 Promotion"].tolist() == [31, 31]
    assert frame["실행 사용자"].tolist() == ["rollback_operator", "알 수 없음"]


def test_rollback_history_option_label_distinguishes_run_and_target_promotion():
    label = etl_load_history.build_catalog_promotion_rollback_option_label(
        make_rollback_run(72, target_promotion_run_id=32, status="blocked")
    )

    assert label == "72 · Promotion 32 · blocked"


def test_rollback_change_audit_dataframe_expands_delete_fields():
    change = make_rollback_change()
    change["changed_fields"]["price"] = {"before": 1200, "after": None}

    frame = etl_load_history.build_catalog_promotion_rollback_change_dataframe(
        [change]
    )

    assert frame.columns.tolist() == (
        etl_load_history.ROLLBACK_CHANGE_AUDIT_DISPLAY_COLUMNS
    )
    assert frame["Change ID"].tolist() == [101, 101]
    assert frame["원본 Audit ID"].tolist() == [41, 41]
    assert frame["상품 ID"].tolist() == [25, 25]
    assert frame["외부 상품 ID"].tolist() == ["P-25", "P-25"]
    assert frame["변경 유형"].tolist() == ["상품 삭제", "상품 삭제"]
    assert frame["변경 필드"].tolist() == ["price", "product_name"]
    assert frame["변경 전"].tolist() == [1200, "Product A"]
    assert frame["변경 후"].tolist() == ["삭제됨", "삭제됨"]


def test_rollback_change_audit_dataframe_prefers_restore_after_external_id():
    change = make_rollback_change(action="restore", external_product_id="P-before")
    change["after_data"]["external_product_id"] = "P-after"

    frame = etl_load_history.build_catalog_promotion_rollback_change_dataframe(
        [change]
    )

    assert frame["외부 상품 ID"].tolist() == ["P-after"]
    assert frame["변경 유형"].tolist() == ["이전 상태 복원"]
    assert frame["변경 전"].tolist() == ["Product B+"]
    assert frame["변경 후"].tolist() == ["Product B"]


def test_rollback_change_audit_dataframe_handles_missing_external_id():
    change = make_rollback_change(external_product_id="")
    change["before_data"].pop("external_product_id")

    frame = etl_load_history.build_catalog_promotion_rollback_change_dataframe(
        [change]
    )

    assert frame["외부 상품 ID"].tolist() == [""]


def test_rollback_history_selection_change_clears_stale_detail_state():
    state = {}
    etl_load_history.initialize_etl_load_state(state)
    state["catalog_promotion_rollback_history_detail_requested"] = True
    state["catalog_promotion_rollback_history_detail_response"] = {
        "rollback_run_id": 71
    }
    state["catalog_promotion_rollback_history_detail_error"] = RuntimeError(
        "old detail"
    )
    state["catalog_promotion_rollback_change_offset"] = 10
    state["catalog_promotion_rollback_change_response"] = {"items": []}
    state["catalog_promotion_rollback_change_error"] = RuntimeError("old audit")

    etl_load_history._on_catalog_promotion_rollback_history_run_change(state)

    assert state["catalog_promotion_rollback_history_detail_requested"] is False
    assert state["catalog_promotion_rollback_history_detail_response"] is None
    assert state["catalog_promotion_rollback_history_detail_error"] is None
    assert state["catalog_promotion_rollback_change_offset"] == 0
    assert state["catalog_promotion_rollback_change_response"] is None
    assert state["catalog_promotion_rollback_change_error"] is None


def test_rollback_success_invalidates_history_cache_without_unrelated_state():
    state = {"unrelated": "keep"}
    etl_load_history.initialize_etl_load_state(state)
    state["catalog_promotion_rollback_history_response"] = {"items": []}
    state["catalog_promotion_rollback_history_error"] = RuntimeError("old list")

    etl_load_history.invalidate_catalog_promotion_rollback_history(state)

    assert state["catalog_promotion_rollback_history_response"] is None
    assert state["catalog_promotion_rollback_history_error"] is None
    assert state["unrelated"] == "keep"


def test_rollback_history_apptest_shows_list_actor_and_reuses_cache(monkeypatch):
    api_client = FakeRollbackHistoryApiClient()
    _patch_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert len(app.exception) == 0
    assert any(
        subheader.value == "Rollback 실행 이력" for subheader in app.subheader
    )
    frame = next(
        dataframe.value
        for dataframe in app.dataframe
        if set(dataframe.value.columns)
        == set(etl_load_history.ROLLBACK_HISTORY_DISPLAY_COLUMNS)
    )
    assert frame["Rollback ID"].tolist() == [71, 72]
    assert frame["실행 사용자"].tolist() == [
        "rollback_operator",
        "rollback_operator",
    ]
    assert api_client.rollback_history_calls == [{"limit": 10, "offset": 0}]

    app.run(timeout=10)

    assert api_client.rollback_history_calls == [{"limit": 10, "offset": 0}]


def test_rollback_history_apptest_shows_empty_state(monkeypatch):
    api_client = FakeRollbackHistoryApiClient(rollback_items=[])
    _patch_api_client(monkeypatch, api_client)

    app = run_authenticated_app_test(timeout=10)

    assert "아직 Rollback 실행 이력이 없습니다." in [
        info.value for info in app.info
    ]


def test_rollback_history_apptest_selects_detail_with_metrics_actor_and_preview(
    monkeypatch,
):
    api_client = FakeRollbackHistoryApiClient()
    _patch_api_client(monkeypatch, api_client)
    app = run_authenticated_app_test(timeout=10)

    _find_selectbox(
        app, "catalog_promotion_rollback_history_run_id"
    ).select(71).run(timeout=10)
    _find_button(
        app, "catalog_promotion_rollback_history_show_detail"
    ).click().run(timeout=10)

    assert api_client.rollback_detail_calls == [71]
    assert any(metric.label == "복구 상품" and metric.value == "2" for metric in app.metric)
    assert any(metric.label == "삭제 상품" and metric.value == "1" for metric in app.metric)
    assert any(metric.label == "충돌" and metric.value == "0" for metric in app.metric)
    markdown_values = [markdown.value for markdown in app.markdown]
    assert "Rollback ID: 71" in markdown_values
    assert "대상 Promotion ID: 31" in markdown_values
    assert "실행 사용자: rollback_operator" in markdown_values
    assert any(expander.label == "Rollback Preview 정보" for expander in app.expander)


def test_rollback_history_apptest_shows_change_audit_in_detail(monkeypatch):
    api_client = FakeRollbackHistoryApiClient()
    _patch_api_client(monkeypatch, api_client)
    app = run_authenticated_app_test(timeout=10)

    _find_selectbox(
        app, "catalog_promotion_rollback_history_run_id"
    ).select(71).run(timeout=10)
    _find_button(
        app, "catalog_promotion_rollback_history_show_detail"
    ).click().run(timeout=10)

    assert "#### 상품 Rollback 변경 Audit" in [
        markdown.value for markdown in app.markdown
    ]
    frame = next(
        dataframe.value
        for dataframe in app.dataframe
        if list(dataframe.value.columns)
        == etl_load_history.ROLLBACK_CHANGE_AUDIT_DISPLAY_COLUMNS
    )
    assert frame["변경 유형"].tolist() == ["상품 삭제", "이전 상태 복원"]
    assert api_client.rollback_change_calls == [
        {"rollback_run_id": 71, "limit": 10, "offset": 0}
    ]


def test_rollback_history_apptest_shows_empty_change_audit(monkeypatch):
    api_client = FakeRollbackHistoryApiClient(rollback_change_items=[])
    _patch_api_client(monkeypatch, api_client)
    app = run_authenticated_app_test(timeout=10)

    _find_selectbox(
        app, "catalog_promotion_rollback_history_run_id"
    ).select(71).run(timeout=10)
    _find_button(
        app, "catalog_promotion_rollback_history_show_detail"
    ).click().run(timeout=10)

    assert "이 Rollback 실행에는 상품 변경 Audit이 없습니다." in [
        info.value for info in app.info
    ]


def test_rollback_history_apptest_shows_safe_change_audit_error(monkeypatch):
    api_client = FakeRollbackHistoryApiClient(
        rollback_change_error=catalogguard_api.CatalogGuardApiResponseError(
            "postgresql://private",
            request_id="a29ae9a1c62f4152bb96f6513c323d96",
        )
    )
    _patch_api_client(monkeypatch, api_client)
    app = run_authenticated_app_test(timeout=10)

    _find_selectbox(
        app, "catalog_promotion_rollback_history_run_id"
    ).select(71).run(timeout=10)
    _find_button(
        app, "catalog_promotion_rollback_history_show_detail"
    ).click().run(timeout=10)

    error_messages = [error.value for error in app.error]
    assert any(
        "Rollback 상품 변경 Audit을 불러오지 못했습니다." in value
        for value in error_messages
    )
    assert any(
        "a29ae9a1c62f4152bb96f6513c323d96" in value
        for value in error_messages
    )
    assert all("postgresql" not in value.lower() for value in error_messages)


def test_rollback_history_apptest_paginates_change_audit_without_refetching_detail(
    monkeypatch,
):
    first_page = [make_rollback_change(index) for index in range(101, 111)]
    second_page = [make_rollback_change(index) for index in range(111, 121)]
    api_client = FakeRollbackHistoryApiClient(
        rollback_change_items=[*first_page, *second_page],
        rollback_change_pages={0: first_page, 10: second_page},
        rollback_change_total=21,
    )
    _patch_api_client(monkeypatch, api_client)
    app = run_authenticated_app_test(timeout=10)

    _find_selectbox(
        app, "catalog_promotion_rollback_history_run_id"
    ).select(71).run(timeout=10)
    _find_button(
        app, "catalog_promotion_rollback_history_show_detail"
    ).click().run(timeout=10)
    _find_button(
        app, "catalog_promotion_rollback_change_next"
    ).click().run(timeout=10)

    assert api_client.rollback_change_calls == [
        {"rollback_run_id": 71, "limit": 10, "offset": 0},
        {"rollback_run_id": 71, "limit": 10, "offset": 10},
    ]
    assert api_client.rollback_detail_calls == [71]
    assert app.session_state["catalog_promotion_rollback_change_offset"] == 10


def test_rollback_history_apptest_selection_change_removes_stale_detail(monkeypatch):
    api_client = FakeRollbackHistoryApiClient()
    _patch_api_client(monkeypatch, api_client)
    app = run_authenticated_app_test(timeout=10)
    _find_selectbox(
        app, "catalog_promotion_rollback_history_run_id"
    ).select(71).run(timeout=10)
    _find_button(
        app, "catalog_promotion_rollback_history_show_detail"
    ).click().run(timeout=10)

    _find_selectbox(
        app, "catalog_promotion_rollback_history_run_id"
    ).select(72).run(timeout=10)

    assert app.session_state[
        "catalog_promotion_rollback_history_detail_requested"
    ] is False
    assert app.session_state[
        "catalog_promotion_rollback_history_detail_response"
    ] is None
    assert api_client.rollback_detail_calls == [71]


def test_rollback_history_apptest_shows_safe_failure_and_list_error(monkeypatch):
    failed_run = make_rollback_run(status="blocked")
    detail_client = FakeRollbackHistoryApiClient(rollback_items=[failed_run])
    _patch_api_client(monkeypatch, detail_client)
    detail_app = run_authenticated_app_test(timeout=10)
    _find_selectbox(
        detail_app, "catalog_promotion_rollback_history_run_id"
    ).select(71).run(timeout=10)
    _find_button(
        detail_app, "catalog_promotion_rollback_history_show_detail"
    ).click().run(timeout=10)

    detail_messages = [warning.value for warning in detail_app.warning]
    assert any("실패 코드: preview_stale" in value for value in detail_messages)
    assert any("상품 상태가 변경되어" in value for value in detail_messages)

    error_client = FakeRollbackHistoryApiClient(
        rollback_history_error=catalogguard_api.CatalogGuardApiResponseError(
            "postgresql://private",
            request_id="a29ae9a1c62f4152bb96f6513c323d96",
        )
    )
    _patch_api_client(monkeypatch, error_client)
    error_app = run_authenticated_app_test(timeout=10)

    error_messages = [error.value for error in error_app.error]
    assert any("Rollback 실행 이력을 불러오지 못했습니다." in value for value in error_messages)
    assert any("a29ae9a1c62f4152bb96f6513c323d96" in value for value in error_messages)
    assert all("postgresql" not in value.lower() for value in error_messages)


def test_rollback_history_apptest_filters_and_paginates(monkeypatch):
    first_page = [make_rollback_run(index) for index in range(71, 81)]
    second_page = [make_rollback_run(81)]
    api_client = FakeRollbackHistoryApiClient(
        rollback_items=[*first_page, *second_page],
        rollback_pages={0: first_page, 10: second_page},
        rollback_total=11,
    )
    _patch_api_client(monkeypatch, api_client)
    app = run_authenticated_app_test(timeout=10)

    _find_selectbox(
        app, "catalog_promotion_rollback_history_status"
    ).select("succeeded").run(timeout=10)
    assert api_client.rollback_history_calls[-1] == {
        "limit": 10,
        "offset": 0,
        "status": "succeeded",
    }

    _find_button(
        app, "catalog_promotion_rollback_history_next"
    ).click().run(timeout=10)

    assert api_client.rollback_history_calls[-1] == {
        "limit": 10,
        "offset": 10,
        "status": "succeeded",
    }
    assert app.session_state["catalog_promotion_rollback_history_offset"] == 10


def test_rollback_execution_apptest_refreshes_history_with_new_run(monkeypatch):
    api_client = FakeRollbackHistoryApiClient()
    _patch_api_client(monkeypatch, api_client)
    app = run_authenticated_app_test(timeout=10)
    assert api_client.rollback_history_calls == [{"limit": 10, "offset": 0}]

    _find_selectbox(app, "catalog_promotion_history_run_id").select(31).run(
        timeout=10
    )
    _find_button(app, "catalog_promotion_history_show_detail").click().run(
        timeout=10
    )
    _find_button(app, "catalog_promotion_rollback_preview").click().run(timeout=10)
    next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.key == "catalog_promotion_rollback_confirmation"
    ).check().run(timeout=10)
    _find_button(app, "catalog_promotion_rollback_execute").click().run(timeout=10)

    assert api_client.rollback_execution_calls == [
        {
            "promotion_run_id": 31,
            "confirmation": True,
            "expected_preview_hash": "c" * 64,
        }
    ]
    assert api_client.rollback_history_calls == [
        {"limit": 10, "offset": 0},
        {"limit": 10, "offset": 0},
    ]
    refreshed_frame = next(
        dataframe.value
        for dataframe in app.dataframe
        if set(dataframe.value.columns)
        == set(etl_load_history.ROLLBACK_HISTORY_DISPLAY_COLUMNS)
    )
    assert refreshed_frame["Rollback ID"].tolist() == [73, 71, 72]
