# 역할: 로그인(access token 발급)과 현재 사용자 조회 API 엔드포인트입니다.
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from api.dependencies import get_current_user
from api.schemas import CurrentUserResponse, LoginRequest, LoginResponse
from core.security import create_access_token
from db.auth_service import authenticate_user
from db.models import User
from db.session import get_session


router = APIRouter()

INVALID_CREDENTIALS_DETAIL = {
    "code": "invalid_credentials",
    "message": "아이디 또는 비밀번호가 올바르지 않습니다.",
}


@router.post("/api/v1/auth/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    session: Session = Depends(get_session),
) -> LoginResponse:
    # 사용자가 없거나, 비밀번호가 틀리거나, 비활성 계정이어도 같은 오류만 반환합니다.
    # 세 경우를 구분해서 응답하면 계정 존재 여부나 활성 상태가 외부에 노출될 수 있습니다.
    user = authenticate_user(
        session,
        username=request.username,
        password=request.password,
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS_DETAIL,
        )

    access_token, expires_in = create_access_token(subject=user.username, role=user.role)
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
    )


@router.get("/api/v1/auth/me", response_model=CurrentUserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> CurrentUserResponse:
    return CurrentUserResponse(username=current_user.username, role=current_user.role)
