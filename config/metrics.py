# 역할: Prometheus metrics 활성화 여부와 HTTP/Web ETL metric 정의·기록 helper를 모읍니다.
import os

from prometheus_client import CollectorRegistry, Counter, Histogram

CATALOGGUARD_METRICS_ENABLED_ENV_VAR = "CATALOGGUARD_METRICS_ENABLED"
# 이 값들(대소문자 무관) 중 하나일 때만 활성화합니다. 그 외 값(설정 안 함, "false" 포함)은
# 모두 안전하게 비활성화로 처리합니다.
_METRICS_ENABLED_TRUE_VALUES = {"true", "1", "yes"}

UNMATCHED_ROUTE_LABEL = "unmatched"
# 이 경로들은 일반 사용자 트래픽 지표를 왜곡하고(Prometheus가 /metrics를 계속 조회),
# health check가 지표 수집 상태에 의존하면 안 되므로 HTTP metric 집계에서 제외합니다.
EXCLUDED_METRIC_PATHS = frozenset({"/health", "/ready", "/metrics"})

# 앱 전역 REGISTRY 대신 이 모듈 전용 registry를 씁니다. 다른 라이브러리가 기본 REGISTRY에
# 등록할 수 있는 process/platform collector 잡음이 섞이지 않아 테스트와 /metrics 출력이
# 이 프로젝트가 실제로 정의한 metric으로만 구성됩니다.
REGISTRY = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "catalogguard_http_requests",
    "Total HTTP requests completed, excluding /health, /ready, /metrics.",
    labelnames=("method", "route", "status_class"),
    registry=REGISTRY,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "catalogguard_http_request_duration_seconds",
    "HTTP request duration in seconds, excluding /health, /ready, /metrics.",
    labelnames=("method", "route"),
    registry=REGISTRY,
)

WEB_ETL_RUNS_TOTAL = Counter(
    "catalogguard_web_etl_runs",
    'Web ETL (POST /api/v1/etl-loads) attempts by outcome: created, duplicate, failed.',
    labelnames=("outcome",),
    registry=REGISTRY,
)

WEB_ETL_ROWS_TOTAL = Counter(
    "catalogguard_web_etl_rows",
    "Rows processed by newly created Web ETL runs (result=loaded|rejected). "
    "Duplicate (created=False) requests do not add to this counter.",
    labelnames=("result",),
    registry=REGISTRY,
)


def is_metrics_enabled() -> bool:
    """CATALOGGUARD_METRICS_ENABLED가 true/1/yes(대소문자 무관)일 때만 True입니다."""
    value = os.environ.get(CATALOGGUARD_METRICS_ENABLED_ENV_VAR, "").strip().lower()
    return value in _METRICS_ENABLED_TRUE_VALUES


def status_class_label(status_code: int) -> str:
    return f"{status_code // 100}xx"


def record_http_request(
    *, method: str, route: str, status_code: int, duration_seconds: float
) -> None:
    """Record one completed (or failed) HTTP request. No-op unless metrics are enabled."""
    if not is_metrics_enabled():
        return
    HTTP_REQUESTS_TOTAL.labels(
        method=method, route=route, status_class=status_class_label(status_code)
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, route=route).observe(
        duration_seconds
    )


def record_web_etl_run(outcome: str) -> None:
    """outcome은 'created' | 'duplicate' | 'failed' 중 하나입니다."""
    if not is_metrics_enabled():
        return
    WEB_ETL_RUNS_TOTAL.labels(outcome=outcome).inc()


def record_web_etl_rows(*, loaded_rows: int | None, rejected_rows: int | None) -> None:
    """새로 생성된 배치(created=True)에서만 호출해, 동일 배치 재사용 시 중복 집계하지 않습니다."""
    if not is_metrics_enabled():
        return
    if loaded_rows:
        WEB_ETL_ROWS_TOTAL.labels(result="loaded").inc(loaded_rows)
    if rejected_rows:
        WEB_ETL_ROWS_TOTAL.labels(result="rejected").inc(rejected_rows)
