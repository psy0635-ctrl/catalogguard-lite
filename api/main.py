# 역할: FastAPI 앱을 만들고 CSV 검수 라우터와 health check를 등록합니다.
from fastapi import FastAPI

from api.routes.inspections import router as inspections_router


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
