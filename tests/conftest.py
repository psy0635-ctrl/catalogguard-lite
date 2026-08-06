# 역할: Streamlit AppTest 로그인 상태와 FastAPI 인증 dependency override를 위한 공용 테스트 helper입니다.
from streamlit.testing.v1 import AppTest


class FakeAuthenticatedUser:
    """get_current_user() dependency override에 쓰는 최소 가짜 사용자입니다."""

    def __init__(
        self,
        *,
        username: str = "operator_user",
        role: str = "operator",
        is_active: bool = True,
        user_id: int = 1,
    ) -> None:
        self.id = user_id
        self.username = username
        self.role = role
        self.is_active = is_active


def override_current_user(*, role: str = "operator", username: str | None = None) -> None:
    """기존 protected endpoint 테스트가 인증을 신경 쓰지 않도록 get_current_user를 override합니다."""
    from api.dependencies import get_current_user
    from api.main import app

    resolved_username = username or f"{role}_user"
    app.dependency_overrides[get_current_user] = lambda: FakeAuthenticatedUser(
        username=resolved_username, role=role
    )


def clear_current_user_override() -> None:
    from api.dependencies import get_current_user
    from api.main import app

    app.dependency_overrides.pop(get_current_user, None)


def build_authenticated_app_test(
    path: str = "app.py",
    *,
    role: str = "operator",
    username: str = "test_operator",
) -> AppTest:
    """실제 로그인 API를 호출하지 않고, 이미 로그인된 상태로 AppTest를 준비합니다."""
    app = AppTest.from_file(path)
    app.session_state["auth_access_token"] = "test-access-token"
    app.session_state["auth_current_username"] = username
    app.session_state["auth_current_role"] = role
    return app


def run_authenticated_app_test(
    path: str = "app.py",
    *,
    role: str = "operator",
    username: str = "test_operator",
    timeout: int = 10,
) -> AppTest:
    return build_authenticated_app_test(path, role=role, username=username).run(
        timeout=timeout
    )
