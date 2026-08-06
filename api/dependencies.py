# 역할: 로그인 사용자 확인(authentication)과 역할 기반 접근 제어(RBAC) FastAPI dependency입니다.
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from core.security import InvalidTokenError, decode_access_token
from db.auth_service import get_user_by_username
from db.models import User
from db.session import get_session_factory


AUTHENTICATE_HEADER = {"WWW-Authenticate": "Bearer"}
AUTHENTICATION_REQUIRED_DETAIL = {
    "code": "authentication_required",
    "message": "로그인이 필요합니다.",
}
INVALID_TOKEN_DETAIL = {
    "code": "invalid_token",
    "message": "인증 토큰이 유효하지 않습니다.",
}
INACTIVE_USER_DETAIL = {
    "code": "inactive_user",
    "message": "비활성화된 계정입니다.",
}
INSUFFICIENT_ROLE_DETAIL = {
    "code": "insufficient_role",
    "message": "이 작업을 수행할 권한이 없습니다.",
}

# tokenUrl은 OpenAPI 문서용 메타데이터일 뿐이며, 이 dependency가 직접 로그인을 처리하지는 않습니다.
_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
)


def get_current_user(
    token: str | None = Depends(_oauth2_scheme),
) -> User:
    """Resolve the caller's User from the Bearer token, re-checking DB state.

    role/is_active는 토큰 payload를 그대로 신뢰하지 않고 매 요청마다 DB에서 다시 확인합니다.
    이렇게 하면 이미 발급된 token이 있어도 계정을 비활성화하면 즉시 접근을 차단할 수 있습니다.

    이 조회는 route가 쓰는 요청 범위 session(Depends(get_session))과 별도의 짧은 session을 씁니다.
    같은 session을 공유하면 이 SELECT가 트랜잭션을 암묵적으로 시작시켜, 이후 쓰기 작업 route가
    수행하는 `with session.begin()`이 "트랜잭션이 이미 시작됨" 오류로 실패하기 때문입니다.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=AUTHENTICATION_REQUIRED_DETAIL,
            headers=AUTHENTICATE_HEADER,
        )

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_TOKEN_DETAIL,
            headers=AUTHENTICATE_HEADER,
        ) from None

    username = payload.get("sub")
    with get_session_factory()() as session:
        user = (
            get_user_by_username(session, username)
            if isinstance(username, str)
            else None
        )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_TOKEN_DETAIL,
            headers=AUTHENTICATE_HEADER,
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INACTIVE_USER_DETAIL,
            headers=AUTHENTICATE_HEADER,
        )
    return user


def require_roles(*allowed_roles: str):
    """Build a dependency that requires the current user's role to be in allowed_roles."""

    def _check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=INSUFFICIENT_ROLE_DETAIL,
            )
        return current_user

    return _check_role


# 조회 endpoint는 viewer/operator 모두 허용하고, 운영 데이터 변경 endpoint는 operator만 허용합니다.
require_viewer = require_roles("viewer", "operator")
require_operator = require_roles("operator")
