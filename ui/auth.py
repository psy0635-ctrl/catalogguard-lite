# 역할: Streamlit 로그인/로그아웃 UI와 로그인 상태(session_state) 관리를 담당합니다.
import streamlit as st

from clients.catalogguard_api import (
    CatalogGuardApiAuthenticationError,
    CatalogGuardApiConfigurationError,
    CatalogGuardApiConnectionError,
    CatalogGuardApiResponseError,
    CatalogGuardApiTimeoutError,
    InvalidCredentialsError,
    create_catalogguard_api_client,
)


ACCESS_TOKEN_STATE_KEY = "auth_access_token"
CURRENT_USERNAME_STATE_KEY = "auth_current_username"
CURRENT_ROLE_STATE_KEY = "auth_current_role"
LOGIN_ERROR_STATE_KEY = "auth_login_error"
FORM_NONCE_STATE_KEY = "auth_form_nonce"
ROLE_LABELS = {"operator": "운영자", "viewer": "조회자"}


def is_authenticated(session_state=None) -> bool:
    state = st.session_state if session_state is None else session_state
    return bool(state.get(ACCESS_TOKEN_STATE_KEY))


def get_current_role(session_state=None) -> str | None:
    state = st.session_state if session_state is None else session_state
    return state.get(CURRENT_ROLE_STATE_KEY)


def is_operator(session_state=None) -> bool:
    return get_current_role(session_state) == "operator"


def clear_auth_state(session_state) -> None:
    for key in (
        ACCESS_TOKEN_STATE_KEY,
        CURRENT_USERNAME_STATE_KEY,
        CURRENT_ROLE_STATE_KEY,
    ):
        session_state.pop(key, None)


def get_authenticated_api_client():
    """create_catalogguard_api_client()와 동일하게 동작하되, 로그인 상태면 토큰을 자동으로 붙입니다.

    설정 오류(CatalogGuardApiConfigurationError)는 그대로 전달하므로 기존 호출부의
    try/except 구조를 바꾸지 않고 create_catalogguard_api_client() 대신 사용할 수 있습니다.
    """
    api_client = create_catalogguard_api_client()
    access_token = st.session_state.get(ACCESS_TOKEN_STATE_KEY)
    if access_token:
        api_client.set_access_token(access_token)
    return api_client


def _submit_login(username: str, password: str) -> None:
    st.session_state[LOGIN_ERROR_STATE_KEY] = None
    if not username or not password:
        st.session_state[LOGIN_ERROR_STATE_KEY] = "아이디와 비밀번호를 입력해 주세요."
        return

    try:
        api_client = create_catalogguard_api_client()
        login_response = api_client.login(username=username, password=password)
        api_client.set_access_token(login_response["access_token"])
        current_user = api_client.get_current_user()
    except CatalogGuardApiConfigurationError:
        st.session_state[LOGIN_ERROR_STATE_KEY] = "API 주소가 설정되지 않았습니다."
        return
    except InvalidCredentialsError:
        st.session_state[LOGIN_ERROR_STATE_KEY] = (
            "아이디 또는 비밀번호가 올바르지 않습니다."
        )
        return
    except (
        CatalogGuardApiAuthenticationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        KeyError,
    ):
        st.session_state[LOGIN_ERROR_STATE_KEY] = "로그인 서버에 연결할 수 없습니다."
        return

    st.session_state[ACCESS_TOKEN_STATE_KEY] = login_response["access_token"]
    st.session_state[CURRENT_USERNAME_STATE_KEY] = current_user["username"]
    st.session_state[CURRENT_ROLE_STATE_KEY] = current_user["role"]


def render_login_form() -> None:
    st.subheader("로그인")
    # 제출할 때마다 위젯 key를 바꿔 비밀번호 입력값이 session_state에 계속 남지 않게 합니다.
    nonce = st.session_state.get(FORM_NONCE_STATE_KEY, 0)
    username = st.text_input("아이디", key=f"auth_username_input_{nonce}")
    password = st.text_input(
        "비밀번호", type="password", key=f"auth_password_input_{nonce}"
    )
    if st.button("로그인", key="auth_login_submit", type="primary"):
        _submit_login(username, password)
        st.session_state[FORM_NONCE_STATE_KEY] = nonce + 1
        st.rerun()

    error_message = st.session_state.get(LOGIN_ERROR_STATE_KEY)
    if error_message:
        st.error(error_message)


def render_logged_in_status() -> None:
    username = st.session_state.get(CURRENT_USERNAME_STATE_KEY, "")
    role = st.session_state.get(CURRENT_ROLE_STATE_KEY, "")
    role_label = ROLE_LABELS.get(role, role)
    st.write(f"{username} ({role_label})로 로그인했습니다.")
    if st.button("로그아웃", key="auth_logout_button"):
        clear_auth_state(st.session_state)
        st.rerun()


def render_auth_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 계정")
        if is_authenticated():
            render_logged_in_status()
        else:
            render_login_form()
