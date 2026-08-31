# Inspection Version Lifecycle Policy

## 목적과 범위

`INSPECTION_VERSION`은 검수 규칙 결과의 의미를 구분하는 단순 증가 문자열입니다. 현재 값은 `"13"`이며, 규칙 결과가 달라지는 다음 변경에서는 `"14"`, `"15"`처럼 올립니다. 이 문서는 version model, semantic versioning, 자동 backfill 또는 cross-version comparison을 추가하지 않습니다.

판단 기준은 변경의 이름이 아니라 **같은 CSV를 다시 검사했을 때 저장되는 검수 결과의 의미가 달라질 수 있는가**입니다. 여기서 결과는 run의 요약뿐 아니라 저장되는 문제 row의 `status`, `error_field`, `reason`, `recommendation`, `risk_level`, `product_group_id`, `product_id`를 포함합니다. Run Comparison이 이 일곱 필드를 문제 identity로 사용하므로, recommendation만 바뀌어도 비교 결과가 달라집니다.

## 현재 구현 계약

| 기능 | inspection_version 사용 | 현재 version만 사용 | 과거 version 처리 |
|---|---|---|---|
| Sync Inspection | 업로드 bytes의 SHA-256과 현재 `INSPECTION_VERSION`을 precheck와 저장에 전달 | 예 | 같은 SHA·현재 version run만 재사용하고, 없으면 현재 version run을 저장 |
| Async Inspection | Worker가 Sync와 같은 현재 version을 precheck와 저장에 전달 | 예 | 같은 SHA·현재 version run만 재사용하고, 없으면 현재 version run을 저장 |
| Dedup | `(file_sha256, inspection_version)` partial unique index와 동일 조건 조회 | 요청한 version 기준 | 같은 SHA라도 version이 다르면 별도 run을 허용 |
| Inspection History | 목록 조회 조건에는 version filter가 없음 | 아니오 | 모든 저장 run을 시간·검색 조건으로 조회; 목록 응답은 version을 개별 표시하지 않음 |
| Inspection Detail | ID로 run과 결과를 조회 | 아니오 | 과거 run도 그대로 조회; detail API 응답은 version을 직접 표시하지 않음 |
| Quality Trend | Repository 집계가 `INSPECTION_VERSION`으로 필터링 | 예 | 과거 version run은 현재 Trend에 섞지 않음 |
| Run Comparison | 두 저장 run의 version equality를 검사 | 아니오 | `12 vs 12`, `13 vs 13`은 가능하고 `12 vs 13`은 422로 차단 |
| History summary CSV download | History 목록을 페이지 단위로 모아 생성 | 아니오 | 과거 run도 포함할 수 있으나 CSV에는 version 열이 없음 |

`InspectionRun.inspection_version`은 DB server default가 아니라 저장 시 애플리케이션이 명시적으로 기록합니다. `file_sha256`이 `NULL`인 migration 이전 run은 partial unique index 대상이 아니므로 신규 파일 업로드와 자동 dedup되지 않습니다.

## 언제 version을 올리는가

다음처럼 같은 입력 CSV의 저장 결과가 바뀔 수 있는 변경은 version 증가 대상입니다.

- 규칙의 추가·삭제·적용 범위 변경
- 오류와 주의의 판정 기준 또는 ERROR/WARNING 상태 변경
- 필수값, 허용 카테고리, 카테고리-상품명 일치, 가격 오류·이상치 기준 변경
- 색상·사이즈 별칭과 표준화, 중복 상품·옵션 조합, 금지어, 개인정보 탐지 규칙 변경
- 저장되는 `error_field`, `reason`, `recommendation`, `risk_level`, 식별 대상 상품, 문제 수 또는 요약이 달라질 수 있는 변경

반대로 주석·README·코드 포맷·변수명·함수 분리, 테스트 추가, 성능·로그·UI 배치 개선, API 내부 또는 Session/transaction refactoring처럼 저장 결과가 동일한 변경은 version을 올리지 않습니다. 이전 Async worker 세션 경계 정리도 이 경우입니다.

버그 수정은 이름만으로 판단하지 않습니다. 수정 뒤 같은 CSV의 저장 결과가 달라지면 version을 올리고, 결과가 동일하면 유지합니다.

### 변경 전 체크리스트

- [ ] 같은 CSV의 문제 row 또는 요약이 달라질 수 있는가?
- [ ] ERROR/WARNING, `error_field`, `reason`, `recommendation`, `risk_level` 중 하나가 달라지는가?
- [ ] 탐지되는 문제 수·대상 product/group 또는 규칙 적용 범위가 달라지는가?
- [ ] 규칙·임계값·허용값·별칭·금지어·개인정보 탐지·중복 기준을 추가, 제거, 변경했는가?

하나라도 예라면 version 증가가 기본입니다. 불확실하면 representative CSV로 이전/변경 후 `InspectionResult`와 요약을 비교해 결정합니다.

## Dedup과 재검수 예시

```text
Inspection Version 13
상품 A.csv -> 오류 3건 -> run 101 저장

검수 결과 의미가 바뀌는 규칙 변경
13 -> 14

같은 상품 A.csv 재업로드
-> SHA-256은 같아도 version이 다름
-> 새 규칙으로 검사하고 run 102를 별도 저장할 수 있음
```

Version을 올리지 않으면 같은 SHA와 version 13의 run 101이 dedup으로 재사용됩니다. 새 규칙을 배포했는데도 재검수가 생략될 수 있으므로, 결과 의미가 바뀌는 변경에서의 증가가 중요합니다.

## 과거 run과 backfill

과거 `InspectionRun`은 실행 당시의 `inspection_version`과 저장된 결과를 보존합니다. 과거 run을 현재 version으로 UPDATE하거나 migration으로 일괄 변경하지 않습니다.

CatalogGuard는 원본 CSV bytes를 DB에 저장하지 않고 `file_sha256`과 검수 결과만 저장합니다. 따라서 과거 `InspectionResult`만으로 새 규칙의 결과를 정확히 재생성할 수 없으며 자동 backfill은 지원하지 않습니다. 새 규칙으로 재검수하려면 원본 CSV를 보유한 사용자가 다시 업로드해야 하며, 이는 새 version의 별도 run을 만드는 방식입니다.

이 정책은 기존 migration이 version 없는 과거 row에 문자열 `"1"`을 기록한 사실을 바꾸지 않습니다. 그 row의 `file_sha256`은 `NULL`로 남아 있어 해시를 추측하거나 소급 dedup하지 않습니다.

## Trend와 Comparison

Quality Trend는 현재 `INSPECTION_VERSION` run만 집계합니다. 서로 다른 version을 한 그래프에 섞으면 상품 품질 변화와 검수 규칙 변화 중 무엇이 수치를 바꿨는지 구분할 수 없기 때문입니다. multi-version Trend는 현재 제공하지 않습니다.

Run Comparison은 현재 version인지가 아니라 **두 run의 저장 version이 같은지**를 확인합니다. 따라서 과거 version끼리도 `12 vs 12`는 비교할 수 있지만 `12 vs 13`은 허용하지 않습니다. 서로 다른 version의 문제 차이는 파일 변화와 규칙 변화가 섞여 의미 있는 비교가 아니기 때문입니다.

## 검증 근거

- `tests/test_inspection_persistence.py`는 같은 SHA·같은 version의 dedup, 같은 SHA·다른 version의 별도 저장, current-version Trend에서 version `"12"` 제외, version mismatch Comparison 거부를 검증합니다.
- `tests/test_api_inspections.py`와 `tests/test_inspection_tasks.py`는 Sync/Async 경로가 현재 `INSPECTION_VERSION`을 전달하는 계약을 검증합니다.
- `tests/test_catalogguard_api_client.py`는 Comparison 응답의 두 version이 다르면 API client가 거부하는 계약을 검증합니다.
