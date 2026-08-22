# 역할: Streamlit AppTest 로그인 상태와 FastAPI 인증 dependency override를 위한 공용 테스트 helper입니다.
from streamlit.testing.v1 import AppTest


class _NoRowsScalarResult:
    """Answers "no rows" for the few shapes route code uses."""

    def one_or_none(self):
        return None

    def all(self):
        return []

    def first(self):
        return None


class FakeSessionWithoutRuntimeOverrides:
    """A stand-in Session for route tests that never reach a real database.

    ETL 프로필 route는 runtime activation override가 있는지 SELECT 한 번으로 확인합니다.
    DB 없이 도는 테스트에도 그 질의에 "override 없음"으로 답해 줄 최소 객체가 필요합니다.

    조회 뒤에는 실행 경로가 읽기 트랜잭션을 정리하므로(end_activation_read_transaction)
    보류 중인 쓰기가 없다는 사실과 rollback()도 함께 흉내 냅니다.

    그 밖의 API는 일부러 구현하지 않습니다. 아무 호출에나 빈 결과를 돌려주면 실제로
    DB를 써야 하는 코드가 테스트에서 조용히 통과하게 됩니다.
    """

    # 이 stub은 읽기만 흉내 내므로 보류 중인 쓰기가 있을 수 없습니다.
    new: tuple = ()
    dirty: tuple = ()
    deleted: tuple = ()

    def scalars(self, statement):
        return _NoRowsScalarResult()

    def rollback(self) -> None:
        return None


def fake_session_without_runtime_overrides():
    """FastAPI get_session dependency override that yields the stub above."""
    yield FakeSessionWithoutRuntimeOverrides()


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
