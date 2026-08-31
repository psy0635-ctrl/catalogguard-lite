# Inspection History Retention Policy

## 목적과 범위

이 문서는 `InspectionRun`과 `InspectionResult`로 저장되는 검수 이력의 현재 보관·삭제 정책을 정의한다. 이 정책은 검수 이력을 **영구 보관한다고 선언하지 않는다.** 현재 서비스에 적용할 보관 기간, 법적 근거, 고객별 계약 또는 용량 한도가 확정되지 않았으므로 임의의 숫자를 정하지 않는다.

범위는 저장된 검수 실행 이력이다. 원본 CSV bytes의 보관 정책은 포함하지 않는다. CatalogGuard Lite는 원본 CSV bytes를 DB에 저장하지 않고 파일명, SHA-256, 검수 version, 요약, issue row와 생성 actor 정보를 저장한다.

이 문서는 DELETE endpoint, soft delete, migration, background purge job을 구현하지 않는다.

## 현재 데이터 구조와 조회 계약

`inspection_runs`는 한 번의 검수 실행에 대한 부모 row이고, `inspection_results`는 그 실행에서 발견한 issue 상세 row다. `InspectionRun.results` 관계는 `cascade="all, delete-orphan"`, `passive_deletes=True`이며, `InspectionResult.inspection_run_id`는 `inspection_runs.id`를 참조하는 `ON DELETE CASCADE` FK다. 초기 migration `20260703_0001_create_inspection_tables.py`도 동일한 DB FK를 만든다.

이 cascade는 부모 row를 삭제하는 **어떤 DB 작업이 발생했을 때** 자식 orphan을 남기지 않는 참조 무결성 규칙이다. 그것만으로 사용 가능한 애플리케이션 삭제 기능이나 삭제 권한이 생기는 것은 아니다.

현재 inspection route에는 다음만 있다.

| 기능 | 현재 endpoint와 권한 |
|---|---|
| 이력 목록, 상세, Quality Trend, Run Comparison | `GET`, `require_viewer` (viewer 또는 operator) |
| 새 검수 저장 | `POST /api/v1/inspections`, `require_operator` |
| 검수 이력 삭제 | 없음 |

`list_inspections()`는 현재 row를 직접 목록화하고, 상세는 ID로 run과 result를 조회한다. Streamlit의 전체 이력 요약 CSV도 목록 API를 페이지 단위로 반복 호출해 만든다. 따라서 별도의 deleted-state filter가 없는 현재 모델에서 물리적으로 제거된 run은 목록·상세·요약 CSV 모두에서 보이지 않는다.

## 현재 보관 정책

현재 MVP의 정책은 다음과 같다.

1. 저장된 검수 이력에 대한 application DELETE API를 제공하지 않는다.
2. 기간 기반 자동 삭제(TTL), scheduler, Airflow/Celery purge job을 제공하지 않는다.
3. `deleted_at`·`deleted_by`를 사용하는 soft delete도 도입하지 않는다.
4. 운영·법적·계약상 보관 요구와 삭제 권한 모델이 확정되기 전에는 run과 연결된 result를 계속 보관한다.

이는 무기한 보관 약속이 아니다. 실제 보관 기간이나 삭제 의무가 확인되면 그 요구를 별도 설계·검토 대상으로 삼는다. 그때까지는 기록을 미리 제거해 history 조회, 동일 version 비교, 현재 version Trend 해석 및 file identity 기반 dedup의 상태를 임의로 바꾸지 않는 것이 현재 MVP의 선택이다.

## 물리 삭제가 현재 기능에 미치는 영향

현재 DB에서 `InspectionRun`을 물리 삭제하면 FK cascade로 연결된 `InspectionResult`도 함께 물리 삭제된다. 이 효과는 다음과 같다.

| 영역 | 물리 삭제 후 현재 동작 |
|---|---|
| History 목록 | 부모 row가 없으므로 목록과 total에서 제외된다. |
| Detail | ID 조회가 `None`이 되어 API는 `404`를 반환한다. |
| 전체/상세 CSV | 목록 기반 전체 요약 CSV에는 포함되지 않으며, 상세 결과도 조회할 수 없어 다시 내려받을 수 없다. |
| Quality Trend | 현재 `INSPECTION_VERSION` row를 PostgreSQL에서 합산하므로, 해당 version run을 지우면 과거 날짜의 run/issue 합계가 소급해서 달라진다. |
| Run Comparison | 비교 대상 중 하나가 없으면 service가 `None`, API가 `404`를 반환한다. 남은 run만으로 삭제된 run과의 비교를 복구할 수 없다. |
| Dedup | `(file_sha256, inspection_version)` partial unique index의 해당 row도 사라지므로, 같은 hash와 version의 다음 업로드는 기존 run을 재사용하지 않고 새 run을 만들 수 있다. |

따라서 물리 삭제는 단순 화면 정리가 아니라 조회 결과, 집계와 identity 상태를 동시에 변경한다. 특히 Trend는 immutable snapshot이 아니라 현재 DB row를 집계한 값이고, 원본 CSV bytes도 저장하지 않으므로 삭제된 결과를 정확히 재생성하거나 복구할 수 있다고 가정하면 안 된다.

## Soft delete와 자동 TTL을 지금 도입하지 않는 이유

Soft delete는 목록·상세·Trend·Comparison·CSV·dedup마다 삭제 row를 제외할지, 과거 비교를 허용할지, partial unique index를 어떻게 바꿀지 정해야 한다. 현재는 그 contract와 `deleted_at`/`deleted_by` schema가 없으므로 도입하지 않는다.

자동 TTL도 보관 기간, 대상 범위, 실행 실패·재시도, 관계 row 삭제 방식, Trend 재계산 허용 여부, 감사와 복구 절차가 정해지지 않았다. 따라서 현재는 scheduler나 purge job을 추가하지 않는다.

## 감사와 RBAC

`InspectionRun`에는 최초 생성 actor를 위한 `actor_user_id`, `actor_username`, `created_at`이 있다. 사용자가 삭제되면 actor FK만 `SET NULL`되고 username snapshot은 남는다. 이 값들은 **검수 실행을 누가 만들었는지**를 나타낼 뿐, 삭제를 누가 언제 왜 수행했는지를 기록하지 않는다.

현재 검수 이력 삭제 route와 deletion event/audit table은 없다. 미래에 삭제를 도입하려면 viewer 권한으로는 허용하지 않고, 별도의 최소 delete 권한을 정해야 한다. 또한 다음을 함께 설계·검증해야 한다.

- retention 근거와 대상 선정 기준, 승인 또는 요청 사유
- actor, 시각, 사유, 대상 run ID와 결과를 남기는 append-only deletion audit event
- hard delete/soft delete 선택과 recovery 가능 범위
- History·CSV·Trend·Comparison·dedup에 적용할 명시적 contract
- FK cascade가 result를 함께 삭제하는 사실과 실패·재시도·권한 경계의 통합 테스트

DB superuser의 직접 `DELETE`까지 막는 WORM 저장소는 현재 구현하지 않는다. 애플리케이션 차원의 삭제 기능을 추가하기 전에도 이 운영 위험은 별도로 통제해야 한다.

## 검증 근거

- `db/models.py`와 `alembic/versions/20260703_0001_create_inspection_tables.py`는 run-result cascade 계약을 함께 정의한다.
- `api/routes/inspections.py`와 `api/dependencies.py`는 현재 GET viewer/operator, POST operator 경계와 DELETE route 부재를 보여 준다.
- `db/persistence_service.py`, `db/repositories.py`, `app.py`는 목록·상세·Trend·Comparison·전체 요약 CSV가 현재 저장 row에 의존하는 경로를 보여 준다.
- `tests/test_inspection_persistence.py`의 cascade 통합 테스트는 disposable PostgreSQL에서 부모 run의 DB 물리 삭제가 연결된 result를 남기지 않는 FK contract를 확인한다. 이 테스트는 운영 데이터 삭제를 수행하지 않는다.
