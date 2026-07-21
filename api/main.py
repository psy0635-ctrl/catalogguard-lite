# 역할: FastAPI 앱을 만들고 CSV 검수 라우터와 health/readiness check를 등록합니다.
import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, status
from starlette.responses import PlainTextResponse, Response

from api.routes.inspections import router as inspections_router
from api.routes.inspection_jobs import router as inspection_jobs_router
from config.logging import configure_logging, log_event
from db.session import check_database_connection


REQUEST_ID_HEADER = "X-Request-ID"
api_logger = configure_logging()


async def internal_server_error_response(
    request: Request,
    _error: Exception,
) -> PlainTextResponse:
    """Add the request ID to the existing safe generic 500 response."""
    request_id = getattr(request.state, "request_id", "")
    headers = {REQUEST_ID_HEADER: request_id} if request_id else {}
    return PlainTextResponse(
        "Internal Server Error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers=headers,
    )


# FastAPI 앱의 시작점입니다. 여기서 앱 정보와 사용할 API 라우터를 등록합니다.
app = FastAPI(
    title="CatalogGuard Lite API",
    version="0.1.0",
    exception_handlers={500: internal_server_error_response},
)


@app.middleware("http")
async def log_http_request(request: Request, call_next) -> Response:
    """Assign a request ID and log completion or an unhandled failure."""
    request_id = uuid.uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as error:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        log_event(
            api_logger,
            logging.ERROR,
            event="http_request_failed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            duration_ms=duration_ms,
            error_type=type(error).__name__,
        )
        raise

    response.headers[REQUEST_ID_HEADER] = request_id
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    log_event(
        api_logger,
        logging.INFO,
        event="http_request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response

# CSV 검수 API 묶음을 현재 앱에 연결합니다.
app.include_router(inspections_router)
app.include_router(inspection_jobs_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    # 서버가 살아 있는지 빠르게 확인하는 가장 단순한 상태 확인 API입니다.
    return {
        "status": "ok",
        "service": "catalogguard-lite-api",
    }


@app.get("/ready")
def readiness_check(request: Request) -> dict[str, str]:
    try:
        check_database_connection()
    except Exception as error:
        log_event(
            api_logger,
            logging.ERROR,
            event="database_readiness_failed",
            request_id=request.state.request_id,
            error_type=type(error).__name__,
        )
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
