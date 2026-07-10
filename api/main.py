# 역할: FastAPI 앱을 만들고 CSV 검수 라우터와 health/readiness check를 등록합니다.
from fastapi import FastAPI, HTTPException, status

from api.routes.inspections import router as inspections_router
from db.session import check_database_connection


# FastAPI 앱의 시작점입니다. 여기서 앱 정보와 사용할 API 라우터를 등록합니다.
app = FastAPI(
    title="CatalogGuard Lite API",
    version="0.1.0",
)

# CSV 검수 API 묶음을 현재 앱에 연결합니다.
app.include_router(inspections_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    # 서버가 살아 있는지 빠르게 확인하는 가장 단순한 상태 확인 API입니다.
    return {
        "status": "ok",
        "service": "catalogguard-lite-api",
    }


@app.get("/ready")
def readiness_check() -> dict[str, str]:
    try:
        check_database_connection()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "service": "catalogguard-lite-api",
                "database": "unavailable",
            },
        ) from None

    return {
        "status": "ready",
        "service": "catalogguard-lite-api",
        "database": "ok",
    }
