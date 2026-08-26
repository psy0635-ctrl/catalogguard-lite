from datetime import datetime
from math import ceil
from typing import Any

import pandas as pd
import streamlit as st

from clients.catalogguard_api import (
    CatalogGuardApiConfigurationError,
    CatalogGuardApiConnectionError,
    CatalogGuardApiResponseError,
    CatalogGuardApiTimeoutError,
    CatalogPromotionBlockedError,
    CatalogPromotionFailedError,
    CatalogPromotionNotFoundError,
    CatalogPromotionPreviewStaleError,
    CatalogPromotionRollbackNotFoundError,
    ETLInvalidUploadError,
    ETLLoadNotFoundError,
    ETLProfileActivationVersionError,
    ETLProfileInactiveError,
    ETLProfileNotFoundError,
    ETLUnsupportedProfileError,
)
from ui.auth import get_authenticated_api_client, is_operator


ETL_LOAD_LIMIT = 10
ETL_QUALITY_TREND_LIMIT = 10
ETL_PRODUCT_LIMIT = 20
ETL_REJECT_LIMIT = 20
UNKNOWN_SIZE_TOKEN_LIMIT = 20
PROMOTION_HISTORY_LIMIT = 10
PROMOTION_AUDIT_LIMIT = 10
ROLLBACK_HISTORY_LIMIT = 10
ROLLBACK_CHANGE_AUDIT_LIMIT = 10
ETL_LOAD_DISPLAY_COLUMNS = [
    "적재 배치 ID",
    "원본 파일명",
    "공급사 프로필",
    "프로필 버전",
    "적재 상품 수",
    "전체 행",
    "변환 거부",
    "적재 시간",
    "실행 사용자",
]
ETL_ERROR_DISPLAY_COLUMNS = ["오류 코드", "발생 건수"]
ETL_QUALITY_OBSERVABILITY_LIMIT = 10
ETL_QUALITY_OBSERVABILITY_ERROR_COLUMNS = ["오류 코드", "발생 건수", "발생 배치 수"]
ETL_QUALITY_OBSERVABILITY_BATCH_COLUMNS = [
    "적재 배치 ID",
    "적재 시간",
    "전체 행",
    "정상 적재",
    "Reject",
    "Reject 비율",
]
# API의 direction을 화면 문구로 옮깁니다. "악화"는 Reject 비율이 올랐다는 관찰 결과일
# 뿐이고 장애 판정이 아닙니다. 위험 임계값은 화면에서도 새로 만들지 않습니다.
ETL_QUALITY_DIRECTION_LABELS = {
    "improved": "개선",
    "unchanged": "동일",
    "worsened": "악화",
    "no_baseline": "비교 데이터 없음",
}
ETL_QUALITY_DIRECTION_UNKNOWN_LABEL = "알 수 없음"
ETL_QUALITY_OBSERVABILITY_NO_PROFILE_MESSAGE = (
    "관찰할 수 있는 ETL 품질 데이터가 없습니다. "
    "품질 정보가 기록된 배치가 있어야 공급사별 변화를 비교할 수 있습니다."
)
ETL_QUALITY_OBSERVABILITY_SELECT_PROFILE_MESSAGE = (
    "공급사를 선택하면 최신 배치와 직전 배치의 Reject 비율을 비교합니다."
)
# 0건과 1건은 사용자가 해야 할 일이 다릅니다. 0건은 볼 데이터 자체가 없고, 1건은 최신
# 배치는 있지만 비교 기준이 없는 상태라 다음 배치를 기다리면 됩니다.
ETL_QUALITY_OBSERVABILITY_NO_BATCH_MESSAGE = "비교할 ETL 품질 데이터가 없습니다."
ETL_QUALITY_OBSERVABILITY_SINGLE_BATCH_MESSAGE = (
    "최신 배치는 있지만 직전 배치가 없어 비교할 수 없습니다."
)
ETL_QUALITY_OBSERVABILITY_NO_ERROR_MESSAGE = (
    "최근 관찰 구간에 집계된 ETL 오류가 없습니다."
)
ETL_QUALITY_OBSERVABILITY_ERROR_MESSAGE = "ETL 품질 관찰 정보를 불러오지 못했습니다."
# 위 검색창의 "공급사 프로필"은 부분 검색어입니다. 그 문자열을 그대로 이 비교에 쓰면
# 서로 다른 공급사가 한 묶음으로 비교되므로, 여기서는 전용 조회가 돌려준 정확한
# profile_name만 고를 수 있게 합니다.
ETL_QUALITY_OBSERVABILITY_PROFILE_CAPTION = (
    "품질 정보가 기록된 ETL 배치가 있는 공급사 전체입니다. 아래 목록이나 위 검색어의 "
    "범위와 무관하며, 정확한 공급사 프로필 이름으로 비교합니다."
)
ETL_QUALITY_OBSERVABILITY_PROFILE_ERROR_MESSAGE = (
    "관찰할 수 있는 공급사 목록을 불러오지 못했습니다."
)
ETL_PROFILE_MAPPING_DISPLAY_COLUMNS = ["공급사 원본 컬럼", "CatalogGuard 컬럼"]
# 비활성 프로필 안내 문구입니다. 서버가 보낸 message 원문을 쓰지 않고 화면 문구는
# 여기서 관리합니다. 실행 실패와 상세 조회 실패는 사용자가 처한 상황이 달라 나눕니다.
ETL_INACTIVE_PROFILE_RUN_MESSAGE = (
    "선택한 ETL 프로필이 비활성화되었습니다. 사용할 수 있는 프로필을 다시 선택하세요."
)
ETL_INACTIVE_PROFILE_DETAIL_MESSAGE = "선택한 ETL 프로필이 비활성화되었습니다."
ETL_PROFILE_DEFAULTS_DISPLAY_COLUMNS = ["CatalogGuard 컬럼", "기본값"]
ETL_REJECT_DISPLAY_COLUMNS = ["원본 행", "오류 코드", "오류 필드", "오류 메시지"]
# 세 상태를 화면에서 절대 뭉개지 않습니다. "override 없음"은 비활성이 아니라 배포
# 기본값을 그대로 따르는 상태입니다.
ETL_PROFILE_ADMIN_RUNTIME_NO_OVERRIDE = "런타임 override 없음 (배포 기본값 사용)"
ETL_PROFILE_ADMIN_RUNTIME_INACTIVE = "런타임에서 비활성으로 지정"
ETL_PROFILE_ADMIN_ACTIVE_BADGE = "🟢 활성"
ETL_PROFILE_ADMIN_INACTIVE_BADGE = "🔴 비활성"
ETL_PROFILE_ADMIN_NO_VERSION = "없음"
ETL_PROFILE_ADMIN_DEACTIVATE_CONFIRM_LABEL = (
    "이 프로필의 신규 ETL 실행을 중단하는 것을 확인했습니다."
)
# 위쪽 actor/updated_at은 현재 runtime override 하나에 대한 current-state 정보이고,
# 성공한 운영 명령의 과거 기록은 아래 Activation 운영 이력이 따로 보여 줍니다. 이 caption은
# override가 있을 때만 그려지므로, "지금 보이는 이 값이 무엇인가"와 "되돌리면 어떻게 되는가"를
# 말합니다. reset하면 이 값은 사라지지만 그 명령 자체는 이력에 남는다는 것이 핵심입니다.
ETL_PROFILE_ADMIN_ACTOR_CAPTION = (
    "현재 런타임 override를 마지막으로 만든 사용자와 시각입니다. "
    "배포 기본값으로 되돌리면 이 값은 사라지지만, 성공한 활성화·비활성화·"
    "배포 기본값으로 되돌리기 명령은 아래 Activation 운영 이력에 남습니다."
)
# 서버 message 원문 대신 화면 문구를 씁니다. 사용자가 바로 할 수 있는 행동을 적습니다.
ETL_PROFILE_ADMIN_STALE_VERSION_MESSAGE = (
    "현재 배포에서 사용할 수 없는 버전입니다. 상태를 새로고침한 뒤 다시 선택하세요."
)
# reset은 "정리"가 아니라 상태 전환입니다. 명시적 비활성 override를 지우면 배포
# 기본값이 다시 적용되어 프로필이 되살아날 수 있으므로, 문구가 그 사실을 말해야 합니다.
ETL_PROFILE_ADMIN_NO_OVERRIDE_RESET_CAPTION = (
    "현재 런타임 override가 없습니다. 배포 기본값을 그대로 사용 중이라 되돌릴 설정이 없습니다."
)
ETL_PROFILE_ADMIN_RESET_CAPTION = (
    "런타임 설정을 지우면 이 프로필은 다시 배포 기본값을 따라갑니다. "
    "비활성화(명시적 비활성)와 달리 운영자가 내린 결정 자체가 사라집니다."
)
ETL_PROFILE_ADMIN_RESET_CONFIRM_LABEL = (
    "런타임 설정을 제거하고 배포 기본값으로 되돌리는 것을 확인했습니다."
)
ETL_PROFILE_ADMIN_RESET_BUTTON_LABEL = "배포 기본값으로 되돌리기"

ETL_PROFILE_ADMIN_HISTORY_LIMIT = 10
ETL_PROFILE_ADMIN_HISTORY_CAPTION = (
    "성공한 활성화·비활성화·초기화 명령을 최신순으로 보여 줍니다. "
    "이 기능이 추가된 이후 성공한 운영 명령만 표시합니다."
)
ETL_PROFILE_ADMIN_HISTORY_EMPTY_MESSAGE = (
    "아직 기록된 Activation 운영 이력이 없습니다. "
    "이 기능이 추가된 이후의 성공한 운영 명령부터 표시됩니다."
)
ETL_PROFILE_ADMIN_HISTORY_ERROR_MESSAGE = "Activation 운영 이력을 불러오지 못했습니다."
# reset을 "비활성화"로 적지 않습니다. override를 지운 것이지 내린 것이 아니고, 배포
# 기본값이 활성이면 reset 직후 그 프로필은 오히려 실행 가능해집니다.
ETL_PROFILE_ADMIN_HISTORY_ACTION_LABELS = {
    "activate": "버전 활성화",
    "deactivate": "비활성화",
    "reset": "배포 기본값으로 되돌리기",
}
ETL_PROFILE_ADMIN_HISTORY_UNKNOWN_ACTION_LABEL = "알 수 없음"
ETL_PROFILE_ADMIN_HISTORY_DISPLAY_COLUMNS = [
    "시각",
    "동작",
    "런타임 결과",
    "실제 적용 버전",
    "배포 기본 버전",
    "사용자",
]

CATALOG_RECONCILIATION_LIMIT = 50
CATALOG_RECONCILIATION_FIELD_COLUMNS = ["변경 필드", "변경 건수"]
CATALOG_RECONCILIATION_ITEM_COLUMNS = ["상품 ID", "상태", "변경 필드"]
CATALOG_RECONCILIATION_STATUS_LABELS = {
    "new": "신규",
    "changed": "변경",
    "unchanged": "동일",
    "not_observed_in_batch": "이번 배치 미관측",
}
# not_observed_in_batch를 삭제/판매 종료로 읽으면 안 됩니다. 지금 시스템은 공급사 피드가
# 전체 snapshot인지 부분 feed인지 보장하지 않으므로, 이 상태는 "이번 배치에 없었다"는
# 관측 사실일 뿐입니다.
CATALOG_RECONCILIATION_NOT_OBSERVED_NOTICE = (
    "이번 ETL 배치에서 관측되지 않은 운영 상품입니다. "
    "삭제 또는 판매 종료를 의미하지 않으며, 자동 삭제 대상으로 판단하지 않습니다."
)
# 이 보고서는 원본 CSV가 아니라 staging에 정상 적재된 상품을 비교합니다. reject된 행은
# 비교 대상에 없으므로, 원본에는 있었지만 거부된 상품이 "이번 배치 미관측"으로 보일 수
# 있습니다. 공급사가 보내지 않은 것과 구분되도록 알려 줍니다.
CATALOG_RECONCILIATION_LEGACY_QUALITY_NOTICE = (
    "이 배치는 ETL 품질 요약 저장 기능이 추가되기 전에 생성되어 "
    "원본 입력 대비 비교 범위를 확인할 수 없습니다."
)
UNKNOWN_SIZE_TOKEN_DISPLAY_COLUMNS = ["사이즈 토큰", "개수"]
ETL_PRODUCT_DISPLAY_COLUMNS = [
    "staging 상품 ID",
    "상품 그룹 ID",
    "상품 ID",
    "상품명",
    "카테고리",
    "색상",
    "사이즈",
    "재고",
    "정상가",
    "할인가",
    "이미지 경로",
    "설명",
    "판매자",
    "등록 시간",
]
PROMOTION_CHANGE_DISPLAY_COLUMNS = [
    "공급사",
    "외부 상품 ID",
    "변경 유형",
    "변경 필드",
    "변경 전 값",
    "변경 후 값",
]
PROMOTION_ACTION_LABELS = {
    "insert": "신규 등록",
    "update": "정보 수정",
    "unchanged": "변경 없음",
}
PROMOTION_HISTORY_DISPLAY_COLUMNS = [
    "실행 ID",
    "ETL 배치",
    "파일명",
    "상태",
    "신규",
    "수정",
    "변경 없음",
    "실행 시각",
    "실행 사용자",
]
PROMOTION_AUDIT_DISPLAY_COLUMNS = [
    "Audit ID",
    "상품 ID",
    "외부 상품 ID",
    "변경 유형",
    "변경 필드",
    "변경 전",
    "변경 후",
    "변경 시각",
]
ROLLBACK_HISTORY_DISPLAY_COLUMNS = [
    "Rollback ID",
    "대상 Promotion",
    "상태",
    "복구",
    "삭제",
    "충돌",
    "실행 시각",
    "실행 사용자",
]
ROLLBACK_CHANGE_AUDIT_DISPLAY_COLUMNS = [
    "Change ID",
    "원본 Audit ID",
    "상품 ID",
    "외부 상품 ID",
    "변경 유형",
    "변경 필드",
    "변경 전",
    "변경 후",
    "변경 시각",
]
ROLLBACK_ACTION_LABELS = {
    "delete": "상품 삭제",
    "restore": "이전 상태 복원",
}

ETL_LOAD_STATE_DEFAULTS = {
    "etl_load_initialized": False,
    "etl_load_filename_query": "",
    "etl_load_profile_query": "",
    "etl_load_applied_filename": "",
    "etl_load_applied_profile": "",
    "etl_load_offset": 0,
    "etl_load_list_response": None,
    "etl_load_list_error": None,
    "etl_load_quality_summary_initialized": False,
    "etl_load_quality_summary_response": None,
    "etl_load_quality_summary_error": None,
    "etl_load_quality_trend_initialized": False,
    "etl_load_quality_trend_response": None,
    "etl_load_quality_trend_error": None,
    # 품질 관찰은 기존 summary/trend와 다른 공급사를 볼 수 있으므로 상태를 분리합니다.
    "etl_quality_observability_profiles_initialized": False,
    "etl_quality_observability_profiles_response": None,
    "etl_quality_observability_profiles_error": None,
    "etl_quality_observability_selected_profile": None,
    "etl_quality_observability_initialized": False,
    "etl_quality_observability_response": None,
    "etl_quality_observability_error": None,
    "etl_load_selected_run_id": None,
    "etl_load_detail_requested": False,
    "etl_load_detail_response": None,
    "etl_load_detail_error": None,
    "etl_load_product_offset": 0,
    "etl_reject_offset": 0,
    "etl_reject_response": None,
    "etl_reject_error": None,
    "catalog_reconciliation_batch_id": None,
    "catalog_reconciliation_offset": 0,
    "catalog_reconciliation_response": None,
    "catalog_reconciliation_error": None,
    "catalog_promotion_preview_batch_id": None,
    "catalog_promotion_preview_response": None,
    "catalog_promotion_preview_hash": None,
    "catalog_promotion_preview_error": None,
    "catalog_promotion_confirmation": False,
    "catalog_promotion_confirmation_input": False,
    "catalog_promotion_in_flight": False,
    "catalog_promotion_result": None,
    "catalog_promotion_history_status": "전체",
    "catalog_promotion_history_offset": 0,
    "catalog_promotion_history_response": None,
    "catalog_promotion_history_error": None,
    "catalog_promotion_history_run_id": None,
    "catalog_promotion_history_detail_requested": False,
    "catalog_promotion_history_detail_response": None,
    "catalog_promotion_history_detail_error": None,
    "catalog_promotion_audit_offset": 0,
    "catalog_promotion_audit_response": None,
    "catalog_promotion_audit_error": None,
    "catalog_promotion_rollback_history_status": "전체",
    "catalog_promotion_rollback_history_offset": 0,
    "catalog_promotion_rollback_history_response": None,
    "catalog_promotion_rollback_history_error": None,
    "catalog_promotion_rollback_history_run_id": None,
    "catalog_promotion_rollback_history_detail_requested": False,
    "catalog_promotion_rollback_history_detail_response": None,
    "catalog_promotion_rollback_history_detail_error": None,
    "catalog_promotion_rollback_change_offset": 0,
    "catalog_promotion_rollback_change_response": None,
    "catalog_promotion_rollback_change_error": None,
    "etl_web_run_profiles_response": None,
    "etl_web_run_profiles_error": None,
    "etl_web_run_selected_profile_id": None,
    "etl_web_run_profile_detail_id": None,
    "etl_web_run_profile_detail_response": None,
    "etl_web_run_profile_detail_error": None,
    "etl_web_run_in_flight": False,
    "etl_web_run_result": None,
    "etl_web_run_error": None,
    # 운영 관리 화면 전용 상태입니다. 실행 selector(etl_web_run_*)와 key를 나눠, 관리
    # 화면을 만지는 것이 실행할 프로필 선택을 바꾸지 않게 합니다.
    "etl_profile_admin_profiles_response": None,
    "etl_profile_admin_profiles_error": None,
    "etl_profile_admin_selected_profile_id": None,
    "etl_profile_admin_activation_profile_id": None,
    "etl_profile_admin_activation_response": None,
    "etl_profile_admin_activation_error": None,
    "etl_profile_admin_selected_version": None,
    "etl_profile_admin_deactivate_confirmed": False,
    "etl_profile_admin_reset_confirmed": False,
    "etl_profile_admin_update_error": None,
    "etl_profile_admin_update_success": None,
    # history는 관리 selector와 별개로 페이지를 들고 있어 prefix를 따로 씁니다.
    "etl_profile_admin_history_profile_id": None,
    "etl_profile_admin_history_response": None,
    "etl_profile_admin_history_error": None,
    "etl_profile_admin_history_offset": 0,
}


def format_etl_datetime(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")

    text_value = str(value)
    normalized_value = (
        f"{text_value[:-1]}+00:00" if text_value.endswith("Z") else text_value
    )
    try:
        parsed_datetime = datetime.fromisoformat(normalized_value)
    except ValueError:
        return text_value
    return parsed_datetime.strftime("%Y-%m-%d %H:%M:%S")


def build_etl_load_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "적재 배치 ID": item.get("etl_load_run_id"),
            "원본 파일명": item.get("source_filename"),
            "공급사 프로필": item.get("profile_name"),
            "프로필 버전": item.get("profile_version"),
            "적재 상품 수": item.get("loaded_rows"),
            "전체 행": _display_nullable(item.get("total_rows")),
            "변환 거부": _display_nullable(item.get("rejected_rows")),
            "적재 시간": format_etl_datetime(item.get("created_at")),
            "실행 사용자": format_actor_username(item.get("actor_username")),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=ETL_LOAD_DISPLAY_COLUMNS)


def _display_nullable(value: object) -> object:
    return "" if value is None else value


def format_actor_username(actor_username: object) -> str:
    # migration 이전 row나 CLI로 적재된 row는 실행 사용자를 알 수 없습니다.
    if not isinstance(actor_username, str) or not actor_username.strip():
        return "알 수 없음"
    return actor_username


def format_etl_quality_rate(
    total_rows: int | None,
    loaded_rows: int | None,
) -> str:
    if total_rows is None or loaded_rows is None or total_rows <= 0:
        return "—"
    return f"{loaded_rows / total_rows * 100:.1f}%"


def build_catalog_reconciliation_field_dataframe(
    field_change_counts: dict[str, int] | None,
) -> pd.DataFrame:
    """Field-level change counts, most frequent first."""
    if not field_change_counts:
        return pd.DataFrame(columns=CATALOG_RECONCILIATION_FIELD_COLUMNS)
    rows = sorted(
        field_change_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return pd.DataFrame(
        [{"변경 필드": field_name, "변경 건수": count} for field_name, count in rows],
        columns=CATALOG_RECONCILIATION_FIELD_COLUMNS,
    )


def build_catalog_reconciliation_item_dataframe(
    items: list[dict[str, Any]] | None,
) -> pd.DataFrame:
    """One row per product: id, human-readable status, changed field names.

    서버가 준 순서를 그대로 유지합니다. 정렬은 서비스가 결정론적으로 정합니다.
    """
    if not items:
        return pd.DataFrame(columns=CATALOG_RECONCILIATION_ITEM_COLUMNS)
    rows = []
    for item in items:
        status = item.get("status", "")
        changed_fields = item.get("changed_fields") or {}
        rows.append(
            {
                "상품 ID": item.get("external_product_id", ""),
                "상태": CATALOG_RECONCILIATION_STATUS_LABELS.get(status, status),
                "변경 필드": ", ".join(sorted(changed_fields)) if changed_fields else "-",
            }
        )
    return pd.DataFrame(rows, columns=CATALOG_RECONCILIATION_ITEM_COLUMNS)


def build_catalog_reconciliation_reject_notice(
    rejected_rows: int | None,
) -> str | None:
    """Warn that rejected rows were never compared, or None when there is nothing to say.

    rejected_rows가 None이면 legacy 배치입니다. 0으로 바꿔 "거부 행이 없었다"고 말하지
    않습니다. 알 수 없다는 사실은 그대로 알 수 없다고 알립니다.
    """
    if rejected_rows is None:
        return CATALOG_RECONCILIATION_LEGACY_QUALITY_NOTICE
    if rejected_rows <= 0:
        return None
    return (
        f"원본 입력 중 {rejected_rows}개 행이 ETL 변환 과정에서 제외되었습니다. "
        "이 보고서는 정상 staging 상품만 운영 카탈로그와 비교하므로, "
        "'이번 배치 미관측'에는 reject 때문에 비교에서 빠진 상품이 포함될 수 있습니다."
    )


def build_etl_error_counts_dataframe(error_counts: dict[str, int] | None) -> pd.DataFrame:
    if not error_counts:
        return pd.DataFrame(columns=ETL_ERROR_DISPLAY_COLUMNS)
    rows = sorted(
        error_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return pd.DataFrame(
        [
            {"오류 코드": code, "발생 건수": count}
            for code, count in rows
        ],
        columns=ETL_ERROR_DISPLAY_COLUMNS,
    )


def build_etl_quality_observability_profile_options(
    response: dict[str, Any] | None,
) -> list[str]:
    """Exact profile_name values the comparison endpoint can actually be run for.

    후보는 화면에 지금 보이는 ETL 목록이 아니라 전용 조회의 응답에서 옵니다. 목록
    페이지에서 만들면 최근 10건에 배치가 없는 공급사를 고를 수 없었습니다.

    서버가 이미 중복 제거와 정렬을 마쳤고 client가 그 계약을 검증하므로, 여기서
    다시 정렬하거나 추려 내지 않습니다.
    """
    return [
        item["profile_name"]
        for item in (response or {}).get("items") or []
        if isinstance(item, dict) and isinstance(item.get("profile_name"), str)
    ]


def resolve_etl_quality_observability_selection(
    options: list[str],
    selected: object,
) -> str | None:
    """Keep the current supplier when it is still selectable, otherwise clear it.

    사라진 공급사를 첫 번째 항목으로 슬쩍 바꾸지 않습니다. 그렇게 하면 이전 공급사의
    숫자가 다른 공급사 이름 아래 그대로 남을 수 있어, 미선택으로 되돌려 사용자가
    직접 고르게 합니다.
    """
    return selected if isinstance(selected, str) and selected in options else None


def format_etl_quality_direction(direction: object) -> str:
    return ETL_QUALITY_DIRECTION_LABELS.get(
        direction if isinstance(direction, str) else "",
        ETL_QUALITY_DIRECTION_UNKNOWN_LABEL,
    )


def format_etl_rejection_rate_delta(delta: object) -> str:
    """Format the change as percentage points (%p), not as a percent change.

    4% -> 9%는 "125% 증가"가 아니라 "+5.00%p"입니다. 두 표현을 섞으면 운영자가 변화
    크기를 완전히 잘못 읽게 됩니다.
    """
    if delta is None or isinstance(delta, bool) or not isinstance(delta, (int, float)):
        return "—"
    if float(delta) == 0.0:
        return "0.00%p"
    return f"{float(delta):+.2f}%p"


def format_etl_batch_rejection_rate(batch: object) -> str:
    if not isinstance(batch, dict):
        return "—"
    rejection_rate = batch.get("rejection_rate")
    if isinstance(rejection_rate, bool) or not isinstance(rejection_rate, (int, float)):
        return "—"
    return f"{float(rejection_rate):.2f}%"


def build_etl_quality_error_code_dataframe(
    error_codes: list[dict[str, Any]] | None,
) -> pd.DataFrame:
    """Aggregated error codes, kept in the order the API already guarantees.

    API가 total_count DESC, error_code ASC로 정렬해서 보냅니다. 화면에서 다시 정렬하면
    같은 데이터가 두 곳에서 다른 순서로 보이게 되므로 순서를 그대로 씁니다.
    """
    if not error_codes:
        return pd.DataFrame(columns=ETL_QUALITY_OBSERVABILITY_ERROR_COLUMNS)
    return pd.DataFrame(
        [
            {
                "오류 코드": item.get("error_code"),
                "발생 건수": item.get("total_count"),
                "발생 배치 수": item.get("affected_batch_count"),
            }
            for item in error_codes
        ],
        columns=ETL_QUALITY_OBSERVABILITY_ERROR_COLUMNS,
    )


def build_etl_quality_recent_batch_dataframe(
    recent_batches: list[dict[str, Any]] | None,
) -> pd.DataFrame:
    """Observed batches as a table, oldest first, in the order the API sends them."""
    if not recent_batches:
        return pd.DataFrame(columns=ETL_QUALITY_OBSERVABILITY_BATCH_COLUMNS)
    return pd.DataFrame(
        [
            {
                "적재 배치 ID": item.get("etl_load_run_id"),
                "적재 시간": format_etl_datetime(item.get("created_at")),
                "전체 행": item.get("total_rows"),
                "정상 적재": item.get("loaded_rows"),
                "Reject": item.get("rejected_rows"),
                "Reject 비율": format_etl_batch_rejection_rate(item),
            }
            for item in recent_batches
        ],
        columns=ETL_QUALITY_OBSERVABILITY_BATCH_COLUMNS,
    )


def build_etl_quality_observability_notice(
    response: dict[str, Any] | None,
) -> str | None:
    """Tell "no data at all" apart from "no batch to compare against yet"."""
    if not isinstance(response, dict):
        return None
    if response.get("batch_count") == 0:
        return ETL_QUALITY_OBSERVABILITY_NO_BATCH_MESSAGE
    if response.get("direction") == "no_baseline":
        return ETL_QUALITY_OBSERVABILITY_SINGLE_BATCH_MESSAGE
    return None


def invalidate_etl_quality_observability(session_state) -> None:
    """Drop the cached comparison so another supplier's numbers are never reused."""
    session_state["etl_quality_observability_initialized"] = False
    session_state["etl_quality_observability_response"] = None
    session_state["etl_quality_observability_error"] = None


def build_etl_profile_mapping_dataframe(
    source_columns: dict[str, list[str]],
) -> pd.DataFrame:
    rows = [
        {
            "공급사 원본 컬럼": source_column,
            "CatalogGuard 컬럼": ", ".join(target_columns),
        }
        for source_column, target_columns in source_columns.items()
    ]
    return pd.DataFrame(rows, columns=ETL_PROFILE_MAPPING_DISPLAY_COLUMNS)


def build_etl_profile_defaults_dataframe(defaults: dict[str, str]) -> pd.DataFrame:
    rows = [
        {"CatalogGuard 컬럼": column, "기본값": value}
        for column, value in defaults.items()
    ]
    return pd.DataFrame(rows, columns=ETL_PROFILE_DEFAULTS_DISPLAY_COLUMNS)


def build_etl_rejection_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for item in items:
        errors = item.get("errors") or []
        rows.append(
            {
                "원본 행": item.get("source_row_number"),
                "오류 코드": ", ".join(str(error.get("code", "")) for error in errors),
                "오류 필드": ", ".join(str(error.get("field", "")) for error in errors),
                "오류 메시지": ", ".join(
                    str(error.get("message", "")) for error in errors
                ),
            }
        )
    return pd.DataFrame(rows, columns=ETL_REJECT_DISPLAY_COLUMNS)


def build_unknown_size_token_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {"사이즈 토큰": item.get("token"), "개수": item.get("count")}
        for item in items
    ]
    return pd.DataFrame(rows, columns=UNKNOWN_SIZE_TOKEN_DISPLAY_COLUMNS)


def build_etl_product_dataframe(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows = [
        {
            "staging 상품 ID": item.get("staging_product_id"),
            "상품 그룹 ID": item.get("product_group_id"),
            "상품 ID": item.get("product_id"),
            "상품명": item.get("product_name"),
            "카테고리": item.get("category"),
            "색상": item.get("color"),
            "사이즈": item.get("size"),
            "재고": item.get("stock"),
            "정상가": item.get("price"),
            "할인가": _display_nullable(item.get("sale_price")),
            "이미지 경로": item.get("image_path"),
            "설명": _display_nullable(item.get("description")),
            "판매자": _display_nullable(item.get("seller")),
            "등록 시간": format_etl_datetime(item.get("created_at")),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=ETL_PRODUCT_DISPLAY_COLUMNS)


def calculate_etl_pagination(
    *, total: int, limit: int, offset: int
) -> tuple[int, int, bool, bool]:
    safe_total = max(0, int(total))
    safe_limit = max(1, int(limit))
    safe_offset = max(0, int(offset))
    current_page = safe_offset // safe_limit + 1
    total_pages = max(1, ceil(safe_total / safe_limit))
    return (
        current_page,
        total_pages,
        safe_offset > 0,
        safe_offset + safe_limit < safe_total,
    )


def build_etl_load_option_label(item: dict[str, Any]) -> str:
    return (
        f"{item.get('etl_load_run_id')} · "
        f"{item.get('source_filename')} · "
        f"{item.get('profile_name')}"
    )


def build_etl_api_error_display_message(
    message: str, error: Exception | None = None
) -> str:
    request_id = getattr(error, "request_id", None)
    if request_id is None:
        return message
    request_id_message = f"요청 ID: {request_id}"
    if request_id_message in message:
        return message
    return f"{message}\n\n{request_id_message}"


def initialize_etl_load_state(session_state=None) -> None:
    state = st.session_state if session_state is None else session_state
    for key, value in ETL_LOAD_STATE_DEFAULTS.items():
        if key not in state:
            state[key] = value


def clear_catalog_promotion_preview_state(
    session_state,
    *,
    clear_result: bool = True,
) -> None:
    session_state["catalog_promotion_preview_batch_id"] = None
    session_state["catalog_promotion_preview_response"] = None
    session_state["catalog_promotion_preview_hash"] = None
    session_state["catalog_promotion_preview_error"] = None
    session_state["catalog_promotion_confirmation"] = False
    session_state["catalog_promotion_in_flight"] = False
    if clear_result:
        session_state["catalog_promotion_result"] = None


def synchronize_catalog_promotion_batch(session_state) -> None:
    selected_run_id = session_state.get("etl_load_selected_run_id")
    preview_batch_id = session_state.get("catalog_promotion_preview_batch_id")
    if preview_batch_id is None or preview_batch_id == selected_run_id:
        return
    clear_catalog_promotion_preview_state(session_state)


def store_catalog_promotion_preview(session_state, response: dict[str, Any]) -> None:
    selected_run_id = session_state.get("etl_load_selected_run_id")
    response_run_id = response.get("etl_load_run_id")
    if selected_run_id is None or response_run_id != selected_run_id:
        raise ValueError("promotion preview batch does not match selected batch")

    clear_catalog_promotion_preview_state(session_state)
    session_state["catalog_promotion_preview_batch_id"] = response_run_id
    session_state["catalog_promotion_preview_response"] = dict(response)
    preview_hash = response.get("preview_hash")
    session_state["catalog_promotion_preview_hash"] = (
        preview_hash if isinstance(preview_hash, str) else None
    )


def can_submit_catalog_promotion(session_state) -> bool:
    response = session_state.get("catalog_promotion_preview_response")
    selected_run_id = session_state.get("etl_load_selected_run_id")
    preview_batch_id = session_state.get("catalog_promotion_preview_batch_id")
    preview_hash = session_state.get("catalog_promotion_preview_hash")
    return (
        isinstance(response, dict)
        and selected_run_id is not None
        and selected_run_id == preview_batch_id
        and response.get("promotion_eligible") is True
        and isinstance(preview_hash, str)
        and len(preview_hash) == 64
        and session_state.get("catalog_promotion_confirmation") is True
        and session_state.get("catalog_promotion_in_flight") is not True
    )


def store_catalog_promotion_success(
    session_state,
    response: dict[str, Any],
) -> None:
    clear_catalog_promotion_preview_state(session_state, clear_result=False)
    session_state["catalog_promotion_result"] = dict(response)
    session_state["catalog_promotion_history_response"] = None
    session_state["catalog_promotion_history_error"] = None


def store_catalog_promotion_failure(
    session_state,
    *,
    kind: str,
    message: str,
) -> None:
    if kind == "preview_stale":
        clear_catalog_promotion_preview_state(session_state, clear_result=False)
    else:
        session_state["catalog_promotion_in_flight"] = False
    session_state["catalog_promotion_result"] = {
        "kind": kind,
        "message": message,
    }


def build_catalog_promotion_changes_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        supplier_key = item.get("supplier_key", "")
        external_product_id = item.get("external_product_id", "")
        action = str(item.get("action", ""))
        action_label = PROMOTION_ACTION_LABELS.get(action, action)
        changed_fields = item.get("changed_fields")
        if action == "update" and isinstance(changed_fields, dict):
            for field_name, change in changed_fields.items():
                change_data = change if isinstance(change, dict) else {}
                rows.append(
                    {
                        "공급사": supplier_key,
                        "외부 상품 ID": external_product_id,
                        "변경 유형": action_label,
                        "변경 필드": field_name,
                        "변경 전 값": _display_nullable(change_data.get("before")),
                        "변경 후 값": _display_nullable(change_data.get("after")),
                    }
                )
            continue

        rows.append(
            {
                "공급사": supplier_key,
                "외부 상품 ID": external_product_id,
                "변경 유형": action_label,
                "변경 필드": "상품 전체" if action == "insert" else "-",
                "변경 전 값": "-" if action == "insert" else "변경 없음",
                "변경 후 값": "신규 등록" if action == "insert" else "변경 없음",
            }
        )
    return pd.DataFrame(rows, columns=PROMOTION_CHANGE_DISPLAY_COLUMNS)


def build_catalog_promotion_history_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows = [
        {
            "실행 ID": item.get("promotion_run_id"),
            "ETL 배치": item.get("etl_load_run_id"),
            "파일명": item.get("source_filename", ""),
            "상태": item.get("status", ""),
            "신규": item.get("inserted_count", 0),
            "수정": item.get("updated_count", 0),
            "변경 없음": item.get("unchanged_count", 0),
            "실행 시각": format_etl_datetime(
                item.get("started_at") or item.get("created_at")
            ),
            "실행 사용자": format_actor_username(item.get("actor_username")),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=PROMOTION_HISTORY_DISPLAY_COLUMNS)


def build_catalog_promotion_rollback_history_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows = [
        {
            "Rollback ID": item.get("rollback_run_id"),
            "대상 Promotion": item.get("target_promotion_run_id"),
            "상태": item.get("status", ""),
            "복구": item.get("restored_count", 0),
            "삭제": item.get("deleted_count", 0),
            "충돌": item.get("conflict_count", 0),
            "실행 시각": format_etl_datetime(
                item.get("started_at") or item.get("created_at")
            ),
            "실행 사용자": format_actor_username(item.get("actor_username")),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=ROLLBACK_HISTORY_DISPLAY_COLUMNS)


def build_catalog_promotion_rollback_change_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        after_data = item.get("after_data")
        before_data = item.get("before_data")
        safe_after = after_data if isinstance(after_data, dict) else {}
        safe_before = before_data if isinstance(before_data, dict) else {}
        external_product_id = (
            safe_after["external_product_id"]
            if "external_product_id" in safe_after
            else safe_before.get("external_product_id", "")
        )
        action = str(item.get("action", ""))
        changed_fields = item.get("changed_fields")
        safe_changes = changed_fields if isinstance(changed_fields, dict) else {}
        for field_name in sorted(safe_changes):
            change = safe_changes.get(field_name)
            safe_change = change if isinstance(change, dict) else {}
            after_value = safe_change.get("after")
            rows.append(
                {
                    "Change ID": item.get("rollback_change_id"),
                    "원본 Audit ID": item.get("original_audit_id"),
                    "상품 ID": item.get("catalog_product_id"),
                    "외부 상품 ID": _display_nullable(external_product_id),
                    "변경 유형": ROLLBACK_ACTION_LABELS.get(
                        action,
                        action,
                    ),
                    "변경 필드": field_name,
                    "변경 전": _display_nullable(safe_change.get("before")),
                    "변경 후": (
                        "삭제됨"
                        if action == "delete" and after_value is None
                        else _display_nullable(after_value)
                    ),
                    "변경 시각": format_etl_datetime(item.get("created_at")),
                }
            )
    return pd.DataFrame(rows, columns=ROLLBACK_CHANGE_AUDIT_DISPLAY_COLUMNS)


def build_catalog_promotion_rollback_option_label(item: dict[str, Any]) -> str:
    return (
        f"{item.get('rollback_run_id')} · "
        f"Promotion {item.get('target_promotion_run_id')} · "
        f"{item.get('status', '')}"
    )


def invalidate_catalog_promotion_rollback_history(session_state) -> None:
    session_state["catalog_promotion_rollback_history_response"] = None
    session_state["catalog_promotion_rollback_history_error"] = None


def build_catalog_promotion_audit_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        after_data = item.get("after_data")
        before_data = item.get("before_data")
        safe_after = after_data if isinstance(after_data, dict) else {}
        safe_before = before_data if isinstance(before_data, dict) else {}
        external_product_id = safe_after.get(
            "external_product_id",
            safe_before.get("external_product_id", ""),
        )
        changed_fields = item.get("changed_fields")
        safe_changes = changed_fields if isinstance(changed_fields, dict) else {}
        for field_name in sorted(safe_changes):
            change = safe_changes.get(field_name)
            safe_change = change if isinstance(change, dict) else {}
            rows.append(
                {
                    "Audit ID": item.get("audit_id"),
                    "상품 ID": item.get("catalog_product_id"),
                    "외부 상품 ID": external_product_id,
                    "변경 유형": PROMOTION_ACTION_LABELS.get(
                        str(item.get("action", "")),
                        item.get("action", ""),
                    ),
                    "변경 필드": field_name,
                    "변경 전": _display_nullable(safe_change.get("before")),
                    "변경 후": _display_nullable(safe_change.get("after")),
                    "변경 시각": format_etl_datetime(item.get("created_at")),
                }
            )
    return pd.DataFrame(rows, columns=PROMOTION_AUDIT_DISPLAY_COLUMNS)


def reset_etl_load_detail_state(session_state) -> None:
    session_state["etl_load_detail_requested"] = False
    session_state["etl_load_detail_response"] = None
    session_state["etl_load_detail_error"] = None
    session_state["etl_load_product_offset"] = 0
    session_state["etl_reject_offset"] = 0
    session_state["etl_reject_response"] = None
    session_state["etl_reject_error"] = None


def apply_etl_load_search(session_state) -> None:
    session_state["etl_load_applied_filename"] = str(
        session_state.get("etl_load_filename_query", "")
    ).strip()
    session_state["etl_load_applied_profile"] = str(
        session_state.get("etl_load_profile_query", "")
    ).strip()
    session_state["etl_load_offset"] = 0
    session_state["etl_load_list_response"] = None
    session_state["etl_load_list_error"] = None
    session_state["etl_load_initialized"] = False
    session_state["etl_load_quality_summary_initialized"] = False
    session_state["etl_load_quality_summary_response"] = None
    session_state["etl_load_quality_summary_error"] = None
    session_state["etl_load_quality_trend_initialized"] = False
    session_state["etl_load_quality_trend_response"] = None
    session_state["etl_load_quality_trend_error"] = None
    session_state["etl_load_selected_run_id"] = None
    reset_etl_load_detail_state(session_state)
    clear_catalog_promotion_preview_state(session_state)


def _on_etl_load_selection_change(session_state) -> None:
    reset_etl_load_detail_state(session_state)
    clear_catalog_promotion_preview_state(session_state)


def _catalog_promotion_error_message(error: Exception) -> str:
    if isinstance(error, CatalogGuardApiConnectionError):
        return "CatalogGuard API 서버에 연결할 수 없습니다."
    if isinstance(error, CatalogGuardApiTimeoutError):
        return "CatalogGuard API 서버의 응답 시간이 초과되었습니다."
    if isinstance(error, ETLLoadNotFoundError):
        return "선택한 ETL 적재 이력을 찾을 수 없습니다."
    if isinstance(error, CatalogGuardApiResponseError):
        return "운영 상품 반영 요청을 처리하지 못했습니다."
    return "운영 상품 반영 요청 중 오류가 발생했습니다."


def _render_catalog_promotion_result() -> None:
    result = st.session_state.get("catalog_promotion_result")
    if not isinstance(result, dict):
        return

    if result.get("status") == "succeeded":
        if result.get("created") is True:
            st.success("운영 상품 반영이 완료되었습니다.")
        else:
            st.info(
                "이미 처리된 ETL 적재 결과입니다. 기존 운영 상품 반영 결과를 표시합니다."
            )
        count_columns = st.columns(3)
        count_columns[0].metric("신규 등록", result.get("inserted_count", 0), border=True)
        count_columns[1].metric("정보 수정", result.get("updated_count", 0), border=True)
        count_columns[2].metric("변경 없음", result.get("unchanged_count", 0), border=True)
        st.caption("새로운 반영이 필요하면 미리보기를 다시 실행하세요.")
        return

    kind = result.get("kind")
    message = str(result.get("message") or "")
    if kind == "preview_stale":
        st.error(
            "미리보기 이후 상품 데이터가 변경되었습니다. "
            "미리보기를 다시 실행하세요."
        )
    elif kind == "promotion_blocked":
        st.error("현재 ETL 적재 결과는 운영 상품에 반영할 수 없습니다.")
        if message:
            st.warning(message)
    elif kind == "promotion_failed":
        st.error("운영 상품 반영 중 오류가 발생했습니다.")
    elif message:
        st.error(message)


def _request_catalog_promotion_preview(api_client) -> None:
    selected_run_id = st.session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return

    clear_catalog_promotion_preview_state(st.session_state)
    st.session_state["catalog_promotion_in_flight"] = True
    try:
        with st.spinner("운영 반영 미리보기를 계산하고 있습니다."):
            response = api_client.get_catalog_promotion_preview(selected_run_id)
        store_catalog_promotion_preview(st.session_state, response)
    except (
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        ETLLoadNotFoundError,
        CatalogGuardApiResponseError,
    ) as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="preview_failed",
            message=build_etl_api_error_display_message(
                _catalog_promotion_error_message(error),
                error,
            ),
        )
    finally:
        st.session_state["catalog_promotion_in_flight"] = False


def _submit_catalog_promotion(api_client) -> None:
    if not can_submit_catalog_promotion(st.session_state):
        return

    selected_run_id = st.session_state["etl_load_selected_run_id"]
    preview_hash = st.session_state["catalog_promotion_preview_hash"]
    st.session_state["catalog_promotion_in_flight"] = True
    try:
        with st.spinner("운영 상품에 반영하고 있습니다."):
            response = api_client.create_catalog_promotion(
                selected_run_id,
                confirmation=True,
                expected_preview_hash=preview_hash,
            )
        store_catalog_promotion_success(st.session_state, response)
    except CatalogPromotionPreviewStaleError as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="preview_stale",
            message=str(error),
        )
    except CatalogPromotionBlockedError as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="promotion_blocked",
            message=str(error),
        )
    except CatalogPromotionFailedError as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="promotion_failed",
            message=str(error),
        )
    except (
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        ETLLoadNotFoundError,
        CatalogGuardApiResponseError,
    ) as error:
        store_catalog_promotion_failure(
            st.session_state,
            kind="promotion_failed",
            message=build_etl_api_error_display_message(
                _catalog_promotion_error_message(error),
                error,
            ),
        )
    finally:
        st.session_state["catalog_promotion_in_flight"] = False


def _render_catalog_promotion_preview(api_client) -> None:
    if not isinstance(
        st.session_state.get("catalog_promotion_preview_response"),
        dict,
    ):
        st.session_state["catalog_promotion_confirmation_input"] = False
    st.divider()
    st.subheader("운영 상품 반영")
    st.write(
        "선택한 ETL 적재 결과와 현재 운영 상품을 비교한 뒤, "
        "변경 내용을 확인하고 명시적으로 승인해 반영합니다."
    )
    selected_run_id = st.session_state.get("etl_load_selected_run_id")
    in_flight = st.session_state.get("catalog_promotion_in_flight") is True
    if selected_run_id is None:
        st.info("운영 상품 반영 결과를 확인할 ETL 적재 이력을 선택하세요.")

    if st.button(
        "운영 반영 미리보기",
        key="catalog_promotion_preview",
        disabled=selected_run_id is None or in_flight,
        type="secondary",
    ):
        _request_catalog_promotion_preview(api_client)

    _render_catalog_promotion_result()
    preview = st.session_state.get("catalog_promotion_preview_response")
    if not isinstance(preview, dict):
        return

    eligible = preview.get("promotion_eligible") is True
    if eligible:
        st.success(
            "반영 가능 — ETL 적재 결과를 운영 상품에 반영할 수 있습니다."
        )
    else:
        st.error(
            "반영 불가 — 현재 ETL 적재 결과는 운영 상품에 반영할 수 없습니다."
        )
        for reason in preview.get("blocked_reasons") or []:
            if isinstance(reason, dict) and reason.get("message"):
                st.warning(str(reason["message"]))

    metric_columns = st.columns(4)
    metric_columns[0].metric("신규 등록 예정", preview.get("insert_count", 0), border=True)
    metric_columns[1].metric("수정 예정", preview.get("update_count", 0), border=True)
    metric_columns[2].metric("변경 없음", preview.get("unchanged_count", 0), border=True)
    total_products = (
        int(preview.get("insert_count", 0))
        + int(preview.get("update_count", 0))
        + int(preview.get("unchanged_count", 0))
    )
    metric_columns[3].metric("전체 대상 상품", total_products, border=True)

    items = preview.get("items") or []
    if items:
        st.markdown("#### 상품별 변경 내용")
        display_dataframe = build_catalog_promotion_changes_dataframe(items)
        for value_column in ("변경 전 값", "변경 후 값"):
            display_dataframe[value_column] = display_dataframe[value_column].map(str)
        st.dataframe(
            display_dataframe,
            width="stretch",
            hide_index=True,
        )

    confirmation = st.checkbox(
        "미리보기 내용을 확인했으며 운영 상품 반영에 동의합니다.",
        key="catalog_promotion_confirmation_input",
        disabled=not eligible or not st.session_state.get(
            "catalog_promotion_preview_hash"
        ),
    )
    st.session_state["catalog_promotion_confirmation"] = bool(confirmation)
    if not is_operator():
        st.caption("운영 상품 반영은 운영자 권한이 필요합니다.")
    if st.button(
        "운영 상품에 반영",
        key="catalog_promotion_submit",
        disabled=not can_submit_catalog_promotion(st.session_state) or not is_operator(),
        type="primary",
    ):
        _submit_catalog_promotion(api_client)
        st.rerun()


def build_etl_load_request_params(
    session_state,
    *,
    limit: int = ETL_LOAD_LIMIT,
    offset: int | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "limit": limit,
        "offset": session_state.get("etl_load_offset", 0)
        if offset is None
        else offset,
    }
    filename = str(session_state.get("etl_load_applied_filename", "")).strip()
    profile_name = str(session_state.get("etl_load_applied_profile", "")).strip()
    if filename:
        params["filename"] = filename
    if profile_name:
        params["profile_name"] = profile_name
    return params


def _fetch_etl_load_list(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("etl_load_initialized"):
        cached_response = session_state.get("etl_load_list_response")
        if isinstance(cached_response, dict):
            return cached_response
        session_state["etl_load_initialized"] = False

    try:
        response = api_client.list_etl_loads(
            **build_etl_load_request_params(session_state)
        )
        session_state["etl_load_list_response"] = response
        session_state["etl_load_list_error"] = None
        session_state["etl_load_initialized"] = True
        return response
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_load_list_error"] = error
        session_state["etl_load_initialized"] = False
        return None


def _fetch_etl_load_quality_summary(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("etl_load_quality_summary_initialized"):
        cached_response = session_state.get("etl_load_quality_summary_response")
        return cached_response if isinstance(cached_response, dict) else None

    profile_name = str(session_state.get("etl_load_applied_profile", "")).strip()
    try:
        response = api_client.get_etl_load_quality_summary(
            profile_name=profile_name or None,
        )
        session_state["etl_load_quality_summary_response"] = response
        session_state["etl_load_quality_summary_error"] = None
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_load_quality_summary_response"] = None
        session_state["etl_load_quality_summary_error"] = error
    session_state["etl_load_quality_summary_initialized"] = True
    return session_state["etl_load_quality_summary_response"]


def _render_etl_load_quality_summary(api_client) -> None:
    response = _fetch_etl_load_quality_summary(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("etl_load_quality_summary_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    "ETL 품질 요약을 불러오지 못했습니다.",
                    error,
                )
            )
        return

    st.subheader("ETL 품질 요약")
    metric_columns = st.columns(6)
    metric_columns[0].metric("실행 배치", response.get("batch_count", 0), border=True)
    metric_columns[1].metric(
        "품질 집계 가능 배치",
        response.get("quality_available_batch_count", 0),
        border=True,
    )
    metric_columns[2].metric("전체 입력", response.get("total_rows", 0), border=True)
    metric_columns[3].metric("정상 적재", response.get("loaded_rows", 0), border=True)
    metric_columns[4].metric("Reject", response.get("rejected_rows", 0), border=True)
    metric_columns[5].metric(
        "Reject 비율",
        f"{float(response.get('rejection_rate', 0.0)):.2f}%",
        border=True,
    )
    if response.get("quality_unavailable_batch_count", 0) > 0:
        st.info("과거 일부 배치는 품질 요약 정보가 없어 집계에서 제외되었습니다.")


def _fetch_etl_load_quality_trend(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("etl_load_quality_trend_initialized"):
        cached_response = session_state.get("etl_load_quality_trend_response")
        return cached_response if isinstance(cached_response, dict) else None

    profile_name = str(session_state.get("etl_load_applied_profile", "")).strip()
    try:
        response = api_client.get_etl_load_quality_trend(
            profile_name=profile_name or None,
            limit=ETL_QUALITY_TREND_LIMIT,
        )
        session_state["etl_load_quality_trend_response"] = response
        session_state["etl_load_quality_trend_error"] = None
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_load_quality_trend_response"] = None
        session_state["etl_load_quality_trend_error"] = error
    session_state["etl_load_quality_trend_initialized"] = True
    return session_state["etl_load_quality_trend_response"]


def _render_etl_load_quality_trend(api_client) -> None:
    response = _fetch_etl_load_quality_trend(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("etl_load_quality_trend_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    "ETL 품질 추이를 불러오지 못했습니다.",
                    error,
                )
            )
        return

    st.subheader("최근 ETL 품질 추이")
    items = response.get("items") or []
    if not items:
        st.info("표시할 품질 추이 데이터가 없습니다.")
        return

    st.caption("최근 품질 집계 가능 배치의 Reject 비율(%) 추이입니다.")
    st.line_chart(
        pd.DataFrame(items),
        x="created_at",
        y="rejection_rate",
        x_label="배치 시각",
        y_label="Reject 비율 (%)",
        width="stretch",
    )


def _fetch_etl_quality_observability_profiles(
    api_client,
    session_state,
) -> dict[str, Any] | None:
    if session_state.get("etl_quality_observability_profiles_initialized"):
        cached_response = session_state.get(
            "etl_quality_observability_profiles_response"
        )
        return cached_response if isinstance(cached_response, dict) else None

    try:
        response = api_client.get_etl_quality_observability_profiles()
        session_state["etl_quality_observability_profiles_response"] = response
        session_state["etl_quality_observability_profiles_error"] = None
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_quality_observability_profiles_response"] = None
        session_state["etl_quality_observability_profiles_error"] = error
    session_state["etl_quality_observability_profiles_initialized"] = True
    return session_state["etl_quality_observability_profiles_response"]


def _on_etl_quality_observability_profile_change(session_state) -> None:
    invalidate_etl_quality_observability(session_state)


def _fetch_etl_quality_observability(api_client, session_state) -> dict[str, Any] | None:
    profile_name = session_state.get("etl_quality_observability_selected_profile")
    if not isinstance(profile_name, str) or not profile_name.strip():
        return None
    if session_state.get("etl_quality_observability_initialized"):
        cached_response = session_state.get("etl_quality_observability_response")
        return cached_response if isinstance(cached_response, dict) else None

    try:
        response = api_client.get_etl_quality_observability(
            profile_name=profile_name,
            limit=ETL_QUALITY_OBSERVABILITY_LIMIT,
        )
        session_state["etl_quality_observability_response"] = response
        session_state["etl_quality_observability_error"] = None
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_quality_observability_response"] = None
        session_state["etl_quality_observability_error"] = error
    session_state["etl_quality_observability_initialized"] = True
    return session_state["etl_quality_observability_response"]


def _render_etl_quality_observability(api_client) -> None:
    """Compare one supplier's latest batch with the previous one, and show why."""
    st.subheader("ETL 품질 관찰")
    st.caption(
        "같은 공급사의 최신 배치를 직전 배치와 비교해 Reject 비율 변화와 주요 오류 "
        "코드를 보여 줍니다."
    )

    profiles_response = _fetch_etl_quality_observability_profiles(
        api_client,
        st.session_state,
    )
    if profiles_response is None:
        error = st.session_state.get("etl_quality_observability_profiles_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    ETL_QUALITY_OBSERVABILITY_PROFILE_ERROR_MESSAGE,
                    error,
                )
            )
        return

    profile_options = build_etl_quality_observability_profile_options(
        profiles_response
    )
    # 고를 공급사가 없으면 비교 조회를 보내 봐야 빈 결과뿐이므로 요청하지 않습니다.
    if not profile_options:
        st.info(ETL_QUALITY_OBSERVABILITY_NO_PROFILE_MESSAGE)
        return

    resolved_profile = resolve_etl_quality_observability_selection(
        profile_options,
        st.session_state.get("etl_quality_observability_selected_profile"),
    )
    if resolved_profile != st.session_state.get(
        "etl_quality_observability_selected_profile"
    ):
        # 더 이상 고를 수 없는 공급사였다면, 그 공급사로 받아 둔 결과도 함께 버립니다.
        st.session_state["etl_quality_observability_selected_profile"] = (
            resolved_profile
        )
        invalidate_etl_quality_observability(st.session_state)

    st.caption(ETL_QUALITY_OBSERVABILITY_PROFILE_CAPTION)
    st.selectbox(
        "관찰할 공급사",
        options=[None, *profile_options],
        format_func=lambda profile_name: (
            "공급사를 선택하세요." if profile_name is None else profile_name
        ),
        key="etl_quality_observability_selected_profile",
        on_change=_on_etl_quality_observability_profile_change,
        args=(st.session_state,),
    )

    response = _fetch_etl_quality_observability(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("etl_quality_observability_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    ETL_QUALITY_OBSERVABILITY_ERROR_MESSAGE,
                    error,
                )
            )
        else:
            st.info(ETL_QUALITY_OBSERVABILITY_SELECT_PROFILE_MESSAGE)
        return

    notice = build_etl_quality_observability_notice(response)
    if response.get("batch_count") == 0:
        st.info(notice or ETL_QUALITY_OBSERVABILITY_NO_BATCH_MESSAGE)
        return

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "최신 Reject 비율",
        format_etl_batch_rejection_rate(response.get("latest_batch")),
        border=True,
    )
    metric_columns[1].metric(
        "직전 Reject 비율",
        format_etl_batch_rejection_rate(response.get("previous_batch")),
        border=True,
    )
    metric_columns[2].metric(
        "변화량",
        format_etl_rejection_rate_delta(response.get("rejection_rate_delta")),
        border=True,
    )
    metric_columns[3].metric(
        "방향",
        format_etl_quality_direction(response.get("direction")),
        border=True,
    )

    direction = response.get("direction")
    if direction == "improved":
        st.success("Reject 비율이 직전 배치보다 낮아졌습니다.")
    elif direction == "worsened":
        # 비율이 올랐다는 관찰 결과일 뿐입니다. 장애 판정이나 자동 조치는 하지 않습니다.
        st.warning("Reject 비율이 직전 배치보다 높아졌습니다.")
    elif direction == "unchanged":
        st.info("Reject 비율이 직전 배치와 같습니다.")
    if notice is not None:
        st.info(notice)

    st.markdown("#### 주요 오류 코드")
    error_codes = response.get("error_codes") or []
    if not error_codes:
        st.info(ETL_QUALITY_OBSERVABILITY_NO_ERROR_MESSAGE)
    else:
        st.dataframe(
            build_etl_quality_error_code_dataframe(error_codes),
            width="stretch",
            hide_index=True,
        )

    recent_batches = response.get("recent_batches") or []
    if recent_batches:
        st.markdown("#### 관찰한 배치")
        st.caption(
            f"품질 정보가 있는 최근 {len(recent_batches)}개 배치입니다. "
            "오래된 배치부터 표시합니다."
        )
        st.dataframe(
            build_etl_quality_recent_batch_dataframe(recent_batches),
            width="stretch",
            hide_index=True,
        )


def _fetch_etl_load_detail(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("etl_load_detail_response") is not None:
        return session_state["etl_load_detail_response"]
    if session_state.get("etl_load_detail_error") is not None:
        return None
    selected_run_id = session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return None
    try:
        response = api_client.get_etl_load_detail(
            int(selected_run_id),
            product_limit=ETL_PRODUCT_LIMIT,
            product_offset=session_state["etl_load_product_offset"],
        )
        session_state["etl_load_detail_response"] = response
        session_state["etl_load_detail_error"] = None
        return response
    except (
        ETLLoadNotFoundError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_load_detail_error"] = error
        return None


def _fetch_etl_rejections(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("etl_reject_response") is not None:
        return session_state["etl_reject_response"]
    if session_state.get("etl_reject_error") is not None:
        return None
    selected_run_id = session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return None
    try:
        response = api_client.list_etl_rejections(
            int(selected_run_id),
            limit=ETL_REJECT_LIMIT,
            offset=session_state["etl_reject_offset"],
        )
        session_state["etl_reject_response"] = response
        session_state["etl_reject_error"] = None
        return response
    except (
        ETLLoadNotFoundError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_reject_error"] = error
        return None


def _render_etl_error(error: Exception, *, detail: bool = False) -> None:
    if isinstance(error, CatalogGuardApiConfigurationError):
        message = "ETL 적재 이력 API 주소가 설정되지 않았습니다."
    elif isinstance(error, CatalogGuardApiConnectionError):
        message = "ETL 적재 이력 서버에 연결할 수 없습니다."
    elif isinstance(error, CatalogGuardApiTimeoutError):
        message = "ETL 적재 이력 서버 응답 시간이 초과되었습니다."
    elif isinstance(error, ETLLoadNotFoundError):
        message = "ETL 적재 배치를 찾을 수 없습니다."
    else:
        message = (
            "ETL 적재 상세 정보를 불러오는 중 오류가 발생했습니다."
            if detail
            else "ETL 적재 이력을 불러오는 중 오류가 발생했습니다."
        )
    st.error(build_etl_api_error_display_message(message, error))


def _render_etl_rejections(api_client, detail_response: dict[str, Any]) -> None:
    if not detail_response.get("reject_details_stored", False):
        st.info(
            "이 배치는 reject 상세 저장 기능 도입 전에 생성되어 거부 행 상세가 없습니다."
        )
        return

    response = _fetch_etl_rejections(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("etl_reject_error")
        if error is not None:
            _render_etl_error(error, detail=True)
        return
    if not response.get("available", False):
        st.info("이 배치에는 거부 행 상세가 없습니다.")
        return

    items = response.get("items") or []
    if not items:
        st.info("거부 행이 없습니다.")
        return

    st.subheader("거부 행 상세")
    st.dataframe(
        build_etl_rejection_dataframe(items),
        width="stretch",
        hide_index=True,
    )
    for item in items:
        with st.expander(f"원본 행 {item.get('source_row_number')} - 마스킹 원본"):
            st.json(item.get("masked_source_data") or {})

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ETL_REJECT_LIMIT,
        offset=st.session_state["etl_reject_offset"],
    )
    st.caption(f"거부 행 {current_page} / {total_pages} 페이지 · 전체 {total}개")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "거부 행 이전",
            disabled=not has_previous,
            key="etl_reject_previous",
            type="tertiary",
        ):
            st.session_state["etl_reject_offset"] -= ETL_REJECT_LIMIT
            st.session_state["etl_reject_response"] = None
            st.rerun()
    with next_col:
        if st.button(
            "거부 행 다음",
            disabled=not has_next,
            key="etl_reject_next",
            type="tertiary",
        ):
            st.session_state["etl_reject_offset"] += ETL_REJECT_LIMIT
            st.session_state["etl_reject_response"] = None
            st.rerun()


def _render_etl_search_controls() -> None:
    filename_col, profile_col, search_col = st.columns([3, 3, 1])
    with filename_col:
        st.text_input(
            "원본 파일명",
            key="etl_load_filename_query",
            placeholder="예: vendor_products.csv",
        )
    with profile_col:
        st.text_input(
            "공급사 프로필",
            key="etl_load_profile_query",
            placeholder="예: sample_fashion_vendor_v2",
        )
    with search_col:
        st.button(
            "조회",
            key="etl_load_search",
            on_click=apply_etl_load_search,
            args=(st.session_state,),
        )


def _render_etl_load_pagination(response: dict[str, Any]) -> None:
    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ETL_LOAD_LIMIT,
        offset=st.session_state["etl_load_offset"],
    )
    st.caption(f"{current_page} / {total_pages} 페이지 · 전체 {total}개 배치")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "이전",
            disabled=not has_previous,
            key="etl_load_previous",
            type="tertiary",
        ):
            st.session_state["etl_load_offset"] -= ETL_LOAD_LIMIT
            st.session_state["etl_load_list_response"] = None
            reset_etl_load_detail_state(st.session_state)
            st.rerun()
    with next_col:
        if st.button(
            "다음",
            disabled=not has_next,
            key="etl_load_next",
            type="tertiary",
        ):
            st.session_state["etl_load_offset"] += ETL_LOAD_LIMIT
            st.session_state["etl_load_list_response"] = None
            reset_etl_load_detail_state(st.session_state)
            st.rerun()


def synchronize_catalog_reconciliation_batch(session_state) -> None:
    """Drop a cached report that belongs to a previously selected batch."""
    selected_run_id = session_state.get("etl_load_selected_run_id")
    cached_batch_id = session_state.get("catalog_reconciliation_batch_id")
    if cached_batch_id is None or cached_batch_id == selected_run_id:
        return
    session_state["catalog_reconciliation_batch_id"] = None
    session_state["catalog_reconciliation_offset"] = 0
    session_state["catalog_reconciliation_response"] = None
    session_state["catalog_reconciliation_error"] = None


def _fetch_catalog_reconciliation(api_client, session_state) -> dict[str, Any] | None:
    if session_state.get("catalog_reconciliation_response") is not None:
        return session_state["catalog_reconciliation_response"]
    if session_state.get("catalog_reconciliation_error") is not None:
        return None
    selected_run_id = session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return None
    try:
        response = api_client.get_catalog_reconciliation(
            int(selected_run_id),
            limit=CATALOG_RECONCILIATION_LIMIT,
            offset=session_state.get("catalog_reconciliation_offset", 0),
        )
        session_state["catalog_reconciliation_batch_id"] = selected_run_id
        session_state["catalog_reconciliation_response"] = response
        session_state["catalog_reconciliation_error"] = None
        return response
    except (
        ETLLoadNotFoundError,
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["catalog_reconciliation_error"] = error
        return None


def _render_catalog_reconciliation(api_client) -> None:
    """Show how this batch differs from the live catalog. Read-only."""
    st.subheader("상품 동기화 차이")
    st.caption(
        "선택한 ETL 배치에서 정상 staging에 적재된 상품과 현재 운영 카탈로그를 비교한 "
        "조회 전용 보고서입니다. 이 화면은 운영 상품을 변경하지 않습니다."
    )

    response = _fetch_catalog_reconciliation(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("catalog_reconciliation_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    "상품 동기화 차이를 불러오지 못했습니다.", error
                )
            )
        return

    metric_columns = st.columns(4)
    metric_columns[0].metric("신규", response.get("new_count", 0), border=True)
    metric_columns[1].metric("변경", response.get("changed_count", 0), border=True)
    metric_columns[2].metric("동일", response.get("unchanged_count", 0), border=True)
    metric_columns[3].metric(
        "이번 배치 미관측",
        response.get("not_observed_in_batch_count", 0),
        border=True,
    )

    if response.get("not_observed_in_batch_count", 0) > 0:
        st.info(CATALOG_RECONCILIATION_NOT_OBSERVED_NOTICE)

    reject_notice = build_catalog_reconciliation_reject_notice(
        response.get("rejected_rows")
    )
    if reject_notice is not None:
        st.warning(reject_notice)

    field_change_counts = response.get("field_change_counts") or {}
    if field_change_counts:
        st.caption("필드별 변경 건수")
        st.dataframe(
            build_catalog_reconciliation_field_dataframe(field_change_counts),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("변경된 상품 필드가 없습니다.")

    items = response.get("items") or []
    if not items:
        st.info("비교할 상품이 없습니다.")
        return

    st.dataframe(
        build_catalog_reconciliation_item_dataframe(items),
        width="stretch",
        hide_index=True,
    )

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=CATALOG_RECONCILIATION_LIMIT,
        offset=st.session_state.get("catalog_reconciliation_offset", 0),
    )
    st.caption(f"상품 {current_page} / {total_pages} 페이지 · 전체 {total}개 상품")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "동기화 차이 이전",
            disabled=not has_previous,
            key="catalog_reconciliation_previous",
            type="tertiary",
        ):
            st.session_state["catalog_reconciliation_offset"] -= (
                CATALOG_RECONCILIATION_LIMIT
            )
            st.session_state["catalog_reconciliation_response"] = None
            st.rerun()
    with next_col:
        if st.button(
            "동기화 차이 다음",
            disabled=not has_next,
            key="catalog_reconciliation_next",
            type="tertiary",
        ):
            st.session_state["catalog_reconciliation_offset"] += (
                CATALOG_RECONCILIATION_LIMIT
            )
            st.session_state["catalog_reconciliation_response"] = None
            st.rerun()


def _render_etl_load_detail(api_client) -> None:
    selected_run_id = st.session_state.get("etl_load_selected_run_id")
    if selected_run_id is None:
        return

    st.subheader("적재 배치 상세")
    detail_response = _fetch_etl_load_detail(api_client, st.session_state)
    if detail_response is None:
        error = st.session_state.get("etl_load_detail_error")
        if error is not None:
            _render_etl_error(error, detail=True)
        return

    st.write(f"적재 배치 ID: {detail_response.get('etl_load_run_id', '')}")
    st.write(f"원본 파일명: {detail_response.get('source_filename', '')}")
    st.write(f"공급사 프로필: {detail_response.get('profile_name', '')}")
    st.write(f"프로필 버전: {detail_response.get('profile_version', '')}")
    st.write(f"적재 상품 수: {detail_response.get('loaded_rows', 0)}")
    st.write(f"적재 시간: {format_etl_datetime(detail_response.get('created_at'))}")
    st.write(f"실행 사용자: {format_actor_username(detail_response.get('actor_username'))}")
    total_rows = detail_response.get("total_rows")
    rejected_rows = detail_response.get("rejected_rows")
    if total_rows is not None and rejected_rows is not None:
        quality_columns = st.columns(4)
        quality_columns[0].metric("전체 입력", f"{total_rows}행", border=True)
        quality_columns[1].metric(
            "정상 적재", f"{detail_response.get('loaded_rows', 0)}행", border=True
        )
        quality_columns[2].metric("변환 거부", f"{rejected_rows}행", border=True)
        quality_columns[3].metric(
            "정상 처리율",
            format_etl_quality_rate(total_rows, detail_response.get("loaded_rows")),
            border=True,
        )
    else:
        st.info(
            "이 배치는 ETL 품질 요약 저장 기능이 추가되기 전에 생성되어 "
            "상세 품질 정보가 없습니다."
        )
    error_counts = detail_response.get("error_counts")
    if isinstance(error_counts, dict):
        if error_counts:
            st.subheader("오류 코드별 발생 건수")
            st.dataframe(
                build_etl_error_counts_dataframe(error_counts),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("변환 과정에서 거부된 행이 없습니다.")
    _render_etl_rejections(api_client, detail_response)

    synchronize_catalog_reconciliation_batch(st.session_state)
    _render_catalog_reconciliation(api_client)

    with st.expander("파일 SHA-256"):
        st.code(f"원본 파일 SHA-256: {detail_response.get('input_file_sha256', '')}")
        st.code(f"적재 파일 SHA-256: {detail_response.get('output_file_sha256', '')}")
        fingerprint = detail_response.get("profile_definition_sha256")
        st.code(f"프로필 정의 SHA-256: {fingerprint or '알 수 없음 (legacy batch)'}")
        st.caption("매핑·필수 원본 컬럼·기본값 정의의 지문이며 전체 애플리케이션 코드 hash는 아닙니다.")
        application_commit_sha = detail_response.get("application_commit_sha")
        st.code(
            "애플리케이션 Commit SHA: "
            f"{application_commit_sha or '알 수 없음 (legacy/미확인)'}"
        )
        st.caption(
            "이 값은 ETL 실행과 연결된 application Git commit을 식별합니다. "
            "전체 runtime snapshot, Docker image digest, dependency 전체 또는 "
            "로컬 미커밋 변경을 의미하지 않으므로 완전한 재현성을 보장하지 않습니다."
        )

    products = detail_response.get("products") or {}
    product_items = products.get("items") or []
    product_dataframe = build_etl_product_dataframe(product_items)
    st.dataframe(product_dataframe, width="stretch", hide_index=True)

    total = max(0, int(products.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ETL_PRODUCT_LIMIT,
        offset=st.session_state["etl_load_product_offset"],
    )
    st.caption(f"상품 {current_page} / {total_pages} 페이지 · 전체 {total}개 상품")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "상품 이전",
            disabled=not has_previous,
            key="etl_product_previous",
            type="tertiary",
        ):
            st.session_state["etl_load_product_offset"] -= ETL_PRODUCT_LIMIT
            st.session_state["etl_load_detail_response"] = None
            st.rerun()
    with next_col:
        if st.button(
            "상품 다음",
            disabled=not has_next,
            key="etl_product_next",
            type="tertiary",
        ):
            st.session_state["etl_load_product_offset"] += ETL_PRODUCT_LIMIT
            st.session_state["etl_load_detail_response"] = None
            st.rerun()


def _clear_catalog_promotion_history_detail(session_state) -> None:
    session_state["catalog_promotion_history_detail_requested"] = False
    session_state["catalog_promotion_history_detail_response"] = None
    session_state["catalog_promotion_history_detail_error"] = None
    session_state["catalog_promotion_audit_offset"] = 0
    session_state["catalog_promotion_audit_response"] = None
    session_state["catalog_promotion_audit_error"] = None
    session_state["catalog_promotion_rollback_result"] = None
    session_state["catalog_promotion_rollback_error"] = None
    session_state["catalog_promotion_rollback_confirmation"] = False


def _on_catalog_promotion_history_filter_change(session_state) -> None:
    session_state["catalog_promotion_history_offset"] = 0
    session_state["catalog_promotion_history_response"] = None
    session_state["catalog_promotion_history_error"] = None
    session_state["catalog_promotion_history_run_id"] = None
    _clear_catalog_promotion_history_detail(session_state)


def _on_catalog_promotion_history_run_change(session_state) -> None:
    _clear_catalog_promotion_history_detail(session_state)


def _fetch_catalog_promotion_history(api_client) -> dict[str, Any] | None:
    cached = st.session_state.get("catalog_promotion_history_response")
    if isinstance(cached, dict):
        return cached
    if st.session_state.get("catalog_promotion_history_error") is not None:
        return None

    params: dict[str, Any] = {
        "limit": PROMOTION_HISTORY_LIMIT,
        "offset": st.session_state["catalog_promotion_history_offset"],
    }
    selected_status = st.session_state.get("catalog_promotion_history_status")
    if selected_status and selected_status != "전체":
        params["status"] = selected_status
    try:
        response = api_client.list_catalog_promotions(**params)
        st.session_state["catalog_promotion_history_response"] = response
        st.session_state["catalog_promotion_history_error"] = None
        return response
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_history_error"] = error
        return None


def _fetch_catalog_promotion_history_detail(api_client) -> dict[str, Any] | None:
    cached = st.session_state.get("catalog_promotion_history_detail_response")
    if isinstance(cached, dict):
        return cached
    if st.session_state.get("catalog_promotion_history_detail_error") is not None:
        return None
    promotion_run_id = st.session_state.get("catalog_promotion_history_run_id")
    if promotion_run_id is None:
        return None
    try:
        response = api_client.get_catalog_promotion_detail(int(promotion_run_id))
        st.session_state["catalog_promotion_history_detail_response"] = response
        st.session_state["catalog_promotion_history_detail_error"] = None
        return response
    except (
        CatalogPromotionNotFoundError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_history_detail_error"] = error
        return None


def _fetch_catalog_promotion_audits(api_client) -> dict[str, Any] | None:
    cached = st.session_state.get("catalog_promotion_audit_response")
    if isinstance(cached, dict):
        return cached
    if st.session_state.get("catalog_promotion_audit_error") is not None:
        return None
    promotion_run_id = st.session_state.get("catalog_promotion_history_run_id")
    if promotion_run_id is None:
        return None
    try:
        response = api_client.list_catalog_promotion_audits(
            int(promotion_run_id),
            limit=PROMOTION_AUDIT_LIMIT,
            offset=st.session_state["catalog_promotion_audit_offset"],
        )
        st.session_state["catalog_promotion_audit_response"] = response
        st.session_state["catalog_promotion_audit_error"] = None
        return response
    except (
        CatalogPromotionNotFoundError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_audit_error"] = error
        return None


def _render_catalog_promotion_history_error(
    message: str,
    error: Exception,
) -> None:
    st.error(build_etl_api_error_display_message(message, error))


def _render_catalog_promotion_audits(api_client) -> None:
    st.markdown("#### 상품 변경 Audit")
    response = _fetch_catalog_promotion_audits(api_client)
    if response is None:
        error = st.session_state.get("catalog_promotion_audit_error")
        if error is not None:
            _render_catalog_promotion_history_error(
                "상품 변경 Audit을 불러오지 못했습니다.",
                error,
            )
        return

    items = response.get("items") or []
    if not items:
        st.info("이 Promotion 실행에는 상품 변경 Audit이 없습니다.")
    else:
        st.dataframe(
            build_catalog_promotion_audit_dataframe(items),
            width="stretch",
            hide_index=True,
        )

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=PROMOTION_AUDIT_LIMIT,
        offset=st.session_state["catalog_promotion_audit_offset"],
    )
    st.caption(f"Audit {current_page} / {total_pages} 페이지 · 전체 {total}건")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "Audit 이전",
            key="catalog_promotion_audit_previous",
            disabled=not has_previous,
        ):
            st.session_state["catalog_promotion_audit_offset"] -= (
                PROMOTION_AUDIT_LIMIT
            )
            st.session_state["catalog_promotion_audit_response"] = None
            st.session_state["catalog_promotion_audit_error"] = None
            st.rerun()
    with next_col:
        if st.button(
            "Audit 다음",
            key="catalog_promotion_audit_next",
            disabled=not has_next,
        ):
            st.session_state["catalog_promotion_audit_offset"] += (
                PROMOTION_AUDIT_LIMIT
            )
            st.session_state["catalog_promotion_audit_response"] = None
            st.session_state["catalog_promotion_audit_error"] = None
            st.rerun()


def _render_catalog_promotion_history_detail(api_client) -> None:
    detail = _fetch_catalog_promotion_history_detail(api_client)
    if detail is None:
        error = st.session_state.get("catalog_promotion_history_detail_error")
        if error is not None:
            _render_catalog_promotion_history_error(
                "Promotion 실행 상세를 불러오지 못했습니다.",
                error,
            )
        return

    st.markdown("#### Promotion 실행 상세")
    st.write(f"실행 ID: {detail.get('promotion_run_id', '')}")
    st.write(f"ETL 배치: {detail.get('etl_load_run_id', '')}")
    st.write(f"원본 파일명: {detail.get('source_filename', '')}")
    st.write(f"상태: {detail.get('status', '')}")
    st.write(f"실행 사용자: {format_actor_username(detail.get('actor_username'))}")
    metric_columns = st.columns(3)
    metric_columns[0].metric("신규 상품", detail.get("inserted_count", 0))
    metric_columns[1].metric("수정 상품", detail.get("updated_count", 0))
    metric_columns[2].metric("변경 없음", detail.get("unchanged_count", 0))
    failure_message = detail.get("safe_failure_message")
    if failure_message:
        st.warning(str(failure_message))
    st.caption(
        "실행 시각: "
        f"{format_etl_datetime(detail.get('started_at') or detail.get('created_at'))}"
    )
    _render_catalog_promotion_rollback(api_client, detail)
    _render_catalog_promotion_audits(api_client)


def _render_catalog_promotion_history(api_client) -> None:
    st.divider()
    st.subheader("Promotion 실행 이력")
    st.write("저장된 Promotion 실행 결과와 상품 변경 Audit을 조회합니다.")
    st.selectbox(
        "상태 필터",
        options=["전체", "applying", "succeeded", "failed", "blocked"],
        key="catalog_promotion_history_status",
        on_change=_on_catalog_promotion_history_filter_change,
        args=(st.session_state,),
    )

    response = _fetch_catalog_promotion_history(api_client)
    if response is None:
        error = st.session_state.get("catalog_promotion_history_error")
        if error is not None:
            _render_catalog_promotion_history_error(
                "Promotion 실행 이력을 불러오지 못했습니다.",
                error,
            )
        return

    items = response.get("items") or []
    if not items:
        st.info("Promotion 실행 이력이 없습니다.")
    else:
        st.dataframe(
            build_catalog_promotion_history_dataframe(items),
            width="stretch",
            hide_index=True,
        )
        run_ids = [item["promotion_run_id"] for item in items]
        labels = {
            item["promotion_run_id"]: (
                f"{item['promotion_run_id']} · {item.get('source_filename', '')} · "
                f"{item.get('status', '')}"
            )
            for item in items
        }
        if st.session_state.get("catalog_promotion_history_run_id") not in run_ids:
            st.session_state["catalog_promotion_history_run_id"] = None
            _clear_catalog_promotion_history_detail(st.session_state)
        st.selectbox(
            "Promotion 실행 선택",
            options=[None, *run_ids],
            format_func=lambda run_id: (
                "조회할 Promotion 실행을 선택하세요."
                if run_id is None
                else labels.get(run_id, str(run_id))
            ),
            key="catalog_promotion_history_run_id",
            on_change=_on_catalog_promotion_history_run_change,
            args=(st.session_state,),
        )
        if st.button(
            "Promotion 상세 조회",
            key="catalog_promotion_history_show_detail",
            disabled=st.session_state.get("catalog_promotion_history_run_id") is None,
        ):
            st.session_state["catalog_promotion_history_detail_requested"] = True
            st.session_state["catalog_promotion_history_detail_response"] = None
            st.session_state["catalog_promotion_history_detail_error"] = None
            st.session_state["catalog_promotion_audit_offset"] = 0
            st.session_state["catalog_promotion_audit_response"] = None
            st.session_state["catalog_promotion_audit_error"] = None
            st.rerun()

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=PROMOTION_HISTORY_LIMIT,
        offset=st.session_state["catalog_promotion_history_offset"],
    )
    st.caption(f"{current_page} / {total_pages} 페이지 · 전체 {total}건")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "이력 이전",
            key="catalog_promotion_history_previous",
            disabled=not has_previous,
        ):
            st.session_state["catalog_promotion_history_offset"] -= (
                PROMOTION_HISTORY_LIMIT
            )
            st.session_state["catalog_promotion_history_response"] = None
            st.session_state["catalog_promotion_history_error"] = None
            st.session_state["catalog_promotion_history_run_id"] = None
            _clear_catalog_promotion_history_detail(st.session_state)
            st.rerun()
    with next_col:
        if st.button(
            "이력 다음",
            key="catalog_promotion_history_next",
            disabled=not has_next,
        ):
            st.session_state["catalog_promotion_history_offset"] += (
                PROMOTION_HISTORY_LIMIT
            )
            st.session_state["catalog_promotion_history_response"] = None
            st.session_state["catalog_promotion_history_error"] = None
            st.session_state["catalog_promotion_history_run_id"] = None
            _clear_catalog_promotion_history_detail(st.session_state)
            st.rerun()

    if st.session_state.get("catalog_promotion_history_detail_requested"):
        _render_catalog_promotion_history_detail(api_client)

    _render_catalog_promotion_rollback_history(api_client)


def _clear_catalog_promotion_rollback_history_detail(session_state) -> None:
    session_state["catalog_promotion_rollback_history_detail_requested"] = False
    session_state["catalog_promotion_rollback_history_detail_response"] = None
    session_state["catalog_promotion_rollback_history_detail_error"] = None
    session_state["catalog_promotion_rollback_change_offset"] = 0
    session_state["catalog_promotion_rollback_change_response"] = None
    session_state["catalog_promotion_rollback_change_error"] = None


def _on_catalog_promotion_rollback_history_filter_change(session_state) -> None:
    session_state["catalog_promotion_rollback_history_offset"] = 0
    invalidate_catalog_promotion_rollback_history(session_state)
    session_state["catalog_promotion_rollback_history_run_id"] = None
    _clear_catalog_promotion_rollback_history_detail(session_state)


def _on_catalog_promotion_rollback_history_run_change(session_state) -> None:
    _clear_catalog_promotion_rollback_history_detail(session_state)


def _change_catalog_promotion_rollback_history_page(
    session_state,
    offset_delta: int,
) -> None:
    session_state["catalog_promotion_rollback_history_offset"] = max(
        0,
        session_state["catalog_promotion_rollback_history_offset"] + offset_delta,
    )
    invalidate_catalog_promotion_rollback_history(session_state)
    session_state["catalog_promotion_rollback_history_run_id"] = None
    _clear_catalog_promotion_rollback_history_detail(session_state)


def _fetch_catalog_promotion_rollback_history(api_client) -> dict[str, Any] | None:
    cached = st.session_state.get("catalog_promotion_rollback_history_response")
    if isinstance(cached, dict):
        return cached
    if st.session_state.get("catalog_promotion_rollback_history_error") is not None:
        return None

    params: dict[str, Any] = {
        "limit": ROLLBACK_HISTORY_LIMIT,
        "offset": st.session_state["catalog_promotion_rollback_history_offset"],
    }
    selected_status = st.session_state.get(
        "catalog_promotion_rollback_history_status"
    )
    if selected_status and selected_status != "전체":
        params["status"] = selected_status
    try:
        response = api_client.list_catalog_promotion_rollbacks(**params)
        st.session_state["catalog_promotion_rollback_history_response"] = response
        st.session_state["catalog_promotion_rollback_history_error"] = None
        return response
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_rollback_history_error"] = error
        return None


def _fetch_catalog_promotion_rollback_history_detail(
    api_client,
) -> dict[str, Any] | None:
    cached = st.session_state.get(
        "catalog_promotion_rollback_history_detail_response"
    )
    if isinstance(cached, dict):
        return cached
    if (
        st.session_state.get("catalog_promotion_rollback_history_detail_error")
        is not None
    ):
        return None
    rollback_run_id = st.session_state.get(
        "catalog_promotion_rollback_history_run_id"
    )
    if rollback_run_id is None:
        return None
    try:
        response = api_client.get_catalog_promotion_rollback_detail(
            int(rollback_run_id)
        )
        st.session_state[
            "catalog_promotion_rollback_history_detail_response"
        ] = response
        st.session_state["catalog_promotion_rollback_history_detail_error"] = None
        return response
    except (
        CatalogPromotionRollbackNotFoundError,
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_rollback_history_detail_error"] = error
        return None


def _fetch_catalog_promotion_rollback_changes(
    api_client,
) -> dict[str, Any] | None:
    cached = st.session_state.get("catalog_promotion_rollback_change_response")
    if isinstance(cached, dict):
        return cached
    if st.session_state.get("catalog_promotion_rollback_change_error") is not None:
        return None
    rollback_run_id = st.session_state.get(
        "catalog_promotion_rollback_history_run_id"
    )
    if rollback_run_id is None:
        return None
    try:
        response = api_client.list_catalog_promotion_rollback_changes(
            int(rollback_run_id),
            limit=ROLLBACK_CHANGE_AUDIT_LIMIT,
            offset=st.session_state["catalog_promotion_rollback_change_offset"],
        )
        st.session_state["catalog_promotion_rollback_change_response"] = response
        st.session_state["catalog_promotion_rollback_change_error"] = None
        return response
    except (
        CatalogPromotionRollbackNotFoundError,
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["catalog_promotion_rollback_change_error"] = error
        return None


def _render_catalog_promotion_rollback_history_error(
    message: str,
    error: Exception,
) -> None:
    st.error(build_etl_api_error_display_message(message, error))


def _render_catalog_promotion_rollback_changes(api_client) -> None:
    st.markdown("#### 상품 Rollback 변경 Audit")
    st.write("Rollback으로 삭제·복원된 상품의 필드별 변경 이력입니다.")
    response = _fetch_catalog_promotion_rollback_changes(api_client)
    if response is None:
        error = st.session_state.get("catalog_promotion_rollback_change_error")
        if error is not None:
            _render_catalog_promotion_rollback_history_error(
                "Rollback 상품 변경 Audit을 불러오지 못했습니다.",
                error,
            )
        return

    items = response.get("items") or []
    if not items:
        st.info("이 Rollback 실행에는 상품 변경 Audit이 없습니다.")
    else:
        st.dataframe(
            build_catalog_promotion_rollback_change_dataframe(items),
            width="stretch",
            hide_index=True,
        )

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ROLLBACK_CHANGE_AUDIT_LIMIT,
        offset=st.session_state["catalog_promotion_rollback_change_offset"],
    )
    st.caption(
        f"Change Audit {current_page} / {total_pages} 페이지 · 전체 {total}건"
    )
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "Change 이전",
            key="catalog_promotion_rollback_change_previous",
            disabled=not has_previous,
        ):
            st.session_state["catalog_promotion_rollback_change_offset"] -= (
                ROLLBACK_CHANGE_AUDIT_LIMIT
            )
            st.session_state["catalog_promotion_rollback_change_response"] = None
            st.session_state["catalog_promotion_rollback_change_error"] = None
            st.rerun()
    with next_col:
        if st.button(
            "Change 다음",
            key="catalog_promotion_rollback_change_next",
            disabled=not has_next,
        ):
            st.session_state["catalog_promotion_rollback_change_offset"] += (
                ROLLBACK_CHANGE_AUDIT_LIMIT
            )
            st.session_state["catalog_promotion_rollback_change_response"] = None
            st.session_state["catalog_promotion_rollback_change_error"] = None
            st.rerun()


def _render_catalog_promotion_rollback_history_detail(api_client) -> None:
    detail = _fetch_catalog_promotion_rollback_history_detail(api_client)
    if detail is None:
        error = st.session_state.get(
            "catalog_promotion_rollback_history_detail_error"
        )
        if error is not None:
            _render_catalog_promotion_rollback_history_error(
                "Rollback 실행 상세를 불러오지 못했습니다.",
                error,
            )
        return

    st.markdown("#### Rollback 실행 상세")
    st.write(f"Rollback ID: {detail.get('rollback_run_id', '')}")
    st.write(
        f"대상 Promotion ID: {detail.get('target_promotion_run_id', '')}"
    )
    st.write(f"상태: {detail.get('status', '')}")
    st.write(f"실행 사용자: {format_actor_username(detail.get('actor_username'))}")
    st.write(f"시작 시각: {format_etl_datetime(detail.get('started_at'))}")
    st.write(f"완료 시각: {format_etl_datetime(detail.get('completed_at'))}")
    st.write(f"생성 시각: {format_etl_datetime(detail.get('created_at'))}")

    metric_columns = st.columns(3)
    metric_columns[0].metric("복구 상품", detail.get("restored_count", 0))
    metric_columns[1].metric("삭제 상품", detail.get("deleted_count", 0))
    metric_columns[2].metric("충돌", detail.get("conflict_count", 0))

    if detail.get("status") in {"failed", "blocked"}:
        failure_code = detail.get("failure_code")
        failure_message = detail.get("safe_failure_message")
        if failure_code:
            st.warning(f"실패 코드: {failure_code}")
        if failure_message:
            st.warning(f"메시지: {failure_message}")

    preview_hash = detail.get("preview_hash")
    preview_schema_version = detail.get("preview_schema_version")
    if preview_hash or preview_schema_version:
        with st.expander("Rollback Preview 정보"):
            if preview_schema_version:
                st.write(f"Preview schema version: {preview_schema_version}")
            if preview_hash:
                st.write(f"Preview SHA-256: {preview_hash}")

    _render_catalog_promotion_rollback_changes(api_client)


def _render_catalog_promotion_rollback_history(api_client) -> None:
    st.divider()
    st.subheader("Rollback 실행 이력")
    st.write("운영 상품 반영을 되돌린 실행 기록과 결과를 확인합니다.")
    st.selectbox(
        "Rollback 상태 필터",
        options=["전체", "applying", "succeeded", "failed", "blocked"],
        key="catalog_promotion_rollback_history_status",
        on_change=_on_catalog_promotion_rollback_history_filter_change,
        args=(st.session_state,),
    )

    response = _fetch_catalog_promotion_rollback_history(api_client)
    if response is None:
        error = st.session_state.get("catalog_promotion_rollback_history_error")
        if error is not None:
            _render_catalog_promotion_rollback_history_error(
                "Rollback 실행 이력을 불러오지 못했습니다.",
                error,
            )
        return

    items = response.get("items") or []
    if not items:
        st.info("아직 Rollback 실행 이력이 없습니다.")
    else:
        st.dataframe(
            build_catalog_promotion_rollback_history_dataframe(items),
            width="stretch",
            hide_index=True,
        )
        run_ids = [item["rollback_run_id"] for item in items]
        labels = {
            item["rollback_run_id"]: build_catalog_promotion_rollback_option_label(
                item
            )
            for item in items
        }
        if (
            st.session_state.get("catalog_promotion_rollback_history_run_id")
            not in run_ids
        ):
            st.session_state["catalog_promotion_rollback_history_run_id"] = None
            _clear_catalog_promotion_rollback_history_detail(st.session_state)
        st.selectbox(
            "Rollback 실행 선택",
            options=[None, *run_ids],
            format_func=lambda run_id: (
                "조회할 Rollback 실행을 선택하세요."
                if run_id is None
                else labels.get(run_id, str(run_id))
            ),
            key="catalog_promotion_rollback_history_run_id",
            on_change=_on_catalog_promotion_rollback_history_run_change,
            args=(st.session_state,),
        )
        if st.button(
            "Rollback 상세 조회",
            key="catalog_promotion_rollback_history_show_detail",
            disabled=(
                st.session_state.get("catalog_promotion_rollback_history_run_id")
                is None
            ),
        ):
            st.session_state[
                "catalog_promotion_rollback_history_detail_requested"
            ] = True
            st.session_state[
                "catalog_promotion_rollback_history_detail_response"
            ] = None
            st.session_state[
                "catalog_promotion_rollback_history_detail_error"
            ] = None
            st.session_state["catalog_promotion_rollback_change_offset"] = 0
            st.session_state["catalog_promotion_rollback_change_response"] = None
            st.session_state["catalog_promotion_rollback_change_error"] = None
            st.rerun()

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ROLLBACK_HISTORY_LIMIT,
        offset=st.session_state["catalog_promotion_rollback_history_offset"],
    )
    st.caption(f"{current_page} / {total_pages} 페이지 · 전체 {total}건")
    previous_col, next_col = st.columns(2)
    with previous_col:
        st.button(
            "Rollback 이전",
            key="catalog_promotion_rollback_history_previous",
            disabled=not has_previous,
            on_click=_change_catalog_promotion_rollback_history_page,
            args=(st.session_state, -ROLLBACK_HISTORY_LIMIT),
        )
    with next_col:
        st.button(
            "Rollback 다음",
            key="catalog_promotion_rollback_history_next",
            disabled=not has_next,
            on_click=_change_catalog_promotion_rollback_history_page,
            args=(st.session_state, ROLLBACK_HISTORY_LIMIT),
        )

    if st.session_state.get(
        "catalog_promotion_rollback_history_detail_requested"
    ):
        _render_catalog_promotion_rollback_history_detail(api_client)


def _fetch_etl_profiles(api_client, session_state) -> list[dict[str, Any]] | None:
    cached = session_state.get("etl_web_run_profiles_response")
    if isinstance(cached, dict):
        return cached.get("items") or []
    if session_state.get("etl_web_run_profiles_error") is not None:
        return None

    try:
        response = api_client.list_etl_profiles()
        session_state["etl_web_run_profiles_response"] = response
        session_state["etl_web_run_profiles_error"] = None
        return response.get("items") or []
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
    ) as error:
        session_state["etl_web_run_profiles_error"] = error
        return None


def _invalidate_etl_profile_list_cache(session_state) -> None:
    """Forget the cached profile list so the next rerun re-reads the active set.

    비활성 오류는 목록을 받은 뒤 배포로 그 프로필이 내려간 race에서 나옵니다. 캐시를
    비워 두면 다음 rerun의 _fetch_etl_profiles()가 GET /api/v1/etl-profiles를 다시
    호출해 서버의 현재 active 목록을 받습니다.

    여기서 st.rerun()을 부르지 않습니다. 렌더링 도중 rerun을 걸면 같은 비활성 오류로
    다시 들어와 무한 rerun이 됩니다. 새로고침은 다음 상호작용 때 자연스럽게 일어납니다.
    """
    session_state["etl_web_run_profiles_response"] = None
    session_state["etl_web_run_profiles_error"] = None


def _fetch_etl_profile_detail(
    api_client,
    session_state,
    profile_id: str | None,
) -> dict[str, Any] | None:
    if not profile_id:
        return None

    if session_state.get("etl_web_run_profile_detail_id") == profile_id:
        cached = session_state.get("etl_web_run_profile_detail_response")
        if isinstance(cached, dict):
            return cached
        if session_state.get("etl_web_run_profile_detail_error") is not None:
            return None

    session_state["etl_web_run_profile_detail_id"] = profile_id
    session_state["etl_web_run_profile_detail_response"] = None
    session_state["etl_web_run_profile_detail_error"] = None
    try:
        response = api_client.get_etl_profile_detail(profile_id)
        session_state["etl_web_run_profile_detail_response"] = response
        return response
    except ETLProfileInactiveError as error:
        session_state["etl_web_run_profile_detail_error"] = error
        # 목록만 무효화합니다. detail_id는 그대로 두어야 이번 프로필의 오류가 캐시되고,
        # rerun마다 같은 409 요청을 반복하지 않습니다.
        _invalidate_etl_profile_list_cache(session_state)
        return None
    except (
        ETLProfileNotFoundError,
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
    ) as error:
        session_state["etl_web_run_profile_detail_error"] = error
        return None


def _on_etl_web_run_profile_change(session_state) -> None:
    session_state["etl_web_run_result"] = None
    session_state["etl_web_run_error"] = None
    session_state["etl_web_run_profile_detail_id"] = None
    session_state["etl_web_run_profile_detail_response"] = None
    session_state["etl_web_run_profile_detail_error"] = None


def _render_etl_profile_detail(api_client, profile_id: str | None) -> None:
    detail = _fetch_etl_profile_detail(api_client, st.session_state, profile_id)
    if detail is None:
        error = st.session_state.get("etl_web_run_profile_detail_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    ETL_INACTIVE_PROFILE_DETAIL_MESSAGE
                    if isinstance(error, ETLProfileInactiveError)
                    else "ETL 프로필 상세 정보를 불러오지 못했습니다.",
                    error,
                )
            )
        return

    st.subheader("선택한 ETL 프로필")
    st.markdown(f"프로필 이름: {detail['display_name']}")
    metadata_columns = st.columns(2)
    metadata_columns[0].metric("내부 프로필", detail["profile_name"])
    metadata_columns[1].metric("프로필 버전", detail["profile_version"])
    st.markdown("#### 필수 원본 컬럼")
    st.markdown("\n".join(f"- {column}" for column in detail["required_source_columns"]))
    st.markdown("#### 컬럼 매핑")
    st.dataframe(build_etl_profile_mapping_dataframe(detail["source_columns"]))
    st.markdown("#### 기본값")
    st.dataframe(build_etl_profile_defaults_dataframe(detail["defaults"]))


def _etl_web_run_error_message(error: Exception) -> str:
    # 없는 프로필과 비활성 프로필은 사용자가 할 일이 다릅니다(오타 수정 vs 다른 프로필
    # 선택). 두 예외는 형제 관계라 순서와 무관하지만 의미가 섞이지 않게 따로 둡니다.
    if isinstance(error, ETLProfileInactiveError):
        return ETL_INACTIVE_PROFILE_RUN_MESSAGE
    if isinstance(error, ETLUnsupportedProfileError):
        return "지원하지 않는 공급사 프로필입니다."
    if isinstance(error, ETLInvalidUploadError):
        return str(error) or "업로드한 CSV를 처리할 수 없습니다."
    if isinstance(error, CatalogGuardApiConfigurationError):
        return "ETL 실행 API 주소가 설정되지 않았습니다."
    if isinstance(error, CatalogGuardApiConnectionError):
        return "ETL 실행 서버에 연결할 수 없습니다."
    if isinstance(error, CatalogGuardApiTimeoutError):
        return "ETL 실행 서버 응답 시간이 초과되었습니다."
    return "ETL 실행 중 오류가 발생했습니다."


def _submit_etl_web_run(api_client, *, profile_id, uploaded_file) -> None:
    st.session_state["etl_web_run_in_flight"] = True
    st.session_state["etl_web_run_error"] = None
    st.session_state["etl_web_run_result"] = None
    try:
        file_bytes = uploaded_file.getvalue()
        with st.spinner("ETL을 실행하고 있습니다."):
            response = api_client.run_etl_load(
                profile_id=profile_id,
                source_filename=uploaded_file.name,
                file_content=file_bytes,
            )
        st.session_state["etl_web_run_result"] = response
        # 새 배치가 즉시 보이도록 ETL History 캐시만 무효화합니다.
        # Promotion 캐시는 이번 ETL 실행과 무관하므로 건드리지 않습니다.
        st.session_state["etl_load_list_response"] = None
        st.session_state["etl_load_initialized"] = False
        st.session_state["etl_load_offset"] = 0
    except ETLProfileInactiveError as error:
        # 목록을 받은 뒤 프로필이 내려간 race입니다. 오류만 띄우고 오래된 목록을 그대로
        # 두면 사용자가 같은 프로필을 다시 고르게 되므로 캐시를 무효화합니다.
        st.session_state["etl_web_run_error"] = error
        _invalidate_etl_profile_list_cache(st.session_state)
        st.session_state["etl_web_run_profile_detail_id"] = None
        st.session_state["etl_web_run_profile_detail_response"] = None
        st.session_state["etl_web_run_profile_detail_error"] = None
    except (
        ETLUnsupportedProfileError,
        ETLInvalidUploadError,
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.session_state["etl_web_run_error"] = error
    finally:
        st.session_state["etl_web_run_in_flight"] = False


def _render_etl_web_run(api_client) -> None:
    st.subheader("ETL 실행")
    st.write("공급사 CSV를 업로드하고 프로필을 선택해 ETL을 실행합니다.")

    profiles = _fetch_etl_profiles(api_client, st.session_state)
    if profiles is None:
        error = st.session_state.get("etl_web_run_profiles_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    "ETL 프로필 목록을 불러오지 못했습니다.", error
                )
            )
        return
    if not profiles:
        st.info("사용할 수 있는 ETL 프로필이 없습니다.")
        return

    profile_ids = [profile["id"] for profile in profiles]
    profile_labels = {profile["id"]: profile["display_name"] for profile in profiles}
    if st.session_state.get("etl_web_run_selected_profile_id") not in profile_ids:
        st.session_state["etl_web_run_selected_profile_id"] = profile_ids[0]
    st.selectbox(
        "ETL 실행 프로필",
        options=profile_ids,
        format_func=lambda profile_id: profile_labels.get(profile_id, profile_id),
        key="etl_web_run_selected_profile_id",
        on_change=_on_etl_web_run_profile_change,
        args=(st.session_state,),
    )
    _render_etl_profile_detail(
        api_client,
        st.session_state.get("etl_web_run_selected_profile_id"),
    )
    uploaded_file = st.file_uploader(
        "공급사 CSV 파일",
        type=["csv"],
        key="etl_web_run_upload_file",
    )

    in_flight = st.session_state.get("etl_web_run_in_flight") is True
    selected_profile_id = st.session_state.get("etl_web_run_selected_profile_id")
    can_run_etl = is_operator()
    if not can_run_etl:
        st.caption("ETL 실행은 운영자 권한이 필요합니다.")
    if st.button(
        "ETL 실행",
        key="etl_web_run_submit",
        type="primary",
        disabled=(
            uploaded_file is None
            or selected_profile_id is None
            or in_flight
            or not can_run_etl
        ),
    ):
        _submit_etl_web_run(
            api_client,
            profile_id=selected_profile_id,
            uploaded_file=uploaded_file,
        )
        st.rerun()

    error = st.session_state.get("etl_web_run_error")
    if error is not None:
        st.error(
            build_etl_api_error_display_message(
                _etl_web_run_error_message(error), error
            )
        )

    result = st.session_state.get("etl_web_run_result")
    if isinstance(result, dict):
        if result.get("created") is True:
            st.success(
                f"ETL 실행이 완료되었습니다. 적재 배치 ID: {result.get('etl_load_run_id')}"
            )
        else:
            st.info(
                "동일한 입력으로 이미 처리된 적재 배치입니다. "
                f"적재 배치 ID: {result.get('etl_load_run_id')}"
            )
        metric_columns = st.columns(3)
        metric_columns[0].metric(
            "전체 행", _display_nullable(result.get("total_rows")), border=True
        )
        metric_columns[1].metric("정상 적재", result.get("loaded_rows", 0), border=True)
        metric_columns[2].metric(
            "변환 거부", _display_nullable(result.get("rejected_rows")), border=True
        )
        st.caption(
            "아래 ETL 적재 이력에서 새로 생성된 배치를 선택해 상세 내용과 운영 반영을 진행하세요."
        )


def format_etl_profile_admin_runtime_state(activation: dict[str, Any] | None) -> str:
    """Describe the runtime override in words that keep three states apart.

    "override 없음"과 "명시적 비활성"을 같은 문구로 보이면 운영자가 배포 기본값을
    자기가 내린 것으로 착각하거나 그 반대로 읽습니다.
    """
    if not isinstance(activation, dict):
        return ""
    if not activation.get("runtime_override_exists"):
        return ETL_PROFILE_ADMIN_RUNTIME_NO_OVERRIDE
    runtime_version = activation.get("runtime_active_version")
    if runtime_version is None:
        return ETL_PROFILE_ADMIN_RUNTIME_INACTIVE
    return f"런타임에서 v{runtime_version} 활성으로 지정"


def format_etl_profile_admin_version(version: object) -> str:
    return ETL_PROFILE_ADMIN_NO_VERSION if version is None else f"v{version}"


def build_etl_profile_admin_activate_state(
    activation: dict[str, Any] | None,
    selected_version: str | None,
) -> tuple[bool, str]:
    """Decide whether activating the selected version would change anything.

    단순히 effective == selected로 막으면 안 됩니다. override가 없는 상태에서 배포
    기본값과 같은 버전을 고르는 것은 **의미가 다른 조작**입니다. 그 경우 배포 기본값을
    따르던 프로필이 그 버전으로 고정되어, 나중에 배포 기본값이 바뀌어도 따라가지
    않습니다. 그래서 override가 없으면 같은 버전이라도 활성화를 허용합니다.

    반대로 이미 같은 버전으로 명시적 override가 걸려 있으면 진짜 no-op입니다. 눌러도
    updated_at만 갱신되므로 막습니다.
    """
    if not isinstance(activation, dict) or not selected_version:
        return False, ""
    if (
        activation.get("runtime_override_exists")
        and activation.get("runtime_active_version") == selected_version
    ):
        return False, f"v{selected_version}은(는) 이미 런타임에서 적용 중입니다."
    if not activation.get("runtime_override_exists"):
        return True, (
            f"지금은 배포 기본값을 따릅니다. 활성화하면 v{selected_version}을(를) "
            "런타임에서 명시적으로 고정합니다."
        )
    return True, ""


def build_etl_profile_admin_reset_preview(activation: dict[str, Any] | None) -> str:
    """Say what will actually apply once the runtime override is removed.

    reset은 "정리" 버튼이 아닙니다. 명시적 비활성 override를 지우면 배포 기본값이 다시
    적용되므로, 배포 기본값이 활성이면 그 프로필은 그 자리에서 **다시 실행 가능**해집니다.
    누르기 전에 결과를 보여 주지 않으면 운영자가 정리라고 생각하고 되살립니다.
    """
    if not isinstance(activation, dict):
        return ""
    deployment_version = activation.get("deployment_active_version")
    if deployment_version is None:
        return "되돌린 뒤에도 배포 기본값이 비활성이라 이 프로필은 계속 비활성입니다."
    preview = f"되돌린 뒤 실제 적용 버전: v{deployment_version}"
    if not activation.get("is_active"):
        preview += " — 지금 비활성인 이 프로필이 다시 활성화됩니다."
    return preview


def build_etl_profile_admin_reset_success_message(
    profile_id: str,
    activation: dict[str, Any] | None,
) -> str:
    """Report the state the server actually returned, not the one we assumed.

    DELETE 응답이 reset 직후의 effective 상태를 그대로 담고 있으므로 GET을 한 번 더
    하지 않습니다. 그 사이에 다른 운영자의 변경이 끼면 방금 만든 상태를 잘못 설명합니다.
    """
    effective = (
        activation.get("effective_active_version")
        if isinstance(activation, dict)
        else None
    )
    if effective is None:
        return (
            f"{profile_id} 프로필의 런타임 설정을 제거했습니다. "
            "배포 기본값도 비활성이라 이 프로필은 계속 비활성입니다."
        )
    return (
        f"{profile_id} 프로필의 런타임 설정을 제거했습니다. "
        f"이제 배포 기본값 v{effective}을(를) 따릅니다."
    )


def build_etl_profile_admin_update_error_message(error: Exception | None) -> str:
    """Pick the headline that tells the operator what to do next.

    버전이 사라진 경우(422)는 사용자가 고칠 수 있는 상태이므로 일반 실패와 다르게
    안내합니다. 서버 message 원문은 쓰지 않습니다.
    """
    if isinstance(error, ETLProfileActivationVersionError):
        return ETL_PROFILE_ADMIN_STALE_VERSION_MESSAGE
    return "ETL 프로필 활성화 상태를 변경하지 못했습니다."


def format_etl_profile_admin_history_action(action: object) -> str:
    """Name one recorded command in the operator's words.

    reset을 "비활성화"로 옮기지 않습니다. 셋은 서로 다른 명령이고, 특히 reset은
    프로필을 **되살릴 수도** 있어 비활성화와 반대 방향의 결과를 낳을 수 있습니다.
    """
    if not isinstance(action, str):
        return ETL_PROFILE_ADMIN_HISTORY_UNKNOWN_ACTION_LABEL
    return ETL_PROFILE_ADMIN_HISTORY_ACTION_LABELS.get(
        action, ETL_PROFILE_ADMIN_HISTORY_UNKNOWN_ACTION_LABEL
    )


def build_etl_profile_admin_history_dataframe(
    items: list[dict[str, Any]],
) -> pd.DataFrame:
    """One row per recorded command, showing the state that command produced.

    "런타임 결과"와 "실제 적용 버전"을 함께 보여 줍니다. reset event는 런타임 override가
    없는 상태이지만 배포 기본값이 활성이면 실제 적용 버전이 있습니다. 한쪽만 보여 주면
    "되돌리기 = 비활성"이라는 잘못된 읽기가 생깁니다.

    런타임 결과 문구는 현재 상태 표시와 같은 helper를 씁니다. event가 그 시점의
    runtime_override_exists/runtime_active_version을 그대로 담고 있어 계산이 같고,
    두 곳의 문구가 갈라지면 같은 상태가 화면마다 다르게 보입니다.
    """
    rows = [
        {
            "시각": format_etl_datetime(item.get("created_at")),
            "동작": format_etl_profile_admin_history_action(item.get("action")),
            "런타임 결과": format_etl_profile_admin_runtime_state(item),
            "실제 적용 버전": format_etl_profile_admin_version(
                item.get("effective_active_version")
            ),
            "배포 기본 버전": format_etl_profile_admin_version(
                item.get("deployment_active_version")
            ),
            "사용자": format_actor_username(item.get("actor_username")),
        }
        for item in items
    ]
    return pd.DataFrame(rows, columns=ETL_PROFILE_ADMIN_HISTORY_DISPLAY_COLUMNS)


def _invalidate_etl_profile_admin_history(session_state) -> None:
    """Drop the cached history page so the next run re-reads it."""
    session_state["etl_profile_admin_history_profile_id"] = None
    session_state["etl_profile_admin_history_response"] = None
    session_state["etl_profile_admin_history_error"] = None


def _invalidate_etl_profile_admin_activation(session_state) -> None:
    session_state["etl_profile_admin_activation_profile_id"] = None
    session_state["etl_profile_admin_activation_response"] = None
    session_state["etl_profile_admin_activation_error"] = None


def _on_etl_profile_admin_profile_change(session_state) -> None:
    _invalidate_etl_profile_admin_activation(session_state)
    # 다른 프로필의 이력을 그 페이지 번호 그대로 이어 보면 첫 페이지가 아닌 곳에서
    # 시작하거나 빈 페이지가 보입니다. 프로필이 바뀌면 항상 최신 페이지부터입니다.
    _invalidate_etl_profile_admin_history(session_state)
    session_state["etl_profile_admin_history_offset"] = 0
    session_state["etl_profile_admin_selected_version"] = None
    session_state["etl_profile_admin_deactivate_confirmed"] = False
    session_state["etl_profile_admin_reset_confirmed"] = False
    session_state["etl_profile_admin_update_error"] = None
    session_state["etl_profile_admin_update_success"] = None


def _fetch_etl_profile_admin_profiles(api_client, session_state):
    """List every allowlisted profile, including deactivated ones.

    관리 화면은 실행 selector와 달리 비활성 프로필도 봐야 합니다. 감추면 한 번 내린
    프로필을 다시 고를 수 없어 되살릴 방법이 없어집니다.
    """
    cached = session_state.get("etl_profile_admin_profiles_response")
    if isinstance(cached, dict):
        return cached.get("items") or []
    if session_state.get("etl_profile_admin_profiles_error") is not None:
        return None

    try:
        response = api_client.list_etl_profiles(include_inactive=True)
        session_state["etl_profile_admin_profiles_response"] = response
        session_state["etl_profile_admin_profiles_error"] = None
        return response.get("items") or []
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
    ) as error:
        session_state["etl_profile_admin_profiles_error"] = error
        return None


def _fetch_etl_profile_admin_activation(api_client, session_state, profile_id):
    if not profile_id:
        return None
    if session_state.get("etl_profile_admin_activation_profile_id") == profile_id:
        cached = session_state.get("etl_profile_admin_activation_response")
        if isinstance(cached, dict):
            return cached
        if session_state.get("etl_profile_admin_activation_error") is not None:
            return None

    session_state["etl_profile_admin_activation_profile_id"] = profile_id
    session_state["etl_profile_admin_activation_response"] = None
    session_state["etl_profile_admin_activation_error"] = None
    try:
        response = api_client.get_etl_profile_activation(profile_id)
        session_state["etl_profile_admin_activation_response"] = response
        return response
    except (
        ETLProfileNotFoundError,
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
    ) as error:
        session_state["etl_profile_admin_activation_error"] = error
        return None


# 활성화·비활성화·reset이 모두 같은 오류를 낼 수 있어 한 곳에서 관리합니다. 세 경로가
# 각자 다른 목록을 들고 있으면 한쪽만 오류를 삼키는 차이가 조용히 생깁니다.
ETL_PROFILE_ACTIVATION_WRITE_ERRORS = (
    ETLProfileActivationVersionError,
    ETLProfileNotFoundError,
    CatalogGuardApiConfigurationError,
    CatalogGuardApiConnectionError,
    CatalogGuardApiTimeoutError,
    CatalogGuardApiResponseError,
    ValueError,
)


def _clear_etl_profile_admin_confirmation(session_state, key) -> None:
    """Uncheck one confirmation box without assigning to an instantiated widget key.

    Streamlit은 이번 run에서 이미 만들어진 widget의 key에 **대입**하면 예외를 냅니다.
    확인 checkbox는 실행 버튼보다 먼저 그려지므로 성공 처리는 항상 그 뒤에 오고,
    거기서 `session_state[key] = False`를 하면 화면이 예외로 끝납니다. 삭제는 허용되며
    다음 run에서 checkbox가 기본값(False)으로 다시 만들어집니다.
    """
    session_state.pop(key, None)


def _commit_etl_profile_activation_change(session_state, send, build_success_message):
    """Send one activation write, and only touch local state after the server accepted it.

    서버가 실패했는데 화면만 바뀌면 운영자가 내리지 않은 프로필을 내렸다고 믿게 됩니다.
    그래서 성공 응답을 받은 뒤에만 캐시를 비웁니다.

    활성화·비활성화·reset이 이 한 곳을 지납니다. 같은 무효화를 각자 복사하면 나중에
    한쪽만 고쳐져 관리 화면과 실행 selector가 서로 다른 상태를 보여 주게 됩니다.
    """
    session_state["etl_profile_admin_update_error"] = None
    session_state["etl_profile_admin_update_success"] = None
    try:
        response = send()
    except ETL_PROFILE_ACTIVATION_WRITE_ERRORS as error:
        session_state["etl_profile_admin_update_error"] = error
        # 상태를 새로 읽어야 사용자가 최신 available_versions로 다시 고를 수 있습니다.
        _invalidate_etl_profile_admin_activation(session_state)
        return False

    session_state["etl_profile_admin_update_success"] = build_success_message(response)
    # 성공한 조작의 확인 표시는 남기지 않습니다. 남겨 두면 다음 조작이 확인 없이
    # 버튼 한 번으로 나갑니다.
    _clear_etl_profile_admin_confirmation(
        session_state, "etl_profile_admin_deactivate_confirmed"
    )
    _clear_etl_profile_admin_confirmation(
        session_state, "etl_profile_admin_reset_confirmed"
    )
    _invalidate_etl_profile_admin_activation(session_state)
    # 방금 내린 명령도 이력의 일부입니다. 여기서 비우지 않으면 현재 상태만 갱신되고
    # 이력만 옛 화면으로 남습니다. 새 event는 최신순 첫 페이지에 오므로 함께 되돌립니다.
    _invalidate_etl_profile_admin_history(session_state)
    session_state["etl_profile_admin_history_offset"] = 0
    # 관리 목록은 비활성 프로필도 포함하므로 구성이 바뀌지 않지만, 실행 selector는
    # 활성 목록만 쓰므로 반드시 다시 읽어야 방금 내린 프로필이 사라집니다.
    session_state["etl_profile_admin_profiles_response"] = None
    session_state["etl_profile_admin_profiles_error"] = None
    _invalidate_etl_profile_list_cache(session_state)
    # 실행 화면의 프로필 상세 캐시도 함께 비웁니다. 방금 버전을 바꿨다면 그 상세가
    # 옛 버전을 가리키기 때문입니다.
    session_state["etl_web_run_profile_detail_id"] = None
    session_state["etl_web_run_profile_detail_response"] = None
    session_state["etl_web_run_profile_detail_error"] = None
    return True


def _apply_etl_profile_activation(api_client, session_state, profile_id, active_version):
    """Set the runtime active version, or deactivate with None."""
    return _commit_etl_profile_activation_change(
        session_state,
        lambda: api_client.update_etl_profile_activation(
            profile_id,
            active_version=active_version,
        ),
        lambda _response: (
            f"{profile_id} 프로필을 비활성화했습니다."
            if active_version is None
            else f"{profile_id} 프로필을 v{active_version}(으)로 활성화했습니다."
        ),
    )


def _reset_etl_profile_activation(api_client, session_state, profile_id):
    """Remove the runtime override so the deployment default applies again.

    비활성화와 다른 동작입니다. 비활성화는 "명시적 비활성" override를 만들고, reset은
    override 자체를 지웁니다. 그래서 reset은 프로필을 **되살릴 수도** 있습니다.
    """
    return _commit_etl_profile_activation_change(
        session_state,
        lambda: api_client.reset_etl_profile_activation(profile_id),
        lambda response: build_etl_profile_admin_reset_success_message(
            profile_id,
            response,
        ),
    )


def _render_etl_profile_activation_controls(api_client, activation) -> None:
    """Operator controls. Viewer sees the state above but no write controls."""
    profile_id = activation["profile_id"]
    versions = list(activation.get("available_versions") or [])

    if not is_operator():
        st.caption("ETL 프로필 활성화 상태 변경은 운영자 권한이 필요합니다.")
        return

    st.markdown("##### 활성 버전 변경")
    if st.session_state.get("etl_profile_admin_selected_version") not in versions:
        st.session_state["etl_profile_admin_selected_version"] = versions[0]
    st.selectbox(
        "활성화할 보존 버전",
        options=versions,
        format_func=lambda version: f"v{version}",
        key="etl_profile_admin_selected_version",
    )
    selected_version = st.session_state.get("etl_profile_admin_selected_version")
    can_activate, activate_note = build_etl_profile_admin_activate_state(
        activation,
        selected_version,
    )
    if activate_note:
        st.caption(activate_note)
    # disabled와 조건을 함께 봅니다. disabled는 화면 안내이고, 실제 전송 여부는
    # 조건이 정합니다. 최종 보장은 서버의 operator RBAC입니다.
    if (
        st.button(
            "선택한 버전 활성화",
            key="etl_profile_admin_activate",
            type="primary",
            disabled=not can_activate,
        )
        and can_activate
    ):
        # 성공이든 실패든 한 번 rerun합니다. 결과 메시지는 이 구획보다 위에서 그려지므로
        # 지금 화면에는 반영되지 않기 때문입니다. 버튼을 누른 뒤에만 부르므로 다음
        # rerun에서는 다시 호출되지 않아 loop가 생기지 않습니다.
        _apply_etl_profile_activation(
            api_client,
            st.session_state,
            profile_id,
            selected_version,
        )
        st.rerun()

    _render_etl_profile_deactivate_controls(api_client, activation)
    _render_etl_profile_reset_controls(api_client, activation)


def _render_etl_profile_deactivate_controls(api_client, activation) -> None:
    """Stop new ETL runs for this profile by writing an explicit inactive override."""
    st.markdown("##### 신규 ETL 실행 중단")
    if not activation.get("is_active"):
        st.caption("이미 비활성 상태입니다. 위에서 버전을 골라 다시 활성화할 수 있습니다.")
        return

    st.caption(
        "비활성화하면 이 프로필의 신규 ETL 실행이 즉시 막힙니다. "
        "과거 적재 이력과 품질·동기화 조회는 그대로 유지됩니다."
    )
    confirmed = st.checkbox(
        ETL_PROFILE_ADMIN_DEACTIVATE_CONFIRM_LABEL,
        key="etl_profile_admin_deactivate_confirmed",
    )
    # 확인 checkbox를 두 번 확인합니다. 신규 ETL을 즉시 막는 조작이라, disabled만
    # 믿고 전송하지 않습니다.
    if (
        st.button(
            "비활성화",
            key="etl_profile_admin_deactivate",
            disabled=not confirmed,
        )
        and confirmed
    ):
        _apply_etl_profile_activation(
            api_client,
            st.session_state,
            activation["profile_id"],
            None,
        )
        st.rerun()


def _render_etl_profile_reset_controls(api_client, activation) -> None:
    """Drop the runtime override so this profile follows the deployment default again.

    override가 없으면 되돌릴 설정 자체가 없으므로 버튼을 만들지 않습니다. 없는 대상을
    지우는 버튼은 사용자에게 "무언가 남아 있다"고 잘못 말합니다.

    override가 있을 때도 확인 없이 보내지 않습니다. 명시적 비활성 override를 지우면
    배포 기본값이 다시 적용되어 프로필이 **되살아날 수** 있어, 비활성화와 같은 수준의
    확인이 필요합니다.
    """
    st.markdown("##### 런타임 설정 초기화")
    if not activation.get("runtime_override_exists"):
        st.caption(ETL_PROFILE_ADMIN_NO_OVERRIDE_RESET_CAPTION)
        return

    st.caption(ETL_PROFILE_ADMIN_RESET_CAPTION)
    # 누르기 전에 결과를 보여 줍니다. reset은 정리가 아니라 상태 전환입니다.
    st.caption(build_etl_profile_admin_reset_preview(activation))
    confirmed = st.checkbox(
        ETL_PROFILE_ADMIN_RESET_CONFIRM_LABEL,
        key="etl_profile_admin_reset_confirmed",
    )
    if (
        st.button(
            ETL_PROFILE_ADMIN_RESET_BUTTON_LABEL,
            key="etl_profile_admin_reset",
            disabled=not confirmed,
        )
        and confirmed
    ):
        _reset_etl_profile_activation(
            api_client,
            st.session_state,
            activation["profile_id"],
        )
        st.rerun()


def _fetch_etl_profile_admin_history(api_client, session_state, profile_id):
    """Read one page of this profile's activation history, or None on failure.

    실패를 예외로 올려보내지 않습니다. 이력 조회가 실패했다고 해서 현재 상태 확인과
    활성화·비활성화·초기화까지 함께 사라지면, 운영자가 정작 필요한 조작을 못 하게
    됩니다. 오류는 이력 구획 안에서만 보여 줍니다.
    """
    if not profile_id:
        return None
    if session_state.get("etl_profile_admin_history_profile_id") == profile_id:
        cached = session_state.get("etl_profile_admin_history_response")
        if isinstance(cached, dict):
            return cached
        if session_state.get("etl_profile_admin_history_error") is not None:
            return None

    session_state["etl_profile_admin_history_profile_id"] = profile_id
    session_state["etl_profile_admin_history_response"] = None
    session_state["etl_profile_admin_history_error"] = None
    try:
        response = api_client.list_etl_profile_activation_history(
            profile_id,
            limit=ETL_PROFILE_ADMIN_HISTORY_LIMIT,
            offset=session_state.get("etl_profile_admin_history_offset", 0),
        )
        session_state["etl_profile_admin_history_response"] = response
        return response
    except (
        ETLProfileNotFoundError,
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        session_state["etl_profile_admin_history_error"] = error
        return None


def _render_etl_profile_activation_history(api_client, profile_id) -> None:
    """Read-only record of the successful commands operators ran on this profile.

    viewer도 봅니다. 상태를 바꿀 수 없는 사람도 "왜 지금 이렇게 되어 있는가"는 확인할
    수 있어야 합니다.

    수정·삭제 조작은 두지 않습니다. append-only 기록이고, 화면에서 지울 수 있으면
    기록이 아닙니다.
    """
    st.markdown("##### Activation 운영 이력")
    st.caption(ETL_PROFILE_ADMIN_HISTORY_CAPTION)

    response = _fetch_etl_profile_admin_history(api_client, st.session_state, profile_id)
    if response is None:
        error = st.session_state.get("etl_profile_admin_history_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    ETL_PROFILE_ADMIN_HISTORY_ERROR_MESSAGE, error
                )
            )
        return

    items = response.get("items") or []
    if not items:
        # 기록이 없는 것은 오류가 아닙니다. 이 기능 이전의 조작은 애초에 남아 있지
        # 않으므로, 실패처럼 보이게 하면 없는 문제를 찾게 만듭니다.
        st.info(ETL_PROFILE_ADMIN_HISTORY_EMPTY_MESSAGE)
    else:
        st.dataframe(
            build_etl_profile_admin_history_dataframe(items),
            width="stretch",
            hide_index=True,
        )

    total = max(0, int(response.get("total", 0)))
    current_page, total_pages, has_previous, has_next = calculate_etl_pagination(
        total=total,
        limit=ETL_PROFILE_ADMIN_HISTORY_LIMIT,
        offset=st.session_state.get("etl_profile_admin_history_offset", 0),
    )
    st.caption(f"이력 {current_page} / {total_pages} 페이지 · 전체 {total}건")
    previous_col, next_col = st.columns(2)
    with previous_col:
        if st.button(
            "이력 이전",
            key="etl_profile_admin_history_previous",
            disabled=not has_previous,
        ):
            st.session_state["etl_profile_admin_history_offset"] -= (
                ETL_PROFILE_ADMIN_HISTORY_LIMIT
            )
            _invalidate_etl_profile_admin_history(st.session_state)
            st.rerun()
    with next_col:
        if st.button(
            "이력 다음",
            key="etl_profile_admin_history_next",
            disabled=not has_next,
        ):
            st.session_state["etl_profile_admin_history_offset"] += (
                ETL_PROFILE_ADMIN_HISTORY_LIMIT
            )
            _invalidate_etl_profile_admin_history(st.session_state)
            st.rerun()


def _render_etl_profile_management(api_client) -> None:
    """Read and change which preserved version a supplier profile runs with."""
    st.divider()
    st.subheader("ETL 프로필 운영 관리")
    st.caption(
        "공급사 프로필의 현재 활성 상태를 확인하고, 보존된 버전 중 하나를 활성화하거나 "
        "신규 ETL 실행을 중단하거나, 런타임 설정을 지워 배포 기본값으로 되돌립니다. "
        "프로필 정의 자체는 여기서 바꾸지 않습니다."
    )

    profiles = _fetch_etl_profile_admin_profiles(api_client, st.session_state)
    if profiles is None:
        error = st.session_state.get("etl_profile_admin_profiles_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    "ETL 프로필 관리 목록을 불러오지 못했습니다.", error
                )
            )
        return
    if not profiles:
        st.info("등록된 ETL 프로필이 없습니다.")
        return

    profile_ids = [profile["id"] for profile in profiles]
    profile_labels = {p["id"]: p["display_name"] for p in profiles}
    if st.session_state.get("etl_profile_admin_selected_profile_id") not in profile_ids:
        st.session_state["etl_profile_admin_selected_profile_id"] = profile_ids[0]
    st.selectbox(
        "관리할 ETL 프로필",
        options=profile_ids,
        format_func=lambda profile_id: profile_labels.get(profile_id, profile_id),
        key="etl_profile_admin_selected_profile_id",
        on_change=_on_etl_profile_admin_profile_change,
        args=(st.session_state,),
    )

    success = st.session_state.get("etl_profile_admin_update_success")
    if success:
        st.success(success)
    update_error = st.session_state.get("etl_profile_admin_update_error")
    if update_error is not None:
        st.error(
            build_etl_api_error_display_message(
                build_etl_profile_admin_update_error_message(update_error),
                update_error,
            )
        )

    activation = _fetch_etl_profile_admin_activation(
        api_client,
        st.session_state,
        st.session_state.get("etl_profile_admin_selected_profile_id"),
    )
    if activation is None:
        error = st.session_state.get("etl_profile_admin_activation_error")
        if error is not None:
            st.error(
                build_etl_api_error_display_message(
                    "ETL 프로필 활성화 상태를 불러오지 못했습니다.", error
                )
            )
        return

    state_columns = st.columns(3)
    state_columns[0].metric(
        "상태",
        ETL_PROFILE_ADMIN_ACTIVE_BADGE
        if activation.get("is_active")
        else ETL_PROFILE_ADMIN_INACTIVE_BADGE,
        border=True,
    )
    state_columns[1].metric(
        "실제 적용 버전",
        format_etl_profile_admin_version(activation.get("effective_active_version")),
        border=True,
    )
    state_columns[2].metric(
        "배포 기본 버전",
        format_etl_profile_admin_version(activation.get("deployment_active_version")),
        border=True,
    )

    st.write(f"런타임 설정: {format_etl_profile_admin_runtime_state(activation)}")
    st.write(
        "사용 가능한 버전: "
        + ", ".join(f"v{v}" for v in activation.get("available_versions") or [])
    )
    if activation.get("runtime_override_exists"):
        st.write(
            f"마지막 변경 사용자: {format_actor_username(activation.get('actor_username'))}"
        )
        st.write(f"마지막 변경 시각: {format_etl_datetime(activation.get('updated_at'))}")
        st.caption(ETL_PROFILE_ADMIN_ACTOR_CAPTION)

    _render_etl_profile_activation_controls(api_client, activation)
    # 쓰기 조작 뒤에 그립니다. viewer는 위 조작 구획이 비어 있고 이력만 보게 됩니다.
    _render_etl_profile_activation_history(api_client, activation["profile_id"])


def _render_unknown_size_token_report(api_client) -> None:
    st.divider()
    st.subheader("미판정 사이즈 토큰")
    st.caption(
        "현재 운영 카탈로그에서 표준 사이즈 vocabulary에 포함되지 않은 원본 토큰의 빈도입니다. "
        "오류 판정이 아니라 vocabulary 검토용 보고서입니다."
    )
    try:
        response = api_client.list_unknown_size_tokens(limit=UNKNOWN_SIZE_TOKEN_LIMIT)
    except (
        CatalogGuardApiConfigurationError,
        CatalogGuardApiConnectionError,
        CatalogGuardApiTimeoutError,
        CatalogGuardApiResponseError,
        ValueError,
    ) as error:
        st.error(
            build_etl_api_error_display_message(
                "미판정 사이즈 토큰을 불러오지 못했습니다.", error
            )
        )
        return

    items = response.get("items") or []
    if not items:
        st.info("현재 운영 카탈로그에 미판정 사이즈 토큰이 없습니다.")
        return

    st.dataframe(
        build_unknown_size_token_dataframe(items),
        width="stretch",
        hide_index=True,
    )


def render_etl_load_history(api_client=None) -> None:
    initialize_etl_load_state()

    if api_client is None:
        try:
            api_client = get_authenticated_api_client()
        except CatalogGuardApiConfigurationError as error:
            _render_etl_error(error)
            return

    _render_etl_web_run(api_client)
    # 실행 흐름 바로 아래, 별도 구획으로 둡니다. 관리 기능이 일반 ETL 실행 화면을
    # 복잡하게 만들지 않도록 divider로 나눕니다.
    _render_etl_profile_management(api_client)
    _render_unknown_size_token_report(api_client)

    st.subheader("ETL 적재 이력")
    st.write(
        "공급사 CSV를 PostgreSQL staging에 적재한 배치와 staging 상품을 조회합니다."
    )
    _render_etl_search_controls()
    _render_etl_load_quality_summary(api_client)
    _render_etl_load_quality_trend(api_client)
    # 공급사 후보를 전용 조회에서 받으므로 아래 목록 조회의 성공 여부와 무관합니다.
    _render_etl_quality_observability(api_client)

    response = _fetch_etl_load_list(api_client, st.session_state)
    if response is None:
        error = st.session_state.get("etl_load_list_error")
        if error is not None:
            _render_etl_error(error)
        return

    items = response.get("items") or []
    if not items:
        st.info("조건에 맞는 ETL 적재 이력이 없습니다.")
        _render_catalog_promotion_history(api_client)
        return

    st.dataframe(
        build_etl_load_dataframe(items),
        width="stretch",
        hide_index=True,
    )
    run_options = [item["etl_load_run_id"] for item in items]
    option_labels = {
        item["etl_load_run_id"]: build_etl_load_option_label(item)
        for item in items
    }
    if st.session_state.get("etl_load_selected_run_id") not in run_options:
        st.session_state["etl_load_selected_run_id"] = None
    synchronize_catalog_promotion_batch(st.session_state)
    st.selectbox(
        "적재 배치 선택",
        options=[None, *run_options],
        format_func=lambda run_id: (
            "ETL 적재 이력을 선택하세요."
            if run_id is None
            else option_labels.get(run_id, str(run_id))
        ),
        key="etl_load_selected_run_id",
        on_change=_on_etl_load_selection_change,
        args=(st.session_state,),
    )
    if st.button("상세 조회", key="etl_load_show_detail"):
        reset_etl_load_detail_state(st.session_state)
        st.session_state["etl_load_detail_requested"] = True
        st.rerun()

    _render_etl_load_pagination(response)
    _render_catalog_promotion_preview(api_client)
    if st.session_state.get("etl_load_detail_requested", False):
        _render_etl_load_detail(api_client)
    _render_catalog_promotion_history(api_client)


def _rollback_ui_error_message(error: Exception) -> str:
    if isinstance(error, CatalogPromotionNotFoundError):
        return "The selected Promotion run no longer exists."
    if isinstance(error, CatalogPromotionPreviewStaleError):
        return "Rollback preview is stale. Create a new preview before executing rollback."
    return "Rollback request could not be completed."


def _render_catalog_promotion_rollback(api_client, detail: dict[str, Any]) -> None:
    if detail.get("status") != "succeeded":
        return
    st.markdown("#### Rollback")
    st.caption("Rollback restores the selected Promotion's recorded before-state. Later changes are detected as conflicts.")
    run_id = detail.get("promotion_run_id")
    if not isinstance(run_id, int):
        return
    preview_key = "catalog_promotion_rollback_preview"
    result_key = "catalog_promotion_rollback_result"
    if st.button("Rollback Preview", key=preview_key):
        try:
            st.session_state[result_key] = api_client.get_catalog_promotion_rollback_preview(run_id)
            st.session_state["catalog_promotion_rollback_error"] = None
        except Exception as error:
            st.session_state[result_key] = None
            st.session_state["catalog_promotion_rollback_error"] = error
    error = st.session_state.get("catalog_promotion_rollback_error")
    if error is not None:
        st.error(_rollback_ui_error_message(error))
        return
    preview = st.session_state.get(result_key)
    if not isinstance(preview, dict):
        return
    if preview.get("rollback_eligible") is True:
        st.success("Rollback is available.")
    else:
        st.error("Rollback is blocked.")
        for reason in preview.get("blocked_reasons") or []:
            if isinstance(reason, dict) and reason.get("message"):
                st.warning(str(reason["message"]))
    cols = st.columns(3)
    cols[0].metric("Restore", preview.get("restore_count", 0))
    cols[1].metric("Delete", preview.get("delete_count", 0))
    cols[2].metric("Conflict", preview.get("conflict_count", 0))
    items = preview.get("items") or []
    if items:
        st.dataframe(pd.DataFrame([{"Product": item.get("external_product_id"), "Action": item.get("rollback_action"), "Conflict": item.get("conflict")} for item in items]), hide_index=True, width="stretch")
    confirmed = st.checkbox("I reviewed the rollback preview and confirm execution.", key="catalog_promotion_rollback_confirmation", disabled=preview.get("rollback_eligible") is not True)
    expected_hash = preview.get("preview_hash")
    if not is_operator():
        st.caption("Rollback execution requires the operator role.")
    if st.button("Execute Rollback", key="catalog_promotion_rollback_execute", type="primary", disabled=not (confirmed and isinstance(expected_hash, str) and is_operator())):
        try:
            response = api_client.create_catalog_promotion_rollback(run_id, confirmation=True, expected_preview_hash=expected_hash)
            st.session_state[result_key] = None
            st.session_state["catalog_promotion_rollback_error"] = None
            st.success(
                f"Rollback completed. Rollback run ID: {response.get('rollback_run_id')}. "
                f"Executed by: {format_actor_username(response.get('actor_username'))}"
            )
            st.session_state["catalog_promotion_history_response"] = None
            invalidate_catalog_promotion_rollback_history(st.session_state)
        except Exception as error:
            st.error(_rollback_ui_error_message(error))
