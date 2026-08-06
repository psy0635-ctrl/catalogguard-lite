# 역할: Streamlit 로그인/로그아웃 UI와 role 기반 버튼 제한을 AppTest로 검증합니다.
from streamlit.testing.v1 import AppTest

from clients.catalogguard_api import InvalidCredentialsError
from conftest import build_authenticated_app_test
from tests.test_etl_load_history_ui import FakeEtlApiClient
from ui import auth as ui_auth
from ui import etl_load_history


class FakeAuthApiClient:
    def __init__(self, *, login_error=None):
        self.login_error = login_error
        self.login_calls = []
        self.access_token = None

    def login(self, *, username, password):
        self.login_calls.append({"username": username, "password": password})
        if self.login_error is not None:
            raise self.login_error
        return {"access_token": "fake-access-token", "token_type": "bearer", "expires_in": 3600}

    def set_access_token(self, access_token):
        self.access_token = access_token

    def get_current_user(self):
        return {"username": "operator_user", "role": "operator"}

    def list_inspections(self, **params):
        # app.py의 다른 탭도 같은 로그인 후 client를 사용하므로 최소 no-op만 제공합니다.
        return {"items": [], "total": 0, "limit": params.get("limit", 20), "offset": 0}


def _patch_auth_api_client(monkeypatch, api_client):
    monkeypatch.setattr(ui_auth, "create_catalogguard_api_client", lambda: api_client)


def _patch_etl_api_client_for_app(monkeypatch, api_client):
    monkeypatch.setattr(etl_load_history, "get_authenticated_api_client", lambda: api_client)


def test_login_form_shows_unique_username_and_password_widgets():
    app = AppTest.from_file("app.py").run(timeout=10)

    username_widgets = [widget for widget in app.text_input if widget.label == "아이디"]
    password_widgets = [widget for widget in app.text_input if widget.label == "비밀번호"]
    # 실제 type="password" 숨김 입력 여부는 ui/auth.py 소스에서 보장하며, 여기서는
    # 두 위젯의 접근성 label이 서로 겹치지 않고 정확히 하나씩만 존재하는지 확인합니다.
    assert len(username_widgets) == 1
    assert len(password_widgets) == 1


def test_successful_login_stores_token_and_shows_authenticated_sidebar(monkeypatch):
    auth_client = FakeAuthApiClient()
    etl_client = FakeEtlApiClient()
    _patch_auth_api_client(monkeypatch, auth_client)
    _patch_etl_api_client_for_app(monkeypatch, etl_client)

    app = AppTest.from_file("app.py").run(timeout=10)
    app.text_input(key="auth_username_input_0").set_value("operator_user")
    app.text_input(key="auth_password_input_0").set_value("correct-password")
    app.button(key="auth_login_submit").click().run(timeout=10)

    assert len(app.exception) == 0
    assert app.session_state["auth_access_token"] == "fake-access-token"
    assert app.session_state["auth_current_username"] == "operator_user"
    assert app.session_state["auth_current_role"] == "operator"
    assert auth_client.login_calls == [
        {"username": "operator_user", "password": "correct-password"}
    ]
    assert any("operator_user" in markdown.value for markdown in app.markdown)
    assert "CSV 입력 템플릿" in [subheader.value for subheader in app.subheader]


def test_login_failure_shows_generic_invalid_credentials_message(monkeypatch):
    auth_client = FakeAuthApiClient(
        login_error=InvalidCredentialsError("no", code="invalid_credentials")
    )
    _patch_auth_api_client(monkeypatch, auth_client)

    app = AppTest.from_file("app.py").run(timeout=10)
    app.text_input(key="auth_username_input_0").set_value("operator_user")
    app.text_input(key="auth_password_input_0").set_value("wrong-password")
    app.button(key="auth_login_submit").click().run(timeout=10)

    assert len(app.exception) == 0
    assert "auth_access_token" not in app.session_state
    assert any(
        "아이디 또는 비밀번호가 올바르지 않습니다" in error.value for error in app.error
    )
    # 로그인 폼이 여전히 보여야 하며 다음 시도를 위해 새 위젯 key를 사용합니다.
    assert any(widget.label == "아이디" for widget in app.text_input)


def test_logout_clears_session_state_and_shows_login_form_again(monkeypatch):
    etl_client = FakeEtlApiClient()
    _patch_etl_api_client_for_app(monkeypatch, etl_client)

    app = build_authenticated_app_test("app.py").run(timeout=10)
    assert "CSV 입력 템플릿" in [subheader.value for subheader in app.subheader]

    app.button(key="auth_logout_button").click().run(timeout=10)

    assert len(app.exception) == 0
    assert "auth_access_token" not in app.session_state
    assert "좌측 사이드바에서 로그인한 뒤 이용해 주세요." in [
        info.value for info in app.info
    ]


def test_viewer_role_disables_web_etl_run_button(monkeypatch):
    etl_client = FakeEtlApiClient()
    _patch_etl_api_client_for_app(monkeypatch, etl_client)

    app = build_authenticated_app_test("app.py", role="viewer").run(timeout=10)

    run_button = next(
        button for button in app.button if button.key == "etl_web_run_submit"
    )
    assert run_button.disabled is True
    assert any(
        "ETL 실행은 운영자 권한이 필요합니다" in caption.value
        for caption in app.caption
    )


def test_operator_role_does_not_force_disable_web_etl_run_button(monkeypatch):
    etl_client = FakeEtlApiClient()
    _patch_etl_api_client_for_app(monkeypatch, etl_client)

    app = build_authenticated_app_test("app.py", role="operator").run(timeout=10)

    run_button = next(
        button for button in app.button if button.key == "etl_web_run_submit"
    )
    # 업로드 파일이 없으므로 여전히 disabled지만, role 캡션은 표시되지 않아야 합니다.
    assert run_button.disabled is True
    assert not any(
        "ETL 실행은 운영자 권한이 필요합니다" in caption.value
        for caption in app.caption
    )
