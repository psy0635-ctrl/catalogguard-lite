# ETL Profile Version Lifecycle Policy

## 이 문서의 목적

ETL Profile의 CREATE / UPDATE / DELETE(Profile CRUD)를 구현하기 **전에**, 프로필 버전을 어떻게 다룰지 먼저 고정하기 위해 시작한 문서다. 처음에는 정책만 정하는 설계 gate였고(Phase 2), 그 뒤 Phase 3·4·5A·5A.1·5B.1이 실제로 구현되면서 **그 정책과 구현 결과를 함께 기록하는 문서**로 자랐다.

이 문서는 다음 세 가지를 **명확히 구분해서** 쓴다. 아직 없는 기능을 이미 있는 것처럼 쓰지 않는다.

- `[현재 구현]` — 지금 저장소 코드에 실제로 있는 동작
- `[정책 결정]` — 지켜야 할 규칙. 그 자체로는 코드를 규정하지 않고, 강제 장치는 별도 Phase에서 만든다
- `[향후 구현]` — 아직 없고, 나중에 만들 때 따를 방향

**시점 표기 규칙**: 각 Phase 절은 그 Phase 시점의 사실을 기록한다. 뒤 Phase가 그것을 바꿨으면 해당 절에 갱신 표시를 남기고, 지금 무엇이 사실인지는 가장 나중 Phase 절이 말한다. 현재 최신은 **Phase 5B.3(18장)** 이다.

| Phase | 무엇이 바뀌었나 | 절 |
| --- | --- | --- |
| Phase 2 | 정책만 확정. production code 무변경 | 4~11장 |
| Phase 3 | Published version guardrail (CI) | 12장 |
| Phase 4 | 버전별 archive + active pointer | 13장 |
| Phase 5A | 배포 기반 Activation / Deactivation | 14장 |
| Phase 5A.1 | 클라이언트/UI의 inactive 처리 | 15장 |
| Phase 5B.1 | Persistent Runtime Activation API | 16장 |
| Phase 5B.2 | Streamlit 운영 관리 화면 | 17장 |
| Phase 5B.3 | Runtime Override Reset | 18장 |

---

## 1. 용어 정리

낯선 용어는 바로 쉬운 말로 붙여 둔다.

| 용어 | 쉬운 설명 |
| --- | --- |
| Immutable(불변) | 한 번 공개(=실제 ETL 실행에 사용)된 버전의 내용을 나중에 바꾸지 않는 것 |
| Lineage(계보) | 같은 Profile이 버전별로 이어지는 줄기. `sample_fashion_vendor`의 v1 → v2 → v3 같은 흐름 |
| Version bump | 의미가 바뀌었을 때 버전 숫자를 하나 올리는 것. 기존 버전을 고치는 게 아니라 새 버전을 만드는 것 |
| Deactivate(비활성화) | 기록은 그대로 남기고, 앞으로 새로 쓰는 것만 막는 것. 삭제와 다르다 |
| Active version | 새 ETL 실행에 쓸 "지금 이 버전" 하나를 가리키는 표시 |
| Reproducibility(재현성) | 과거 배치가 "그때 어떤 규칙으로 변환됐는지"를 나중에도 알 수 있는 성질 |
| Dedup identity | 같은 배치인지 판정하는 기준 키. 이 키가 같으면 새 배치를 만들지 않는다 |
| Snapshot | 그 시점의 내용을 통째로 복사해 저장해 둔 것 |
| Fingerprint(지문) | 내용 전체를 짧은 해시 문자열 하나로 요약한 값. 내용이 바뀌면 값이 바뀐다 |

---

## 2. `[현재 구현]` 코드에서 확인한 사실

아래는 모두 현재 저장소 코드를 직접 읽고 확인한 내용이다. 추측은 없다.

### 2.1 세 가지 식별자의 역할

| 값 | 어디에 있나 | 현재 값 | 실제 역할 |
| --- | --- | --- | --- |
| `profile_id` | `etl/profile_loader.py`의 `_ETL_PROFILE_REGISTRY` key (코드 안) | `sample_fashion_vendor_v1`, `sample_marketplace_vendor_v1` | API/UI가 프로필을 고를 때 쓰는 **allowlist 식별자**. 파일 경로가 아니다 |
| `profile_name` | 프로필 JSON의 `profile_name` | `sample_fashion_vendor`, `sample_marketplace_vendor` | 프로필 **계보 이름**. `etl_load_runs.profile_name`에 기록되고 이력 검색 필터로도 쓰인다 |
| `profile_version` | 프로필 JSON의 `profile_version` | 두 프로필 모두 **`"2"`** | 실제 **변환 의미 버전**. `etl_load_runs.profile_version`에 기록되고 dedup 키의 일부다 |

`profile_id`와 파일명의 `_v1`은 **semantic version이 아니다.** 기존 API 클라이언트 호환을 위해 고정된 문자열이며, `etl/profile_loader.py` 주석과 `docs/etl_mvp.md`에도 같은 내용이 이미 적혀 있다. 실제 버전은 JSON의 `profile_version`("2")이고, 두 값이 충돌해 보이지 않도록 `display_name`에는 버전 표기를 넣지 않는다(`tests/etl/test_profile_loader.py::test_list_etl_profiles_display_names_do_not_claim_a_profile_version`이 이를 검증한다).

### 2.2 프로필 JSON에 실제로 있는 필드

`config/etl/sample_fashion_vendor/v2.json`, `config/etl/sample_marketplace_vendor/v2.json` 두 파일 모두 다음 5개 필드만 가진다.

- `profile_name`
- `profile_version`
- `source_columns` — 공급사 컬럼 → 표준 컬럼 매핑(한 원본 컬럼이 여러 표준 컬럼으로 갈 수 있다)
- `required_source_columns` — 반드시 있어야 하는 공급사 컬럼 목록
- `defaults` — 값이 비었을 때 채울 기본값

`display_name`은 **JSON에 없다.** 코드 쪽 `_ETL_PROFILE_REGISTRY`에만 있다. 이 사실은 뒤의 Policy C에서 중요하게 쓰인다.

### 2.3 `ETLLoadRun`이 저장하는 것

`db/models.py`의 `ETLLoadRun` 컬럼 전체:

`source_filename`, `profile_name`, `profile_version`, `input_file_sha256`, `output_file_sha256`, `loaded_rows`, `total_rows`, `rejected_rows`, `error_counts`, `reject_details_stored`, `rejects_file_sha256`, `initial_source_type`, `initial_source_ref`, `actor_user_id`, `actor_username`, `created_at`

- `profile_name`: `String(100)`, NOT NULL
- `profile_version`: `String(20)`, NOT NULL

### 2.4 Dedup identity

`db/models.py`에 unique index가 있다.

```text
ux_etl_load_runs_input_profile_version
  = (input_file_sha256, profile_name, profile_version)
```

`etl/db_loader.py`의 `load_standard_csv()`도 정확히 같은 세 컬럼으로 기존 배치를 조회하고, 이미 있으면 새 행을 만들지 않고 `created=False`로 기존 배치를 그대로 반환한다. `IntegrityError` 경쟁 상황에서도 기존 row를 **update하지 않는다.**

`etl/web_service.py`의 `run_web_etl()`은 변환을 먼저 다 수행한 뒤 `load_standard_csv()`를 호출하므로, dedup에 걸리면 **이번에 계산한 새 결과를 버리고** 기존 배치를 돌려준다. 즉 버전을 올리지 않으면 이미 적재한 CSV에는 새 매핑이 반영되지 않는다.

### 2.5 프로필 스냅샷 / mapping hash 저장 여부

**없음.**

`ETLLoadRun`에는 프로필 JSON 전체 snapshot도, mapping config의 hash도 저장하지 않는다. `input_file_sha256`·`output_file_sha256`·`rejects_file_sha256`은 모두 **파일 bytes**의 해시이지 프로필 내용의 해시가 아니다. `etl/pipeline.py`가 만드는 summary JSON에도 `profile_name`/`profile_version` 문자열만 들어가고 매핑 내용은 들어가지 않는다.

### 2.6 과거 버전 archive / registry 존재 여부

**Phase 2 작성 시점에는 없었다.** `config/etl/`에는 현재 버전 JSON 파일 2개만 있었고, 과거 `profile_version = "1"`의 내용은 git 이력에만 남아 있었으며(`80e8ea4`), 애플리케이션이 읽을 수 있는 archive·registry 형태로는 존재하지 않았다.

> **갱신**: 이 항목은 Phase 4에서 해소되었다. 지금은 버전별 archive와 명시적 active pointer가 있다(13장). Profile을 담는 DB 모델은 여전히 없다.

### 2.7 `profile_version` 값의 검증 수준

- `etl/profile_loader.py`의 `load_profile()`은 `_require_non_empty_text()`로 **"공백이 아닌 문자열"** 만 확인한다. 숫자인지, 순서가 증가하는지, 형식이 무엇인지는 검사하지 않는다.
- `etl/db_loader.py`는 길이 20자 초과만 거부한다(`profile_name`은 100자).
- DB 컬럼은 `String(20)`.

따라서 지금 코드는 `"2"`뿐 아니라 `"2.1.0"`, `"v3-beta"`, `"abc"` 같은 임의 문자열도 받아들인다. **이 문서는 이 validation 동작을 바꾸지 않는다.**

### 2.8 Read-only Profile Detail (직전 단계 완료분)

커밋 `973882e`("feat: add ETL profile detail")로 다음이 추가되었고, 조회 전용이다.

- `GET /api/v1/etl-profiles/{profile_id}` → `ETLProfileDetailResponse(id, display_name, profile_name, profile_version, source_columns, required_source_columns, defaults)`, 권한은 viewer 이상
- `etl.profile_loader.get_etl_profile_detail()`
- `clients/catalogguard_api.py`의 `get_etl_profile_detail()`
- Streamlit `ui/etl_load_history.py`의 `_render_etl_profile_detail()`

즉 운영자는 **지금 화면에서 프로필 매핑을 볼 수 있다.** 다만 이 화면이 보여 주는 것은 언제나 "현재 파일의 내용"이지 "과거 배치가 사용한 내용"이 아니다. 이 구분이 아래 4장 위험의 핵심이다.

### 2.9 품질 지표의 집계 기준

`db/etl_query_service.py`의 `get_etl_load_quality_summary()`와 `get_etl_load_quality_trend()`는 `profile_name`으로만 필터한다(부분 일치, 대소문자 무시). **`profile_version`은 필터 조건에 없다.** 따라서 한 계보의 여러 버전 배치가 같은 요약/추세에 함께 집계된다.

---

## 3. 지금 구조에서 무엇이 위험한가

### 3.1 문제 상황

현재 `sample_fashion_vendor`의 `profile_version`은 `"2"`다. 어떤 사람이 `config/etl/sample_fashion_vendor/v2.json`을 열어 매핑을 이렇게 바꿨다고 하자.

```text
변경 전 (v2):  "vendor_sku": ["product_group_id", "product_id"]
변경 후 (여전히 v2로 두고): "vendor_sku": "product_id"
```

`profile_version`은 `"2"` 그대로 둔다. 코드상 이 편집을 막는 장치는 **없다.** `load_profile()`은 매핑이 스키마상 유효하기만 하면 통과시킨다.

### 3.2 그래서 생기는 문제 5가지

**(1) 같은 입력 + 같은 버전인데 결과가 달라진다**

같은 공급사 CSV를 넣어도 변환 결과 CSV가 달라진다. 그런데 이력에 남는 라벨은 양쪽 다 `profile_name=sample_fashion_vendor, profile_version=2`다. 버전 문자열이 결과를 설명하지 못한다.

**(2) dedup identity의 의미가 깨진다**

dedup 키는 `(input_file_sha256, profile_name, profile_version)`이다. 이 키의 전제는 "세 값이 같으면 결과도 같다"는 것이다. 버전을 그대로 두고 매핑만 바꾸면 이 전제가 무너진다. 실제로는 결과가 달라지는데도 시스템은 "이미 적재한 배치"라고 판단해 **새 매핑을 적용한 결과를 버리고** 옛 배치를 돌려준다(2.4 참조). 사용자는 새 매핑으로 적재했다고 믿지만 DB에는 옛 결과가 남는다.

**(3) 과거 배치의 당시 매핑을 재현할 수 없다**

`ETLLoadRun`에는 스냅샷도 hash도 없다(2.5). 파일은 덮어쓰였고 archive도 없다(2.6). 남는 단서는 git 이력뿐인데, DB가 그것을 보장하는 구조가 아니다. "3개월 전 batch 41은 어떤 매핑이었나"에 시스템이 답하지 못한다.

**(4) 품질 지표 비교가 왜곡된다**

Quality Summary / Quality Trend는 `profile_name`으로만 묶는다(2.9). 매핑이 바뀌면 reject 판정 기준이 바뀌므로 rejection rate가 변한다. 그런데 추세 그래프에는 "공급사 데이터 품질이 나빠졌다"처럼 보인다. 실제 원인은 공급사가 아니라 **우리 쪽 프로필 편집**이다. 원인 오진으로 이어진다.

**(5) 운영자가 보는 "버전 2"의 의미가 시점마다 달라진다**

Profile Detail 화면(2.8)은 현재 파일 내용을 보여 준다. 운영자가 이력에서 `profile_version=2` 배치를 보고 Detail 화면의 매핑을 그 배치의 매핑이라고 이해하는 것은 자연스럽다. 그러나 in-place 편집이 있었다면 그 이해는 틀린다. **틀렸다는 사실조차 화면에 드러나지 않는다.** 이것이 가장 조용하고 위험한 실패다.

### 3.3 이미 있는 좋은 선례

`80e8ea4`("feat: align ETL required attributes with category-aware policy")에서 카테고리별 필수 속성 정책을 도입할 때, 두 샘플 프로필의 `profile_version`을 `"1"` → `"2"`로 올렸다. 커밋 메시지에 그 이유가 명시돼 있다. dedup 키가 `(input_file_sha256, profile_name, profile_version)`이므로 버전을 두지 않으면 이미 적재한 CSV에 새 정책이 적용되지 않기 때문이다. 기존 `"1"` 배치 이력은 남겼고, 파일명과 `profile_id`는 호환을 위해 유지했다.

즉 **이 프로젝트는 이미 올바른 판단을 한 번 내렸다.** 이번 문서는 그 판단을 사람의 기억이 아니라 문서화된 규칙으로 만든다.

주의할 점 하나: 이 사례에서 실제로 바뀐 것은 프로필 JSON이 아니라 **코드**(`etl/transformer.py`, `etl/db_loader.py`의 카테고리 정책)였다. 그런데도 버전을 올렸다. 변환 의미는 프로필 JSON만으로 결정되지 않고 코드와 함께 결정되기 때문이다. 이 점은 아래 정책에서 그대로 반영한다.

---

## 4. `[정책 결정]` Lifecycle 정책

각 정책이 현재 코드와 충돌하지 않는지 검토한 결과를 함께 적는다.

### Policy A — Published Version Immutable (채택)

**규칙**: 한 번이라도 실제 ETL 실행에 사용된 `(profile_name, profile_version)` 조합의 변환 의미는 수정하지 않는다. `source_columns`, `required_source_columns`, `defaults`를 바꾸지 않는다. 바꿔야 하면 **기존 버전을 고치지 말고 새 버전을 만든다.**

쉽게: v2를 고치는 게 아니라 v3를 추가한다.

**현재 코드와의 정합성**: 충돌 없음. `load_profile()`은 버전 값의 형식을 강제하지 않으므로 `"3"`으로 올리는 것만으로 정상 동작한다. dedup 키에 버전이 들어 있으므로 새 버전은 자동으로 새 배치를 만든다.

**한계(솔직하게)**: 현재 이 규칙을 **강제하는 코드는 없다.** 사람이 JSON을 편집하면 그대로 통과한다. 이 규칙을 자동으로 지켜 주는 장치가 다음 구현 후보 A(7장)다.

### Policy B — Semantic Change = Version Bump (채택)

**규칙**: 변환 결과의 의미에 영향을 주는 변경이 있으면 `profile_version`을 올린다. 대상은 다음과 같다.

- `source_columns` 매핑 변경(추가/삭제/대상 컬럼 변경)
- `required_source_columns` 변경 — 입력 검증 의미와 reject 판정이 바뀐다
- `defaults` 변경 — 빈 값일 때 채워지는 출력 값이 바뀐다
- 프로필 JSON 밖이라도, **그 프로필로 변환한 결과의 의미를 바꾸는 코드 변경** (예: `80e8ea4`의 카테고리별 필수 속성 정책)

마지막 항목이 중요하다. 변환 의미는 프로필 JSON 단독으로 결정되지 않는다. `etl/transformer.py`, `core/fashion_attribute_validator.py`, `config/settings.py`의 `CSV_TEMPLATE_COLUMNS`/`REQUIRED_FIELDS`가 함께 결정한다. 코드 쪽 변경으로 같은 입력의 결과가 달라진다면, 프로필 JSON을 한 글자도 안 고쳤더라도 버전을 올린다.

**현재 코드와의 정합성**: 충돌 없음. `80e8ea4`가 이미 이 방식으로 처리했다.

### Policy C — `display_name`은 semantic version 대상 아님 (채택, 단 조건 있음)

**규칙**: `display_name`은 UI 표시용 metadata이고 변환 결과를 바꾸지 않으므로, `"패션 공급사 샘플"` → `"패션 공급사 A"` 같은 변경으로 `profile_version`을 올리지 않는다.

**현재 registry 구조와의 관계(요청하신 검토)**: 구조상 충돌은 없지만 두 가지를 짚어야 한다.

1. `display_name`은 프로필 JSON이 아니라 **코드**(`_ETL_PROFILE_REGISTRY`)에 있다(2.2). 그래서 "JSON을 고쳤으니 버전을 올려야 하나?"라는 질문 자체가 성립하지 않는다. `display_name` 변경은 애초에 JSON을 건드리지 않는다. 대신 코드 변경 + 배포가 필요하다는 부수 효과가 있다. 향후 Profile 등록 기능을 만들 때 `display_name`을 JSON이나 DB로 옮긴다면, **그때도 이 값은 semantic 필드가 아님을 명시**해야 한다.
2. `display_name`에 버전처럼 보이는 문자열(`"샘플 v1"`, `"패션 v2"`)을 **넣지 않는다.** 넣으면 사용자가 목록에서 "v1"을 고르고 이력에는 `profile_version="2"`가 기록되는 표시 불일치가 생긴다. 이는 `80e8ea4`에서 실제로 제거한 문제이고, `tests/etl/test_profile_loader.py::test_list_etl_profiles_display_names_do_not_claim_a_profile_version`이 회귀를 막고 있다.

### Policy D — `profile_name` 변경은 새 lineage (채택)

**규칙**: `profile_name`은 하나의 계보 이름이다. `sample_fashion_vendor` → `new_fashion_vendor`처럼 이름 자체가 바뀌면 version bump가 아니라 **새 계보**로 본다. 새 계보는 `profile_version`을 처음부터(`"1"`) 시작한다.

**근거**: `profile_name`은 dedup 키의 일부이자 이력 검색·품질 집계의 기준이다(2.4, 2.9). 이름이 바뀌면 과거 배치는 옛 이름으로만 검색되고 품질 추세도 갈라진다. 즉 이름 변경은 이미 시스템 안에서 "다른 계보"처럼 동작한다. 정책이 그 실제 동작을 따라가는 것이 안전하다.

**주의**: 기존 계보 이름을 새 이름으로 **소급 변경(rename)하지 않는다.** 과거 `etl_load_runs` 행의 `profile_name`을 바꾸면 그 배치가 실제로 어떤 프로필로 만들어졌는지에 대한 기록이 오염된다.

### Policy E — `profile_id`는 API identifier (채택)

**규칙**: `_v1`이 붙은 `profile_id`는 semantic version이 아니다. 기존 client 호환 때문에 **이번 단계에서 rename하지 않는다.** 문서·화면·코드에서 세 값을 항상 구분해 쓴다.

```text
profile_id       = API/UI에서 선택하는 allowlist 식별자   (예: sample_fashion_vendor_v1)
profile_name     = Profile 계보 이름                      (예: sample_fashion_vendor)
profile_version  = 실제 ETL 변환 의미 버전                (예: "2")
```

**현재 코드와의 정합성**: 충돌 없음. 이미 이렇게 동작하며 `etl/profile_loader.py` 주석과 `docs/etl_mvp.md`에도 같은 내용이 있다.

**향후 주의**: 새 프로필을 추가할 때 새 `profile_id`에 `_v1` 같은 버전형 접미사를 붙이지 않는 편이 좋다. 지금의 `_v1`은 이미 굳어진 호환 부채이지 따라야 할 관례가 아니다.

### Policy F — Historical Version Preservation (채택, 대부분 `[향후 구현]`)

**규칙**: 한 번 ETL에 사용된 프로필 버전의 내용은 나중에 물리적으로 덮어쓰거나 삭제하지 않는다. 목표 구조는 다음과 같다.

```text
sample_fashion_vendor
 ├─ v1  archived
 ├─ v2  archived
 └─ v3  active
```

**현재 상태(솔직하게)**: 이런 archive 구조는 **지금 없다.** 현재 `config/etl/`에는 현재 버전 파일 하나씩만 있고, v1의 내용은 git 이력에만 남아 있다(2.6). 위 그림은 `[향후 구현]` 방향이지 현재 동작이 아니다.

**지금 당장 지킬 수 있는 최소한**: 프로필 JSON 파일을 **삭제하지 않는다.** 새 버전을 만들 때도 옛 내용을 git 이력에서 되찾을 수 있도록 커밋 메시지에 버전 변경 사실과 이유를 남긴다(`80e8ea4`가 좋은 예다).

### Policy G — Delete 대신 Deactivate (채택, `[향후 구현]`)

**규칙**: 향후 Profile CRUD의 DELETE는 파일/DB row의 실제 제거를 기본 동작으로 삼지 않는다. `active = false` 같은 비활성화를 기본으로 한다.

**근거**: 과거 `etl_load_runs` 행이 `(profile_name, profile_version)`으로 그 버전을 참조한다. 원본을 지우면 이력이 가리키는 대상이 사라져, 3.2의 (3)(5) 문제가 영구화된다.

**현재 상태**: Profile을 담는 DB 모델 자체가 없으므로 이번 단계에서 구현하지 않는다. DELETE API도 없다(현재 프로필 관련 API는 목록·상세 조회 2개뿐이다).

> **갱신(Phase 5A)**: 비활성 상태 자체는 이제 코드에 있다. `active_version = None`이 Deactivate이며, `versions`의 archive는 그대로 남는다(14장).
>
> **갱신(Phase 5B.1)**: 이 값을 바꾸는 API가 생겼다. `PUT /api/v1/etl-profiles/{profile_id}/activation`에 `active_version: null`을 보내면 배포 없이 비활성화된다(16장). DELETE API는 여전히 없다 — Policy G대로 삭제가 아니라 비활성이 기본 동작이기 때문이다.
>
> **갱신(Phase 5B.3)**: 같은 경로에 `DELETE`가 생겼다. 다만 이것은 **프로필 삭제가 아니라 runtime override row 삭제**이며, 지운 결과는 "없어짐"이 아니라 "배포 기본값 복귀"다. 프로필도 archive도 과거 배치도 그대로 남으므로 Policy G는 그대로다(18장).

### Policy H — Active Version (채택, `[향후 구현]`, 단 자동 추론 금지)

**규칙**: 한 `profile_name`에 여러 버전이 생기면, 신규 ETL 실행에 쓸 버전을 **명시적으로** 지정한다. **"가장 큰 숫자 = active"로 자동 추론하지 않는다.**

**자동 추론을 쓰지 않는 이유**:

1. `profile_version`은 임의 문자열을 허용한다(2.7). `"10"`과 `"9"`를 문자열로 비교하면 `"10"`이 더 작다. `"v3-beta"` 같은 값은 비교 자체가 정의되지 않는다.
2. 새 버전을 커밋했지만 아직 검증 전인 상태가 있을 수 있다. "가장 큰 것이 자동으로 실행된다"면 준비되지 않은 버전이 곧바로 운영 실행에 들어간다.
3. 문제가 생겼을 때 이전 버전으로 되돌리려면 "더 큰 번호"를 새로 만들어야 하는데, 이는 내용상 롤백인 것을 버전 진행처럼 위장한다.

**더 안전한 방식**: 명시적 registry pointer. 사실 현재 구조가 이미 원시적인 형태의 pointer다. `_ETL_PROFILE_REGISTRY[profile_id]["filename"]`이 "지금 쓸 파일"을 가리킨다. 향후에는 이 pointer가 버전을 직접 가리키게 확장하면 된다.

```text
[향후 구현 방향]
registry: sample_fashion_vendor_v1  ->  active_version: "3"
archive:  v1.json, v2.json, v3.json  (모두 보존)
```

---

## 5. `[정책 결정]` Version bump 판정표

현재 프로필 구조에 실제로 있는 필드만 표에 넣는다.

| 변경 | Version bump | 이유 |
| --- | --- | --- |
| `source_columns` 매핑 변경 | **필요** | 같은 입력의 변환 결과가 달라진다 |
| `required_source_columns` 변경 | **필요** | 입력 검증과 reject 판정 의미가 달라진다 |
| `defaults` 변경 | **필요** | 빈 값일 때 출력되는 값이 달라진다 |
| 변환 의미를 바꾸는 코드 변경 (transformer, 카테고리 필수 속성 정책 등) | **필요** | JSON이 그대로여도 같은 입력의 결과가 달라진다 (`80e8ea4` 선례) |
| `profile_name` 변경 | **새 profile 계보 권장** | 계보 자체가 바뀐다. bump가 아니다 (Policy D) |
| `display_name` 변경 | 불필요 | UI 표시만 바뀌고 변환에 영향이 없다. 애초에 JSON 밖에 있다 (Policy C) |
| 설명 문서·주석 수정 | 불필요 | 변환에 영향이 없다 |
| JSON 키 순서·들여쓰기 같은 formatting | 불필요 | 파싱 결과가 동일하다 |

---

## 6. `[정책 결정]` Version 형식

**결정: 단순 증가 정수 문자열(`"1"`, `"2"`, `"3"`)을 계속 쓴다. SemVer(`2.1.0`)는 이번 MVP에서 도입하지 않는다.**

근거:

- 현재 프로필은 2개이고 버전은 각각 `"2"` 하나뿐이다. SemVer의 major/minor/patch 구분이 표현할 만한 복잡성이 아직 없다.
- 이 프로젝트에서 프로필 변경은 사실상 전부 "결과가 달라지는 변경"이다. Policy B의 bump 대상 목록이 곧 major 변경에 해당하므로, minor/patch 자리는 늘 `0`으로 남을 가능성이 높다. 의미 없는 자릿수는 오히려 판단을 흐린다.
- `etl_load_runs.profile_version`은 `String(20)`이라 형식 변경이 스키마 변경을 부르지는 않지만, 형식이 섞이면(`"2"`와 `"2.0.0"`이 공존) dedup 키가 다른 값으로 취급되어 같은 입력이 두 배치로 갈라진다.
- 유지보수 난이도. 정수 하나는 규칙 설명이 한 줄로 끝난다.

`[현재 구현]` 다시 확인: 코드는 형식을 강제하지 않는다(2.7). `"2.1.0"`도 `"abc"`도 통과한다. 즉 위 결정은 **규약(convention)이며 코드가 막아 주는 제약이 아니다.** 이번 문서 작업에서 validation 동작은 바꾸지 않았다.

---

## 7. `[현재 구현]` 재현성이 지금 어디까지 가능한가

"재현성"을 쉬운 말로 정의하면 이렇다.

> 과거 배치가 `profile_name = sample_fashion_vendor`, `profile_version = 2`를 기록했다면, 나중에도 "그때 v2가 어떤 매핑이었는지"를 알 수 있어야 한다.

현재 도달한 수준을 과장하지 않고 나누면 다음과 같다.

| 질문 | 지금 답할 수 있나 | 근거 |
| --- | --- | --- |
| 이 배치는 어떤 프로필 계보를 썼나 | **가능** | `etl_load_runs.profile_name` |
| 이 배치는 어떤 버전을 썼나 | **가능** | `etl_load_runs.profile_version` |
| 이 배치의 입력 파일이 무엇이었나(동일성 확인) | **가능** | `input_file_sha256` (단, 원본 bytes는 보존하지 않음) |
| 이 배치의 출력 CSV가 무엇이었나(동일성 확인) | **가능** | `output_file_sha256` |
| 그 버전의 **당시 매핑 내용**이 무엇이었나 | **DB만으로는 불가능** | 스냅샷·hash 미저장(2.5), archive 없음(2.6) |
| 그 버전이 그 뒤에 수정되지 않았음을 증명 | **불가능** | in-place 편집을 막거나 감지하는 장치 없음 |

정확한 현재 상태 서술은 다음 한 문장이다.

> **어떤 버전을 사용했는지는 알 수 있지만, 그 버전의 당시 정확한 JSON 내용이 영구 보존된다고 DB 자체가 보장하지는 않는다.**

git 이력에 과거 내용이 남는 것은 사실이지만, 그것은 개발 저장소의 성질이지 애플리케이션이 제공하는 보장이 아니다. 저장소를 볼 수 없는 운영자는 답을 얻지 못한다.

---

## 8. `[향후 구현]` 구조 옵션 비교

### Option A — 현재 방식 유지 (config JSON + code allowlist)

프로필 JSON 파일 하나 + 코드 registry. 버전 관리는 사람이 규약으로 지킨다.

- **장점**: 추가 작업 없음. 구조가 단순하고 읽기 쉽다. 프로필 변경이 코드 리뷰를 거친다(권한 통제가 자연스럽다).
- **단점**: Policy A를 강제하지 못한다. 과거 버전을 애플리케이션이 읽을 수 없다. 3.2의 위험이 그대로 남는다.
- **구현 복잡도**: 없음(0)
- **MVP 적합성**: 지금 동작 중이므로 적합하지만, 위험이 문서로만 관리된다.
- **확장성**: 낮음. 프로필이 늘고 버전이 쌓이면 관리가 사람 기억에 의존한다.

### Option B — 버전별 immutable JSON archive + active registry

버전마다 별도 파일을 두고, registry가 "지금 쓸 버전"을 가리킨다.

```text
config/etl/sample_fashion_vendor/
  v1.json   (보존, 수정 금지)
  v2.json   (보존, 수정 금지)
  v3.json   (보존, 수정 금지)
registry: sample_fashion_vendor_v1 -> active_version "3"
```

- **장점**: Policy A·F·H를 구조 자체로 표현한다. 과거 버전을 애플리케이션이 읽을 수 있어 재현성이 실제로 생긴다. 파일 기반이라 git diff로 변경이 그대로 드러난다. allowlist 보안 모델(`get_profile_path()`의 경로 검증)을 그대로 유지할 수 있다.
- **단점**: `get_profile_path()`와 registry 구조를 바꿔야 한다. 파일이 계속 늘어난다. active pointer를 코드에 두면 활성 버전 전환에 배포가 필요하다. → 마지막 항목은 Phase 5B.1이 해소했다. archive와 registry는 그대로 두고 activation 상태만 DB로 분리해, 전환에 배포가 필요 없어졌다(16장).
- **구현 복잡도**: 중간. DB 마이그레이션은 필요 없다.
- **MVP 적합성**: 좋음. 현재 구조의 자연스러운 확장이다.
- **확장성**: 좋음. 나중에 Option C로 옮길 때도 archive가 그대로 이관 대상이 된다.

### Option C — Profile / ProfileVersion DB 테이블

프로필과 버전을 DB로 옮기고 CRUD API를 붙인다.

- **장점**: 화면에서 프로필을 만들고 활성화할 수 있다. `active` 플래그, 작성자, 시각 같은 메타데이터를 자연스럽게 갖는다. `etl_load_runs`에서 FK로 버전을 참조할 수 있다.
- **단점**: 가장 큰 변경이다. 테이블 2개 + Alembic migration + CRUD API + RBAC + UI + 검증. 사용자가 매핑을 직접 입력하게 되므로 지금 코드 리뷰가 담당하던 안전장치를 애플리케이션 검증으로 전부 대체해야 한다. 잘못된 프로필이 곧바로 운영 실행에 들어갈 수 있는 새 위험이 생긴다. 프로필 정의가 git 밖으로 나가 코드 리뷰 대상에서 빠진다.
- **구현 복잡도**: 높음.
- **MVP 적합성**: 낮음. 프로필이 2개뿐인 지금 단계에 비해 과하다.
- **확장성**: 가장 높음. 운영자가 직접 공급사를 늘리는 단계가 되면 결국 필요하다.

### 추천

**현재 단계 목표 구조로는 Option B를 추천한다.** 다만 지금 당장 B를 통째로 만들자는 뜻은 아니다(로드맵 9장, 다음 구현 10장 참고).

이유:

- 지금 가장 큰 위험은 "프로필을 만들 수 없다"가 아니라 **"이미 쓴 버전이 조용히 바뀔 수 있다"**(3.2)이다. Option B는 이 위험을 정면으로 해결하지만 Option C는 이 위험을 해결하면서 새 위험(무검증 사용자 입력)을 추가한다.
- 현재 프로필은 2개다. 프로필을 늘리는 기능보다 있는 프로필을 신뢰할 수 있게 만드는 것이 먼저다.
- 포트폴리오 관점에서도 "DB CRUD를 만들었다"보다 **"불변성과 재현성 문제를 먼저 식별하고, 가장 작은 안전장치부터 넣었다"**가 설명하기에 훨씬 강한 이야기다. 실제로 이 판단은 `80e8ea4`에서 한 번 내렸던 판단과 일관된다.
- Option B는 Option C로 가는 길을 막지 않는다. archive된 버전 JSON은 나중에 `profile_versions` 테이블의 초기 데이터가 된다.

---

## 9. `[향후 구현]` 단계별 로드맵

| Phase | 내용 | 상태 |
| --- | --- | --- |
| Phase 1 | Read-only Profile Detail (`GET /api/v1/etl-profiles/{profile_id}`, 클라이언트, Streamlit 표시) | **완료** (`973882e`) |
| Phase 2 | Lifecycle Policy 확정 — 이 문서 | **이번 작업** |
| Phase 3 | Published version guardrail — 이미 공개된 `(profile_name, profile_version)`의 매핑이 바뀌면 CI에서 실패시킨다 | **완료** (12장) |
| Phase 4 | Versioned archive + active pointer — 버전별 JSON 보존, registry가 활성 버전을 명시 (Option B) | **완료** (13장) |
| Phase 5A | Deployment-based Activation / Deactivation — `active_version`이 버전 문자열 또는 `None`. `None`이면 신규 ETL 실행만 막는다 | **완료** (14장) |
| Phase 5A.1 | 클라이언트/UI의 inactive 처리 — Python client가 `inactive_profile`을 전용 예외로 매핑하고 Streamlit이 원인을 안내한다 | **완료** (15장) |
| Phase 5B.1 | Persistent Runtime Activation API — activation을 바꾸는 API·권한·DB 지속 상태 (16장) | **완료** |
| Phase 5B.2 | Streamlit Admin UI — 활성 버전 선택·활성화·비활성화 화면 (17장) | **완료** |
| Phase 5B.3 | Runtime Override Reset — runtime override를 지워 배포 기본값으로 되돌린다 (18장) | **완료** |
| Phase 6 | 필요할 때만 DB-backed Profile / ProfileVersion (Option C) | 조건부 |

Phase 4가 끝나기 전에는 새 프로필 **등록** 기능을 만들지 않는다. 등록을 먼저 만들면 보존 구조 없이 프로필 수만 늘어 3.2의 위험이 프로필 수만큼 곱해진다.

Full CRUD는 로드맵의 마지막이며, 그마저도 조건부다. 프로필이 계속 2~3개 수준이면 Option C는 필요하지 않을 수 있다.

---

## 10. `[향후 구현]` 다음 실제 구현 후보 비교

| 기준 | A. Immutable version guardrail | B. Versioned profile registration | C. DB-backed Profile/ProfileVersion |
| --- | --- | --- | --- |
| 구현 난이도 | 낮음 (테스트 + 고정 기록 파일) | 중간 (registry/경로 구조 변경) | 높음 (테이블 2개 + migration + CRUD API + RBAC + UI) |
| 현재 위험 감소 | **큼** — 3.2의 (1)(2)(5)를 직접 차단 | 큼 — (3)까지 해결 | 큼, 단 새 위험 추가 |
| 실제 사용자 가치 | 간접적(사고 예방) | 중간(과거 버전 조회 가능) | 직접적(프로필 추가 가능) |
| 포트폴리오 가치 | **높음** — 문제 식별 → 최소 안전장치 서사 | 높음 | 중간 (흔한 CRUD) |
| 기존 구조 변경량 | **거의 없음** (production code 무변경 가능) | 중간 | 큼 |
| 되돌리기 쉬움 | 매우 쉬움 | 보통 | 어려움 |

### 최종 추천: **A. Immutable version guardrail**

현재 단계에서는 **가장 작은 안전장치를 먼저** 넣는다.

구체적 형태(다음 단계에서 설계·구현할 내용이며, 이번 문서에서는 만들지 않았다):

- 공개된 각 `(profile_name, profile_version)`에 대해 **semantic 필드만**(`source_columns`, `required_source_columns`, `defaults`) 정규화해 fingerprint(해시)를 계산하고, 그 값을 저장소에 고정 기록으로 남긴다.
- 테스트가 현재 프로필 JSON에서 fingerprint를 다시 계산해 고정 기록과 비교한다. 다르면 실패하고, 실패 메시지가 "매핑을 바꿨다면 `profile_version`을 올리세요"라고 알려 준다.
- 정당한 bump는 **기존 기록을 수정하는 것이 아니라 새 항목을 추가**하는 방식으로만 반영한다. 기존 항목을 지우거나 고치는 변경은 리뷰에서 걸러야 할 신호다.

이 방식의 장점:

- production code를 바꾸지 않고도 Policy A와 B를 강제할 수 있다. 런타임 동작·API 계약·DB 스키마가 그대로다.
- 고정 기록 파일 자체가 **가장 값싼 형태의 archive**다. 매핑 원문은 아니지만, "당시 v2의 지문"이 남으므로 이후 Phase 4에서 실제 archive로 확장할 때 기준점이 된다.

이 방식의 한계(미리 밝혀 둔다):

- 저장소 안의 프로필 JSON만 검사한다. `etl/transformer.py`나 카테고리 정책 같은 **코드 쪽 의미 변경은 자동으로 감지하지 못한다.** 그 판단은 여전히 사람 몫이며, `80e8ea4`처럼 리뷰에서 짚어야 한다.
- 런타임 강제가 아니라 CI 검사다. 이는 의도된 선택이다. 이 단계에서 production 동작을 바꾸지 않기 위해서다.

---

## 11. `[Phase 2 시점]` 정책 확정 단계가 바꾸지 않은 것

> 아래는 **Phase 2(정책 확정) 시점**의 기록이다. 이후 Phase들은 실제로 코드와 스키마를 바꿨으므로, 지금의 사실은 각 Phase 절을 봐야 한다.

- production code 변경 없음: `etl/*`, `api/*`, `clients/*`, `ui/*`, `db/*`, `config/etl/*.json` 모두 그대로 → 이후 Phase 4가 `profile_loader`와 archive 구조를, Phase 5A가 실행 차단을, Phase 5B.1이 API·DB 상태를 바꿨다
- `INSPECTION_VERSION = "13"` 유지 → **지금도 유지된다**
- 두 샘플 프로필의 `profile_version = "2"` 유지 → **지금도 유지된다**
- Alembic head `20260813_0013` 유지, DB 스키마·migration 변경 없음 → Phase 5B.1이 `20260822_0014`를 추가했다(16장)
- 의존성·GitHub Actions workflow 변경 없음 → **지금도 유지된다**
- `profile_version` validation 동작 변경 없음(임의 문자열 허용 상태 그대로) → **지금도 유지된다**. 다만 activation API는 registry `versions`에 있는 값만 활성화할 수 있게 따로 검증한다(16.3)

Phase 2는 **정책을 고정하는 설계 gate**였고, 여기서 정한 규칙을 실제로 강제하는 장치는 Phase 3에서 만들었다(12장).

---

## 12. `[현재 구현]` Phase 3 — Published version guardrail

Policy A·B를 사람의 기억이 아니라 테스트로 강제한다. **production 동작은 바꾸지 않는다.**

| 항목 | 값 |
| --- | --- |
| baseline 파일 | `tests/fixtures/etl/profile_fingerprints.json` |
| baseline 구조 | `profile_name` → `profile_version` → fingerprint |
| guardrail 테스트 | `tests/etl/test_profile_version_guardrail.py` |
| fingerprint 대상 | `source_columns`, `required_source_columns`, `defaults` |
| 알고리즘 | canonical JSON(UTF-8)의 SHA-256, 64자리 lowercase hex |
| 실행 | 기존 `pytest`에 포함(별도 CI job 없음) |

fingerprint는 `load_profile()`이 검증·정규화한 `ETLProfile`에서 계산한다. guardrail이 JSON을 다시 해석하지 않으므로 검증 기준은 여전히 loader 한 곳뿐이다. `profile_id`, `display_name`, 파일명, 경로는 payload에 넣지 않고, `profile_name`/`profile_version`은 payload가 아니라 기록을 찾는 key로만 쓴다.

정규화 기준은 "보기 좋게 전부 정렬"이 아니라 **의미가 없다고 확인한 것만 정렬**이다.

- `source_columns`의 dict 순서와 `defaults`의 key 순서는 정렬한다. `_validate_mapping()`이 하나의 표준 컬럼에 두 공급사 컬럼이 매핑되는 것을 막으므로, 어떤 순서로 채워도 같은 표준 행이 나온다.
- `required_source_columns`의 순서와 한 source의 target 순서는 **보존한다.** 특히 `required_source_columns` 순서는 `transform_rows()`가 만드는 `MISSING_SOURCE_VALUE` 오류 배열 순서가 되고, 그 배열이 reject CSV와 `etl_rejected_rows.errors`에 그대로 저장되므로 실제 출력에 드러난다.

동작:

- 공개된 버전의 매핑이 바뀌면 → 실패. 메시지가 `profile_name`/`profile_version`과 "기존 버전을 고치지 말고 새 버전을 추가하라"를 알려 준다.
- `profile_version`을 올렸는데 새 기록을 추가하지 않으면 → 실패. 기존 기록을 덮어써서 해결하도록 유도하지 않는다.
- 과거 버전 기록은 남아 있어도 된다. baseline은 append-only로 자라며, 현재 allowlist와 개수가 같을 것을 요구하지 않는다.

**한계(숨기지 않는다)**:

- 프로필 JSON과 baseline 해시를 **함께** 고쳐 버리면 pytest만으로는 막지 못한다. 이 경우는 PR diff와 코드 리뷰가 막는다. 기존 기록의 수정·삭제는 리뷰에서 걸러야 할 신호다.
- `etl/transformer.py`나 카테고리 정책 같은 **코드 쪽 의미 변경은 감지하지 못한다.** Policy B의 그 항목은 여전히 사람의 판단이다.
- 런타임 강제가 아니라 CI 검사다. 실행 중인 서버가 바뀐 프로필을 거부하지는 않는다.
- Phase 4의 실제 버전별 JSON archive는 아직 없다. 지금 남는 것은 매핑 원문이 아니라 지문뿐이다.

---

## 13. `[현재 구현]` Phase 4 — Versioned archive + active pointer

8장 Option B를 구현했다. 과거 정의를 파일로 보존하고, 신규 실행에 쓸 버전은 registry가 명시한다.

### 13.1 디렉터리 구조

```text
config/etl/
  sample_fashion_vendor/
    v1.json      (보존, 수정 금지)
    v2.json      (현재 active)
  sample_marketplace_vendor/
    v1.json      (보존, 수정 금지)
    v2.json      (현재 active)
```

기존 flat 파일(`config/etl/sample_fashion_vendor_v1.json` 등)은 **삭제했다.** 같은 정의를 두 곳에 두면 한쪽만 수정되어 서로 달라질 수 있기 때문이다. 호환용 symlink도 두지 않았다(Windows 환경 고려).

### 13.2 Registry

`etl/profile_loader.py`의 `_ETL_PROFILE_REGISTRY`가 다음을 가진다.

| key | 의미 |
| --- | --- |
| `display_name` | UI 표시용. semantic 필드가 아니다 (Policy C) |
| `profile_name` | 계보 이름 (Policy D) |
| `active_version` | 신규 ETL 실행에 쓸 버전 하나 |
| `versions` | 버전 → archive 파일 상대 경로 |

현재 두 profile 모두 `active_version = "2"`다. v1을 archive에 넣었다고 active가 바뀌지 않는다.

**active version은 명시적 pointer로만 정한다** (Policy H). `max()`·정렬·mtime·파일명으로 추론하지 않는다. `profile_version`이 임의 문자열을 허용해 크기 비교가 성립하지 않고(`"10"` < `"9"`), 아직 검증하지 않은 버전이 파일 추가만으로 운영 실행에 들어가면 안 되기 때문이다. `tests/etl/test_profile_version_archive.py::test_active_version_is_not_inferred_from_the_largest_version`이 `versions`에 `"10"`이 있어도 active `"2"`가 선택되는 것을 고정한다.

### 13.3 경로 해석과 안전성

- `get_profile_path(profile_id)` — **active version** 파일 경로. 기존 호출자(`run_web_etl()` 등)의 계약이 그대로다.
- `get_profile_version_path(profile_id, profile_version)` — 과거 버전 조회용 내부 helper. `profile_version`은 `versions`의 **정확한 key**여야 하므로 호출자 문자열이 경로 조각으로 쓰이지 않는다. `"../1"`, `"v2.json"`, `"/etc/passwd"` 등은 `ETLProfileNotFoundError`로 거부한다.

nested 디렉터리를 쓰게 되면서 기존의 "부모 디렉터리가 `ETL_PROFILE_DIR`와 같은가" 검사는 성립하지 않는다. 대신 `resolve()` 뒤에 `is_relative_to(ETL_PROFILE_DIR.resolve())`로 **containment**를 확인한다. 문자열 `startswith()`는 쓰지 않는다. registry 값 자체가 실수로 archive 밖(`../../config/settings.py`)을 가리켜도 거부하며, symlink는 `resolve()`가 실제 대상으로 바꾼 뒤 검사하므로 탈출할 수 없다.

### 13.4 v1 archive의 출처

v1은 **추측해서 만들지 않았다.** git 이력에서 원문을 그대로 복원했다.

```text
git show 80e8ea4^:config/etl/sample_fashion_vendor_v1.json
git show 80e8ea4^:config/etl/sample_marketplace_vendor_v1.json
```

`80e8ea4`가 두 프로필의 `profile_version`을 `"1"` → `"2"`로 올린 커밋이므로, 그 부모가 v1 시점의 마지막 상태다. 복원한 v1과 현재 v2의 차이는 **`profile_version` 값 한 줄뿐**이고 `source_columns`·`required_source_columns`·`defaults`는 동일하다.

### 13.5 fingerprint baseline

`tests/fixtures/etl/profile_fingerprints.json`에 v1 항목을 **추가**했다. 기존 v2 항목은 수정하지 않았다.

| profile_name | version | fingerprint |
| --- | --- | --- |
| sample_fashion_vendor | 1 | `917268b6…4e22b1` |
| sample_fashion_vendor | 2 | `917268b6…4e22b1` |
| sample_marketplace_vendor | 1 | `43f7ece4…c31608` |
| sample_marketplace_vendor | 2 | `43f7ece4…c31608` |

**v1과 v2의 fingerprint가 같은 것은 정상이다.** Phase 3 fingerprint는 `source_columns`·`required_source_columns`·`defaults`만 포함하고 `profile_version`은 포함하지 않는데(12장), 두 파일은 그 값만 다르기 때문이다. 값이 같다고 해서 임의로 바꾸지 않았다.

이는 동시에 12장 마지막 한계를 다시 보여 준다. v1 → v2의 실제 변화는 JSON이 아니라 **코드**(`etl/transformer.py`, `etl/db_loader.py`의 카테고리별 필수 속성 정책)에 있었고, fingerprint는 그것을 담지 않는다.

### 13.6 guardrail 확장

Phase 3 guardrail이 이제 **archive 전체**를 검사한다. 등록된 모든 `(profile_name, profile_version)`을 `load_profile()`로 읽어 baseline과 비교하므로, 과거 v1을 수정해도 현재 v2를 수정해도 CI가 실패한다. 새 버전을 registry에 추가했는데 baseline 항목이 없으면 실패하고, 과거 항목이 남아 있는 것은 계속 허용한다(append-only).

### 13.7 이번에 바뀌지 않은 것

- active transform 동작: 두 profile 모두 `"2"` 그대로. 파일 위치만 바뀌었고 매핑·기본값·필수 컬럼은 한 글자도 바꾸지 않았다
- `INSPECTION_VERSION = "13"`, Alembic head `20260813_0013`, DB 스키마·migration·의존성·workflow
- API 계약: `GET /api/v1/etl-profiles`, `GET /api/v1/etl-profiles/{profile_id}` 응답 그대로. Profile Detail은 계속 active 버전을 보여 주며 archive 경로·파일명·registry 내부를 노출하지 않는다
- 웹 ETL: `profile_id`로 실행하면 계속 active v2만 쓴다. 사용자가 v1을 고르는 기능은 없다

### 13.8 재현성: 가능해진 것과 아직 아닌 것

**가능해진 것** — 과거 profile JSON 정의를 애플리케이션이 archive 파일에서 읽을 수 있다. "그때 v1이 어떤 매핑이었나"에 저장소가 답한다.

**아직 보장하지 않는 것** — 현재 코드로 v1.json을 실행해도 **과거 v1 배치의 결과를 그대로 재현한다고 말할 수 없다.** v1 → v2 전환에는 JSON 밖의 코드 변경(카테고리별 필수 속성 정책)이 포함됐고, 지금 실행되는 것은 언제나 현재 코드다. `ETLLoadRun`에는 여전히 profile snapshot도, application commit SHA도, transformer 코드 버전도 저장하지 않는다(2.3, 2.5). git 이력을 함께 보면 개발자가 당시 코드를 찾을 수는 있지만, 런타임이 자동으로 재현해 주는 기능은 아니다.

### 13.9 `[Phase 4 시점]` 아직 없던 것

Phase 4 시점에는 Activation / Deactivation이 **미구현**이었다. 이후 Phase 5A에서 비활성 상태(`active_version = None`)를 코드에 추가했고(14장), Phase 5B.1에서 그 값을 **런타임에** 바꾸는 API와 DB 상태를 만들었다(16장).

그 뒤 Phase 5B.2에서 Streamlit 운영 관리 화면까지 생겼다(17장). 지금 기준으로 남아 있는 것은 Profile CRUD 부재다.

---

## 14. `[현재 구현]` Phase 5A — Deployment-based Activation / Deactivation

Phase 4의 명시적 active pointer 위에 **비활성(deactivated)** 상태 하나를 더 표현한다. 구조는 그대로 두고 `active_version`이 가질 수 있는 값만 넓혔다.

### 14.1 상태 표현

`active_version`은 **버전 문자열 또는 `None`** 둘 중 하나다.

| `active_version` | 의미 |
| --- | --- |
| `"2"` (버전 문자열) | 활성. 신규 ETL 실행은 그 버전의 archive를 쓴다 |
| `None` | 비활성. 신규 ETL 실행만 막는다. archive와 registry 항목은 그대로 남는다 |

`""`, `" "`, `"disabled"` 같은 값은 **비활성 표시가 아니다.** 그런 값은 `versions`에 없는 잘못된 pointer이므로 기존처럼 `ETLProfileNotFoundError`로 실패한다. 비활성 상태를 뜻하는 값은 `None` 하나뿐이라 상태가 모호해질 여지를 두지 않는다. `tests/etl/test_profile_activation.py::test_placeholder_strings_are_not_a_deactivation_marker`가 이를 고정한다.

Policy H는 그대로다. 비활성 프로필에서 "가장 큰 버전으로 대신 실행"하지 않는다. 비활성은 *무엇을 실행할지 정해지지 않은* 상태이지 *최신 버전으로 실행해도 되는* 상태가 아니다.

### 14.2 없는 프로필과 비활성 프로필은 다른 상태다

| 상황 | 예외 | API 응답 |
| --- | --- | --- |
| allowlist에 없는 `profile_id` | `ETLProfileNotFoundError` | 실행 API `400 unsupported_profile`, 상세 API `404` (기존 계약 그대로) |
| 있지만 `active_version = None` | `ETLProfileInactiveError` | `409 inactive_profile` |

`ETLProfileInactiveError`는 `ETLProfileNotFoundError`를 **상속하지 않는다.** 상속으로 묶으면 기존 `except ETLProfileNotFoundError`가 비활성 상태까지 조용히 삼켜, "오타로 없는 프로필"과 "운영이 내린 프로필"이 같은 응답으로 뭉개진다.

### 14.3 신규 ETL 실행 차단

차단은 **서버에서** 한다. 목록에서 숨기는 것은 앞단일 뿐 방어선이 아니다. 세 입력 경로가 모두 같은 `get_profile_path()`를 지나므로 정책이 한 곳에서 갈라지지 않는다.

| 입력 경로 | endpoint | 비활성일 때 |
| --- | --- | --- |
| Web CSV Upload | `POST /api/v1/etl-loads` | `409 {"code": "inactive_profile"}` |
| S3 source | `POST /api/v1/etl-loads/s3` | `409 {"code": "inactive_profile"}` |
| HTTP feed | `POST /api/v1/etl-loads/http` | `409 {"code": "inactive_profile"}` |

응답 메시지는 archive 경로·파일명·registry 내부를 노출하지 않는다. 세 경로 모두 기존 실패 metric(`record_web_etl_run("failed")`)을 정확히 한 번 남긴다.

**S3/HTTP feed는 외부 source를 읽기 전에 막는다.** 두 endpoint는 source adapter를 먼저 실행하는 구조라, 검사를 실행 시점으로 미루면 이미 비활성인 것을 알면서도 외부를 읽게 되고 source가 먼저 실패할 때 `409 inactive_profile` 대신 `404 s3_object_not_found`·`502 http_feed_read_failed`·`503 http_feed_not_configured` 같은 응답이 앞서 나간다. 그래서 두 handler는 source를 읽기 전에 `is_etl_profile_inactive()`로 확인한다. 이 순서 덕분에 비활성 프로필 요청은 나가지 않아야 할 외부 요청 자체를 만들지 않는다.

사전 검사가 막는 것은 **"allowlist에 있으면서 비활성"인 경우뿐이다.** 없는 `profile_id`는 사전 검사하지 않고 그대로 통과시켜, 기존 source-error precedence와 `400 unsupported_profile` 계약을 바꾸지 않는다. 잘못된 active pointer도 마찬가지로 통과시켜 기존대로 실행 시점에 실패한다(자동 fallback 없음). `is_etl_profile_inactive()`는 registry를 읽기만 하는 조회 함수이며 activation을 바꾸지 않는다.

### 14.4 Profile 목록과 상세

- `GET /api/v1/etl-profiles` — `list_etl_profiles()`가 비활성 프로필을 **제외**한다. 이 목록의 유일한 용도가 "신규 ETL 실행용 selector"이기 때문이다. 응답 형태(`{id, display_name}`)는 그대로다. Streamlit selector에서도 비활성 프로필을 고를 수 없게 된다.
- `GET /api/v1/etl-profiles/{profile_id}` — 이 API는 **active 버전의** detail을 보여 준다. 비활성 프로필에 마지막 active 버전을 그대로 보여 주면 "지금 이 버전으로 실행된다"는 거짓이 되므로 `409 inactive_profile`을 반환한다. 없어졌다(`404`)고 말하지도 않는다.

archive 버전을 조회하는 **공개 API는 만들지 않았다.** 과거 정의 접근은 내부 helper `get_profile_version_path()`로만 가능하다.

### 14.5 Deactivate는 Delete가 아니다

`active_version = None`이어도 다음은 그대로다.

- `versions`의 archive 파일과 registry 항목은 삭제하지 않는다
- `get_profile_version_path(profile_id, "1")`, `get_profile_version_path(profile_id, "2")`는 계속 동작한다
- Phase 3 fingerprint guardrail은 archive 전체를 계속 검사한다
- 과거 `etl_load_runs` 행이 참조하는 `(profile_name, profile_version)` 정의를 여전히 읽을 수 있다

막히는 것은 **신규 실행 하나뿐이다.**

### 14.6 이번에 바뀌지 않은 것

- **두 프로필은 계속 active `"2"`다.** Phase 5A는 기능을 지원하는 코드 확장이지 실제 프로필을 비활성화하는 작업이 아니다
- `INSPECTION_VERSION = "13"`, Alembic head `20260813_0013`, DB 스키마·migration·의존성·workflow
- ETL transform 의미, dedup identity, fingerprint baseline
- 없는 `profile_id`의 기존 계약: 실행 API `400 unsupported_profile`, 상세 API `404`
- 활성 프로필의 목록·상세·Web/S3/HTTP ETL·Browser E2E 동작

### 14.7 아직 없는 것 (Phase 5B)

> **이 절은 Phase 5B.1(16장)이 일부를 해소했다.** 아래는 Phase 5A 시점의 상태이며, 무엇이 바뀌었는지는 각 항목에 적었다.

Phase 5A 시점에 activation 변경은 **배포가 필요한 code configuration**이었다. `active_version`을 바꾸려면 코드 변경 → 테스트 → 배포를 거쳐야 했다.

- ~~activation/deactivation을 바꾸는 **관리자 API가 없다**~~ → Phase 5B.1에서 추가됐다(16장)
- ~~Streamlit **활성/비활성 버튼이 없다**~~ → Phase 5B.2에서 추가됐다(17장)
- ~~DB-backed active flag가 없다~~ → Phase 5B.1이 **activation 상태만** DB로 옮겼다. 프로필 정의 자체를 DB로 옮기는 것은 여전히 Phase 6(조건부)이다
- Profile CRUD(등록·수정·삭제)가 없다 → 여전히 없다
- 런타임 메모리의 registry를 API로 고치는 기능은 **의도적으로** 만들지 않았다. 재시작하면 사라지는 상태는 "관리 기능처럼 보이지만 관리되지 않는" 더 나쁜 상태를 만든다. Phase 5B.1도 이 판단을 그대로 지켜, 메모리 registry를 고치지 않고 **DB에 저장되는 별도 상태**를 얹었다

---

## 15. `[현재 구현]` Phase 5A.1 — 클라이언트/UI의 inactive 처리

Phase 5A에서 서버는 `409 inactive_profile`을 구분했지만, Python API 클라이언트는 이 코드를 전용 예외로 매핑하지 않아 Streamlit에는 일반 서버 오류로 보였다. 사용자가 보는 화면이 실제 원인을 말하지 못하는 gap이었다. 서버 계약은 그대로 두고 클라이언트·UI만 맞춘다.

### 15.1 클라이언트 매핑

`clients/catalogguard_api.py`에 `ETLProfileInactiveError`를 추가했다. `ETLWebRunApiError`(즉 `CatalogGuardApiResponseError`) 계열이고 `code`와 `request_id`를 기존 방식대로 보존한다. `ETLUnsupportedProfileError`와는 **형제 관계**다. 사용자가 해야 할 일이 다르기 때문이다 — 없는 프로필은 선택을 고쳐야 하고, 비활성 프로필은 다른 프로필을 골라야 한다.

| 경로 | 응답 | 클라이언트 예외 |
| --- | --- | --- |
| `POST /api/v1/etl-loads` | `409 inactive_profile` | `ETLProfileInactiveError` |
| `GET /api/v1/etl-profiles/{profile_id}` | `409 inactive_profile` | `ETLProfileInactiveError` |
| 위 두 경로 | `400 unsupported_profile` / `404` | 기존 계약 그대로 |

Profile Detail의 409 매핑은 **opt-in**이다. `_get_json()`/`_get_response()`의 `map_inactive_profile` 플래그를 profile detail에서만 켠다. 모든 GET의 409를 프로필 오류로 바꾸면 관계없는 endpoint의 상태 충돌까지 잘못 분류된다. 켠 곳에서도 payload의 `code`가 실제로 `inactive_profile`일 때만 전용 예외가 되고, JSON이 아니거나 `detail`이 없거나 코드가 다르면 기존 `CatalogGuardApiResponseError`로 남는다.

화면 문구는 **클라이언트가 관리하는 고정 문구**를 쓰고 서버 `message` 원문을 그대로 노출하지 않는다. archive 경로나 registry 내부값은 표시하지 않는다.

### 15.2 Streamlit race 처리

목록을 받은 뒤 배포로 프로필이 내려가는 race가 있다. 이때 오류만 띄우고 오래된 목록을 그대로 두면 사용자가 같은 프로필을 다시 고르게 된다.

- 실행(`_submit_etl_web_run()`)과 상세 조회(`_fetch_etl_profile_detail()`) 모두 `ETLProfileInactiveError`를 일반 서버 오류와 구분해 처리한다
- 두 경로 모두 프로필 목록 캐시(`etl_web_run_profiles_response`, `etl_web_run_profiles_error`)를 무효화해, 다음 rerun의 `_fetch_etl_profiles()`가 `GET /api/v1/etl-profiles`를 다시 호출해 서버의 현재 active 목록을 받는다
- 실행 실패 쪽은 상세 캐시(`etl_web_run_profile_detail_*`)도 함께 비운다. 상세 조회 쪽은 `detail_id`를 남겨 같은 프로필에 409 요청을 반복하지 않는다
- **캐시 무효화 시 `st.rerun()`을 부르지 않는다.** 렌더링 도중 rerun을 걸면 같은 비활성 오류로 다시 들어와 무한 rerun이 된다. 새로고침은 기존 흐름(실행 버튼 뒤의 `st.rerun()`, 또는 다음 상호작용)에서 자연스럽게 일어난다

### 15.3 여전히 없는 것

Phase 5A.1은 **표시와 오류 분류만** 바꾼다. 이 시점에는 runtime activation API·Streamlit 활성/비활성 버튼·DB-backed active flag·Profile CRUD가 모두 없었고, activation 상태를 바꾸려면 코드 변경 → 테스트 → 배포가 필요했다. 그중 API와 DB 상태는 Phase 5B.1(16장), Streamlit 관리 화면은 Phase 5B.2(17장)에서 생겼다. Profile CRUD는 여전히 없다.

---

## 16. `[현재 구현]` Phase 5B.1 — Persistent Runtime Activation API

Phase 5A까지 activation은 코드 상수였다. 바꾸려면 코드 수정 → 테스트 → 배포가 필요했고, 그래서 "공급사 피드가 깨졌으니 지금 내려 달라"에 배포 한 번이 필요했다. Phase 5B.1은 그 상태를 API로 바꿀 수 있게 하되 **DB에 저장**한다.

메모리의 registry를 API로 고치는 방식은 14.7에서 의도적으로 거부했던 것이고, 여기서도 하지 않는다. 재시작하면 사라지고 worker마다 달라지는 상태는 관리 기능처럼 보이지만 관리되지 않는다.

### 16.1 무엇을 저장하는가

프로필 **정의**는 옮기지 않았다. `config/etl`의 버전별 archive와 코드 registry가 계속 source of truth이고, Policy A(Published Version Immutable)도 그대로다. DB에 있는 것은 "이미 보존된 어떤 버전을 신규 실행에 쓸 것인가" 하나뿐이다.

`etl_profile_activations` (Alembic `20260822_0014`)

| 컬럼 | 뜻 |
| --- | --- |
| `profile_id` | registry의 allowlist key. unique index가 프로필당 row 하나를 보장한다 |
| `active_version` | 활성 버전 문자열, 또는 `NULL`(비활성) |
| `actor_user_id` / `actor_username` | 마지막으로 바꾼 로그인 사용자 |
| `updated_at` | 마지막으로 바꾼 시각 |

`profile_id`에 FK를 걸지 않았다. 프로필은 아직 DB entity가 아니라 코드 registry의 key이므로, 존재하지 않는 대상을 가리키는 FK를 만들 수 없다. 대신 쓰기 경로가 allowlist와 `versions`를 검증한다.

### 16.2 배포 기본값과 runtime override

**"row 없음"과 "row 있음 + `active_version` NULL"은 다른 상태다.**

| runtime row | `active_version` | effective |
| --- | --- | --- |
| 없음 | — | 배포 registry의 `active_version` |
| 있음 | `"2"` | `"2"` |
| 있음 | `NULL` | 비활성 |

둘을 하나로 합치면 배포 기본값이 바뀔 때 운영자의 결정이 조용히 뒤집힌다. "아직 아무도 손대지 않았다"와 "운영자가 명시적으로 내렸다"는 다음에 해야 할 일이 다르다.

계산은 `etl.profile_loader.resolve_etl_profile_activation()` **한 곳**에서만 한다. Web/S3/HTTP/Airflow가 각자 DB를 읽어 각자 판단하면 같은 프로필이 경로마다 다르게 활성으로 보인다.

### 16.3 API

| method | path | 권한 |
| --- | --- | --- |
| `GET` | `/api/v1/etl-profiles/{profile_id}/activation` | viewer |
| `PUT` | `/api/v1/etl-profiles/{profile_id}/activation` | operator |

`PUT`을 쓰는 이유는 이 요청이 새 자원을 만드는 것이 아니라 하나뿐인 상태를 통째로 바꾸기 때문이다. 같은 body를 두 번 보내면 결과가 같다. 저장소의 다른 endpoint가 모두 `POST`인 것은 그것들이 실행·발급·생성이기 때문이고, 여기서만 성격이 다르다.

요청 body는 `{"active_version": "2"}` 또는 `{"active_version": null}` 하나뿐이다. **actor를 body로 받지 않는다.** 받아 두고 무시하면 다음 사람이 "왜 반영되지 않지"를 디버깅하게 되므로, 받을 자리 자체를 두지 않고 `extra="forbid"`로 거부한다. 이 endpoint를 Profile Update API로 오해해 `source_columns`를 보내면 조용히 무시되지 않고 422가 된다.

응답은 세 값을 나눠서 준다. `effective` 하나만 주면 지금 상태가 배포 때문인지 운영자 때문인지 알 수 없다.

```json
{
  "deployment_active_version": "2",
  "runtime_override_exists": true,
  "runtime_active_version": null,
  "effective_active_version": null,
  "is_active": false,
  "available_versions": ["1", "2"]
}
```

`available_versions`가 없으면 호출자가 무엇을 고를 수 있는지 몰라 존재하지 않는 버전을 추측해 보내게 된다. 보존 목록에 없는 값은 `422 unknown_profile_version`으로 거부하고, 없는 `profile_id`는 `404`다. 둘을 같은 코드로 뭉개지 않는 이유는 운영자가 고쳐야 할 대상이 다르기 때문이다.

**비활성 프로필도 이 GET에서는 200으로 조회된다.** 이 endpoint의 목적이 "지금 활성인가"를 묻는 것이므로, 비활성이라고 409를 내면 상태를 확인할 방법이 사라진다. 목록(`GET /api/v1/etl-profiles`)이 비활성을 숨기는 것과는 목적이 다르다.

### 16.4 과거 버전을 다시 활성화한다는 것의 의미

이제 `{"active_version": "1"}` 한 번으로 과거 버전으로 되돌릴 수 있다. 그래서 **무엇이 되돌아가고 무엇이 되돌아가지 않는지**를 여기서 다시 분명히 해 둔다. 13.8의 한계는 그대로이며, 전환이 쉬워진 만큼 오해하기도 쉬워졌다.

**되돌아가는 것**: 그 버전의 프로필 JSON 정의. `source_columns`, `required_source_columns`, `defaults`가 archive에 보존된 그대로 쓰인다. 새 배치의 `profile_version`도 그 값으로 기록된다.

**되돌아가지 않는 것**: 애플리케이션 코드. 실행되는 것은 **언제나 현재 코드**다. v1을 다시 활성화해도 "현재 코드 + v1.json"이 돌아가지, 과거 v1 배치가 돌던 런타임 전체가 재현되지는 않는다.

이 차이가 실제로 문제가 되는 선례가 이미 있다. v1 → v2 전환에서 실제로 바뀐 것은 JSON이 아니라 **카테고리별 필수 속성 정책 코드**였다(`80e8ea4`, 5장). 그 코드는 지금도 v2 시점의 것이므로, v1.json을 활성화해도 그 정책은 v1 시절로 돌아가지 않는다.

`ETLLoadRun`에는 여전히 profile snapshot도, application commit SHA도, transformer 코드 버전도 저장하지 않는다(2.3, 2.5). 따라서 activation API는 **"어떤 매핑 정의로 실행할지"를 고르는 기능**이지 "과거 배치를 재현하는 기능"이 아니다. 재현이 목적이라면 코드 버전까지 함께 고정해야 하고, 그것은 이 문서의 어떤 Phase도 아직 제공하지 않는다.

### 16.5 신규 실행 차단

Phase 5A의 `409 inactive_profile` 계약은 **그대로다.** runtime에서 내렸든 배포로 내렸든 응답은 같고, Python client의 `ETLProfileInactiveError`도 그대로 동작한다.

네 입력 경로가 모두 같은 resolver를 지난다.

| 경로 | 어떻게 지나는가 |
| --- | --- |
| Web CSV Upload | `run_web_etl()` → `get_profile_path(session=...)` |
| S3 source | source를 읽기 전 `is_etl_profile_inactive(session=...)`, 그 뒤 `run_web_etl()` |
| HTTP feed | 위와 같다 |
| Airflow DAG | `run_web_etl()`에 자기 session을 넘긴다 |

S3/HTTP는 외부를 읽기 전에 막는다는 14.3의 순서도 그대로다. 이 사전 검사가 이제 session을 받는 이유는, 배포 기본값만 보면 runtime에서 내린 프로필이 외부를 먼저 읽고 나서야 막히기 때문이다.

`etl.cli`는 `profile_id`가 아니라 파일 경로를 직접 받으므로 이 resolver를 지나지 않는다. 의도적이다. CLI의 `--profile`은 "이 파일로 실행하라"는 명시적 지시이지 "활성 버전으로 실행하라"가 아니다.

### 16.6 막히지 않는 것

비활성은 **신규 실행 하나만** 막는다. 과거 데이터 조회는 그대로다 — ETL 이력·상세·품질 요약/추이/관찰·상품 동기화 차이·Promotion 이력·audit·Rollback 이력. `versions` archive와 과거 `etl_load_runs`도 그대로 남는다(Policy G, 14.5).

### 16.7 조회와 쓰기 트랜잭션

activation 조회는 SELECT라 session을 autobegin시킨다. 그 상태로 두면 바로 뒤 `load_standard_csv()`의 `with session.begin()`이 "A transaction is already begun"으로 실패한다. 실제로 PostgreSQL 통합 테스트에서 이 충돌이 먼저 드러났다.

그래서 조회 직후 `end_activation_read_transaction()`으로 읽기 트랜잭션을 끝낸다. 읽기 전용이라 잃을 것이 없고, 그 사이에 끼는 `run_pipeline()`은 파일 I/O라 idle 트랜잭션을 붙들고 있을 이유도 없다.

단순히 `rollback()`만 하지 않는다. 나중에 누군가 이 앞에 쓰기를 추가하면 그 쓰기가 **조용히** 사라지기 때문이다. 지금까지 같은 상황은 `session.begin()`이 시끄럽게 실패시켜 줬는데, rollback이 그 신호를 지운다. 그래서 rollback 전에 보류 중인 ORM 쓰기가 있으면 `PendingWriteBeforeActivationReadError`를 먼저 낸다.

한계도 적어 둔다. 이 검사는 ORM 단위 작업(`new`/`dirty`/`deleted`)만 본다. `session.execute(insert(...))` 같은 Core 쓰기는 감지되지 않고 함께 rollback된다. 다만 그런 호출자는 원래도 허용되지 않았다 — `load_standard_csv()`가 자기 트랜잭션을 여는 구조라, `run_web_etl()`에 넘기는 session은 트랜잭션이 열려 있지 않아야 한다는 것이 이 함수 이전부터의 계약이다.

현재 네 경로 모두 이 시점에 쓰기를 들고 있지 않다. Web upload는 `await file.read()`만, S3/HTTP는 비활성 사전 검사(읽기)와 source fetch만, Airflow는 session을 만든 직후 호출한다.

### 16.8 동시성

`profile_id` unique index가 중복 row를 막고, 쓰기는 `INSERT ... ON CONFLICT (profile_id) DO UPDATE` 한 문장이라 동시 요청이 `IntegrityError`로 사용자에게 새지 않는다. 결과는 **last-write-wins**다.

분산 lock이나 낙관적 버전 필드는 두지 않았다. 이 상태는 프로필당 값 하나이고 변경 빈도가 낮아, lock의 복잡도가 그것이 막는 위험보다 크다.

**진 쪽의 결정은 보존되지 않는다.** 이 표는 append-only history가 아니라 프로필당 current-state row 하나다. A가 deactivate하고 B가 v2를 activate하면 최종 row에는 B의 `active_version`·`actor_username`·`updated_at`만 남고, A의 이전 결정은 사라진다.

`actor_username`과 `updated_at`은 **현재 상태를 마지막으로 만든 것이 누구/언제인가**를 말할 뿐이며, 그것으로 activation 변경 이력을 되짚을 수는 없다. append-only activation audit/history는 Phase 5B.1 범위 밖이고(16.10), 필요해지면 별도 표가 있어야 한다.

### 16.9 이번에 바뀌지 않은 것

- `INSPECTION_VERSION = "13"`, `PREVIEW_SCHEMA_VERSION = 1`, 두 프로필의 semantic `profile_version = "2"`
- ETL dedup identity `(input_file_sha256, profile_name, profile_version)`. activation 변경 자체는 dedup을 바꾸지 않는다. 다만 활성 버전을 v1으로 바꾼 뒤 같은 CSV를 실행하면 `profile_version`이 달라 다른 배치가 된다 — 기존 dedup 정책 그대로의 결과다
- 프로필 JSON, fingerprint baseline, transform 의미
- `400 unsupported_profile` / `404` / `409 inactive_profile`의 기존 응답 계약
- Streamlit 화면. 실행 화면의 inactive 안내(15장)가 runtime deactivation에도 그대로 동작한다

### 16.10 아직 없는 것

- ~~**Streamlit 관리 UI가 없다**(Phase 5B.2). 지금은 API를 직접 호출해야 한다~~ → Phase 5B.2에서 추가됐다(17장)
- Profile CRUD(등록·수정·삭제)가 없다
- ~~activation 변경 **이력**이 없다. 표는 현재 상태 한 줄만 들고 있어 "언제 누가 내렸다가 언제 올렸는가"는 남지 않는다. append-only audit이 필요해지면 별도 표가 필요하다~~ → Phase 5B.4에서 별도 표로 추가됐다(19장). 다만 그 기록은 `20260823_0015` 적용 **이후**의 명령부터다
- 과거 배치의 **런타임 재현**은 여전히 없다. 버전 전환이 쉬워졌을 뿐, 실행되는 코드는 언제나 현재 코드다(16.4)
- ~~Airflow DAG는 비활성 프로필을 `catalogguard_etl_unexpected`로 실패시킨다~~ → 전용 코드 `etl_profile_inactive`(non-retryable)로 구분한다. 다만 DAG에는 API의 S3/HTTP route와 달리 fetch 전 사전 검사가 없어, 비활성 프로필도 HTTP 피드를 한 번 읽은 뒤 `run_web_etl()`에서 판별된다. 분류는 정확하지만 그 읽기는 낭비이며, 피드 자체가 실패하면 여전히 피드 오류 코드가 먼저 보고된다

---

## 17. `[현재 구현]` Phase 5B.2 — Streamlit 운영 관리 화면

Phase 5B.1이 만든 activation API를 운영자가 화면에서 쓸 수 있게 한다. 서버 계약·DB 스키마·동시성 정책은 **한 줄도 바꾸지 않았다.** Alembic head도 `20260822_0014` 그대로다.

### 17.1 먼저 걸린 것: 비활성 프로필이 목록에서 사라진다

`GET /api/v1/etl-profiles`는 활성 프로필만 돌려준다. 실행 selector에는 맞는 동작이지만, 관리 화면이 같은 목록을 쓰면 **한 번 내린 프로필을 다시 고를 수 없어 영영 되살릴 수 없다.**

Streamlit이 registry를 직접 import해서 우회하지 않는다. UI는 API 경계를 지켜야 하고, 그러지 않으면 화면이 서버와 다른 allowlist를 갖게 된다.

그래서 목록 endpoint에 **optional query parameter 하나**만 더했다.

| 호출 | 결과 |
| --- | --- |
| `GET /api/v1/etl-profiles` | 활성 프로필만 (**기존 계약 그대로**) |
| `GET /api/v1/etl-profiles?include_inactive=true` | allowlist 전체 |

기본값이 `false`라 기존 호출자는 지금까지와 완전히 같은 응답을 받는다. 응답 shape도 그대로 `{id, display_name}`이고, 각 프로필의 실제 상태는 이미 있는 `.../activation`으로 따로 조회한다. 프로필이 두 개뿐인 지금 bulk endpoint를 새로 만드는 것보다 단순하다.

`include_inactive=true`는 **필터를 끄는 것이지 후보를 넓히지 않는다.** registry allowlist 밖의 항목은 어느 경우에도 나오지 않고 정의 순서도 같다.

### 17.2 화면

`ETL 적재 이력` 탭의 `ETL 실행` 바로 아래에 `ETL 프로필 운영 관리` 구획을 둔다. divider로 나눠 일반 실행 흐름을 복잡하게 만들지 않는다.

**selector와 상태 key를 실행 화면과 분리했다.** 관리 화면에서 프로필을 바꾸는 것이 "지금 실행할 프로필" 선택을 건드리면 안 되기 때문이다.

| 용도 | 목록 | state key |
| --- | --- | --- |
| 신규 ETL 실행 | 활성만 | `etl_web_run_selected_profile_id` |
| 운영 관리 | `include_inactive=true` | `etl_profile_admin_selected_profile_id` |

### 17.3 세 상태를 절대 뭉개지 않는다

화면에서 가장 중요한 부분이다. `런타임 override 없음`은 **비활성이 아니다.**

| 화면 문구 | 뜻 |
| --- | --- |
| `런타임 override 없음 (배포 기본값 사용)` | 아무도 손대지 않았고 배포 registry 값을 따른다 |
| `런타임에서 v2 활성으로 지정` | 운영자가 명시적으로 그 버전을 고정했다 |
| `런타임에서 비활성으로 지정` | 운영자가 명시적으로 내렸다 |

`상태`(활성/비활성), `실제 적용 버전`, `배포 기본 버전`을 함께 보여 줘서 "왜 지금 이 상태인가"에 답한다.

`마지막 변경 사용자`와 `마지막 변경 시각`은 **runtime override가 있을 때만** 보여 준다. override가 없는데 표시하면 아무도 바꾼 적 없는 상태를 누군가 바꾼 것처럼 읽힌다. 그 값이 변경 이력이 아니라 현재 상태를 만든 마지막 정보라는 점도 화면에 적는다(16.8).

### 17.4 활성화 버튼을 언제 막는가

단순히 `effective == selected`로 막으면 **틀린다.**

override가 없는 상태에서 배포 기본값과 같은 버전을 고르는 것은 의미가 다른 조작이다. 누르면 배포 기본값을 따르던 프로필이 그 버전으로 **고정**되어, 나중에 배포 기본값이 바뀌어도 따라가지 않는다. 그래서 그 경우 활성화를 허용하고, 무엇이 달라지는지 화면에 적는다.

| 상태 | 활성화 버튼 |
| --- | --- |
| override 없음 (배포 기본값 v2), `v2` 선택 | **가능** — 배포 기본값 추종 → 명시적 고정으로 바뀐다 |
| override `v1`, `v1` 선택 | 막음 — 진짜 no-op이라 `updated_at`만 갱신된다 |
| override `v1`, `v2` 선택 | 가능 |
| 명시적 비활성, 아무 버전 선택 | 가능 (되살리기) |

버전 목록은 항상 activation 응답의 `available_versions`에서만 만든다. UI가 버전을 하드코딩하지 않는다.

### 17.5 비활성화는 확인을 거친다

신규 ETL을 즉시 막는 조작이라 checkbox 확인 전에는 버튼이 disabled다. 확인 값은 전송 직전에 한 번 더 본다. `disabled`는 화면 안내이고 최종 보장은 서버의 operator RBAC이다. 비밀번호 재입력 같은 절차는 만들지 않았다.

이미 비활성인 프로필에는 비활성화 버튼을 보여 주지 않는다. 대신 버전을 골라 다시 활성화할 수 있다.

### 17.6 권한

`ui.auth.is_operator()`를 그대로 쓴다. UI에서 role 문자열을 새로 비교하지 않는다.

- viewer: 상태·배포 기본값·런타임 설정·사용 가능한 버전을 **볼 수 있다**
- viewer: 버전 selectbox와 활성화/비활성화 버튼이 **아예 없다**
- operator: 전부 가능

### 17.7 캐시와 rerun

성공/실패 판정 뒤에만 로컬 상태를 건드린다. 서버가 거절했는데 화면만 바뀌면 운영자가 내리지 않은 프로필을 내렸다고 믿게 된다.

성공하면 관리 목록·실행 목록·실행 화면의 프로필 상세 캐시를 함께 비운다. 그래야 방금 내린 프로필이 실행 selector에서 사라지고, 다시 올리면 되돌아온다.

버튼을 누른 뒤에만 `st.rerun()`을 부른다. 결과 메시지가 이 구획보다 위에서 그려지기 때문에 rerun 없이는 이번 화면에 반영되지 않는다. 렌더링 도중 무조건 rerun하지 않으므로 Phase 5A.1이 피한 무한 rerun은 생기지 않는다.

### 17.8 보안

- actor 입력칸이 **없다.** 서버가 인증된 `current_user`에서만 가져온다
- `profile_id`와 버전은 자유 입력이 아니라 API가 준 선택지에서만 고른다
- 서버 `message` 원문을 그대로 쓰지 않고 클라이언트가 화면 문구를 관리한다

### 17.9 이번에 바뀌지 않은 것

activation API 계약, DB 스키마, Alembic head(`20260822_0014`), 동시성 정책(last-write-wins), `INSPECTION_VERSION`, `PREVIEW_SCHEMA_VERSION`, profile semantic version, dedup identity, 프로필 JSON, Observability/Reconciliation/Promotion/Rollback, 의존성.

### 17.10 아직 없는 것

- ~~**runtime override 제거(배포 기본값 복귀) 기능이 없다.**~~ → Phase 5B.3에서 추가됐다(18장). 아래 17.11은 Phase 5B.2 시점의 한계 기록이다
- ~~activation 변경 이력(append-only audit)이 없다(16.10)~~ → Phase 5B.4에서 추가됐다(19장)
- Profile CRUD가 없다
- 이 화면의 Chromium E2E가 없다. AppTest로만 검증한다

### 17.11 `[한계]` runtime override는 되돌릴 수 없다

> **갱신(Phase 5B.3)**: 이 한계는 해소됐다. 아래는 Phase 5B.2 시점의 기록이며, 지금 무엇이 사실인지는 18장이 말한다.

현재 API로 만들 수 있는 상태 전환은 셋뿐이다.

```text
배포 기본값 사용  --PUT version-->  명시적 활성 override
배포 기본값 사용  --PUT null----->  명시적 비활성 override
명시적 비활성     --PUT version-->  명시적 활성 override
```

**없는 전환**: `명시적 override → 배포 기본값 사용`. runtime row를 지우는 DELETE/reset endpoint가 없기 때문이다.

`PUT {"active_version": null}`은 **override 제거가 아니라 명시적 비활성**이다. 두 개념을 섞으면 안 된다. 그래서 화면에 "배포 기본값으로 되돌리기" 버튼을 만들지 않았다. 있지도 않은 동작을 버튼으로 보여 주는 것이 기능이 없는 것보다 나쁘다.

한 번 override를 만들면 그 프로필은 계속 명시적으로 관리된다. Phase 5B.2의 목표(상태 확인·활성화·비활성화)에는 이 전환이 필요 없어서 blocker는 아니지만, 실제 운영에서 필요해지면 별도 endpoint를 설계해야 한다.

---

## 18. `[현재 구현]` Phase 5B.3 — Runtime Override Reset

Phase 5B.2가 남긴 한계 하나(17.11)를 없앤다. **없던 상태 전환 하나**를 더하는 것이 전부이고, 기존 계약은 한 줄도 바꾸지 않았다. DB 스키마와 Alembic head(`20260822_0014`)도 그대로다.

### 18.1 왜 필요했나: `PUT null`은 reset이 아니다

`PUT {"active_version": null}`은 **명시적 비활성**이다. row가 남고, "운영자가 이 프로필을 내렸다"는 사실이 저장된다. 그래서 이 요청으로는 "아무도 손대지 않은 상태"로 돌아갈 수 없다.

한 번 override를 만들면 그 프로필은 영영 명시적으로 관리됐다. 배포 기본값이 바뀌어도 그 프로필만 따라가지 않고, 되돌릴 방법이 없었다.

두 개념을 하나로 합치는 것(= `PUT null`을 reset으로 바꾸는 것)은 **선택지가 아니다.** 합치는 순간 운영자가 내린 결정이 배포 기본값이 바뀔 때 조용히 뒤집힌다. 그래서 `PUT null`의 뜻은 그대로 두고 **DELETE를 따로 만들었다.**

### 18.2 상태 전환

| 동작 | `etl_profile_activations` row | effective |
| --- | --- | --- |
| `PUT {"active_version": "2"}` | 있음 (`active_version = '2'`) | `"2"` |
| `PUT {"active_version": null}` | 있음 (`active_version = NULL`) | `None` — 명시적 비활성 |
| `DELETE` (이번 Phase) | **없음** | 배포 registry의 `active_version` |

`DELETE` 뒤에는 `runtime_override_exists = false`, `runtime_active_version = null`이고 `effective_active_version = deployment_active_version`이다. `is_active`도 배포 기본값이 다시 정한다.

이제 없던 전환이 생겼다.

```text
명시적 활성 override  --DELETE-->  배포 기본값 사용
명시적 비활성 override --DELETE-->  배포 기본값 사용
```

### 18.3 `[안전]` reset은 프로필을 되살릴 수 있다

이번 Phase에서 가장 중요한 사실이다.

배포 기본값이 활성(`v2`)인 프로필에 명시적 비활성 override가 걸려 있을 때 reset을 누르면, override가 사라지면서 **배포 기본값 `v2`가 다시 적용되어 그 프로필이 즉시 실행 가능해진다.**

그래서 화면에서 reset을 단순한 "정리" 버튼처럼 보여 주지 않는다.

- 누르기 전에 **되돌린 뒤 실제 적용 버전**을 보여 준다
- 지금 비활성인 프로필이면 "다시 활성화됩니다"를 명시한다
- 배포 기본값 자체가 비활성이면 "reset 뒤에도 계속 비활성"임을 정확히 말한다
- 비활성화와 같은 수준의 확인 checkbox를 거친다

### 18.4 Idempotency와 404의 구분

`DELETE`는 idempotent하다. override가 이미 없어도 200이고, 배포 기본값 상태를 그대로 돌려준다. 두 번째 DELETE는 재시도이지 오류가 아니다.

다만 **없는 프로필은 계속 404**다. "지울 것이 없다"와 "그런 프로필이 없다"는 운영자가 해야 할 일이 다르고, 하나로 뭉개면 오타로 친 profile_id가 성공으로 보인다.

| 요청 | 응답 |
| --- | --- |
| allowlist 프로필 + override 있음 | 200 (지우고 배포 기본값 상태 반환) |
| allowlist 프로필 + override 없음 | 200 (그대로 배포 기본값 상태 반환) |
| allowlist 밖 profile_id | 404 |
| viewer | 403 |
| 미인증 | 401 |

### 18.5 왜 204가 아니라 200 + activation 응답인가

`204 No Content`면 화면이 reset 직후의 effective 상태를 알기 위해 `GET`을 한 번 더 해야 한다. 그 사이에 다른 운영자의 변경이 끼면 화면이 **방금 자기가 만든 상태를 잘못 설명한다.**

그래서 기존 `ETLProfileActivationResponse`를 그대로 돌려준다. 새 schema를 만들지 않았고, 클라이언트도 기존 응답 검증을 그대로 재사용한다. `actor_username`과 `updated_at`은 항상 `null`이다 — 그 값을 들고 있던 row 자체가 없어졌기 때문이다.

`DELETE`는 body를 받지 않는다. 지울 대상은 경로의 `profile_id` 하나로 정해지고, actor는 저장할 row가 없어진다.

### 18.6 권한

기존 RBAC dependency를 그대로 쓴다. 새 role도 새 검사도 없다.

| 메서드 | 권한 |
| --- | --- |
| `GET .../activation` | viewer 이상 |
| `PUT .../activation` | operator |
| `DELETE .../activation` | operator |

### 18.7 `[한계]` reset은 정보를 지운다

이 표는 프로필당 **current-state row 하나**다(16.8). DELETE하면 그 row의 `active_version`뿐 아니라 `actor_username`과 `updated_at`도 함께 사라진다.

즉 "누가 언제 이 override를 만들었는가"는 reset과 동시에 어디에도 남지 않는다. activation append-only history/audit 표는 **이번 Phase에서도 만들지 않았다**(16.10). 필요해지면 별도 Phase에서 별도 표로 설계해야 하며, 이 표를 그 용도로 읽으면 안 된다.

> **갱신(Phase 5B.4)**: 이 한계는 해소됐다. current-state 표는 그대로이고(지금도 reset하면 그 row의 actor/updated_at은 사라진다), **명령 자체**는 별도 append-only 표에 남는다. 19장을 보라.

### 18.8 이번에 바뀌지 않은 것

- `PUT {"active_version": null}`의 뜻. 여전히 **명시적 비활성**이고 override를 남긴다
- `GET`/`PUT`의 응답 계약, `ETLProfileActivationResponse` schema, `available_versions` 규칙
- DB 스키마, Alembic head `20260822_0014`, migration
- effective 계산 위치. 계속 `resolve_etl_profile_activation()` 한 곳뿐이다
- Profile CRUD 없음, ProfileVersion DB 표 없음, activation history 없음
- Airflow DAG, S3/HTTP의 fetch 전 사전 검사, 실패 코드 우선순위
- `INSPECTION_VERSION`, `PREVIEW_SCHEMA_VERSION`, profile semantic version, dedup identity, 프로필 JSON
- 의존성

### 18.9 부수적으로 고친 것

Streamlit 관리 화면의 확인 checkbox 초기화가 성공 처리에서 `session_state[key] = False`로 되어 있었다. Streamlit은 이번 run에서 이미 만들어진 widget의 key에 대입하면 예외를 내므로, 비활성화 성공 뒤 화면이 예외로 끝나고 있었다. 기존 AppTest가 `app.exception`을 보지 않아 드러나지 않던 문제다.

대입 대신 삭제(`pop`)로 바꿨다. 삭제는 허용되고 다음 run에서 checkbox가 기본값으로 다시 만들어진다. reset과 비활성화가 같은 경로를 쓰므로 한 곳만 고치면 둘 다 낫는다.

### 18.10 아직 없는 것

- ~~activation 변경 이력(append-only audit)이 없다 — 18.7~~ → Phase 5B.4에서 추가됐다(19장)
- Profile CRUD(등록·수정·삭제)가 없다
- 이 화면의 Chromium E2E가 없다. AppTest로만 검증한다
- 과거 배치의 런타임 재현은 여전히 없다(16.4)

---

## 19. `[현재 구현]` Phase 5B.4 — Activation Append-only History

Phase 5B.1~5B.3이 남긴 한계(16.10, 18.7)를 없앤다. **current-state 구조는 한 줄도 바꾸지 않았다.** `PUT null`은 여전히 명시적 비활성이고, `DELETE`는 여전히 reset이다. 더한 것은 표 하나와 읽기 endpoint 하나다. Alembic head는 `20260823_0015`.

### 19.1 왜 별도 표인가

`etl_profile_activations`는 프로필당 **current-state row 하나**다. 그래서 이런 일이 일어났다.

```text
운영자 A --activate v2--> 운영자 B --deactivate--> 운영자 C --reset-->
```

표에 남는 것은 마지막 상태뿐이고, C의 reset은 row 자체를 지우므로 `actor_username`과 `updated_at`까지 함께 사라진다. **누가 무엇을 했는지 아무것도 남지 않는다.**

이 표를 history 표로 바꾸는 것은 선택지가 아니다. 바꾸면 "지금 무엇이 적용되는가"를 물을 때마다 이력 전체에서 최신 행을 골라야 하고, 그 계산이 `resolve_etl_profile_activation()` 밖으로 새어 나간다. 그래서 **두 표를 나눴다.**

| 표 | 답하는 질문 | 쓰기 | row 수 |
| --- | --- | --- | --- |
| `etl_profile_activations` | 지금 무엇이 적용되는가 | upsert / delete | 프로필당 0 또는 1 |
| `etl_profile_activation_events` | 지금까지 무엇을 했는가 | **INSERT만** | 명령마다 1, 계속 누적 |

### 19.2 `[중요]` 이 표가 기록하는 단위

**"상태가 실제로 달라진 순간"이 아니라 "서버가 성공으로 처리한 operator 명령"이다.**

| 요청 | 상태 변화 | event |
| --- | --- | --- |
| `PUT {"active_version": "2"}` | 있음 | `activate` 1건 |
| 같은 `PUT`을 한 번 더 | **없음** | `activate` 1건 더 |
| `PUT {"active_version": null}` | 있음 | `deactivate` 1건 |
| 이미 비활성인데 같은 `PUT` | **없음** | `deactivate` 1건 더 |
| `DELETE` | 있음 | `reset` 1건 |
| override 없는데 `DELETE` (idempotent 200) | **없음** | `reset` 1건 더 |
| 없는 프로필 / 없는 버전 / 401 / 403 | 없음 | **없음** |

즉 **state idempotency ≠ audit event idempotency**다. API가 idempotent한 것은 결과 상태에 대한 성질이고, 이 표가 답하는 질문은 "누가 무엇을 시도해서 서버가 받아들였는가"이다. 같은 명령을 두 번 내린 것은 실제로 두 번 일어난 일이다.

실패한 요청은 아무것도 남기지 않는다. 검증(allowlist, 보존 버전)은 지금도 쓰기 트랜잭션을 열기 **전에** 끝나므로, 없는 프로필/버전이 이 표에 흔적을 남길 수 없다. 401/403은 애초에 service까지 도달하지 않는다.

### 19.3 스키마

`alembic/versions/20260823_0015_create_etl_profile_activation_events.py`

| 컬럼 | 뜻 |
| --- | --- |
| `id` | BigInteger PK |
| `profile_id` | 어떤 allowlist 프로필에 대한 명령인가 (**FK 없음**) |
| `action` | `activate` / `deactivate` / `reset` |
| `deployment_active_version` | 명령 성공 시점의 배포 기본값 snapshot |
| `runtime_override_exists` | 명령 직후 override 존재 여부 |
| `runtime_active_version` | 명령 직후 runtime override 버전 |
| `effective_active_version` | 명령 직후 실제로 신규 실행에 쓰이는 버전 |
| `actor_user_id` | `users.id`, `ON DELETE SET NULL` |
| `actor_username` | 이름 snapshot |
| `created_at` | `timestamptz`, `server_default now()` |

네 상태 값은 모두 **snapshot**이다. 나중에 registry를 다시 읽어 계산하면 배포 기본값이 바뀔 때 과거 기록의 뜻이 조용히 달라진다.

`profile_id`에 FK를 걸지 않는 이유는 `etl_profile_activations`와 같다. 프로필은 아직 DB entity가 아니라 코드 registry의 key이고, allowlist 검증은 application service가 한다.

**제약**: `profile_id` 공백 금지, `action` 세 값, 세 버전 컬럼은 `NULL` 또는 trim 후 non-empty. 여기에 더해 **명령과 그 직후 상태가 모순되는 row를 막는다.**

```text
activate   : override 있음 AND runtime IS NOT NULL AND effective = runtime
deactivate : override 있음 AND runtime IS NULL     AND effective IS NULL
reset      : override 없음 AND runtime IS NULL     AND effective IS NOT DISTINCT FROM deployment
```

reset을 `=`로 비교하지 않는다. 배포 기본값 자체가 비활성이면 양쪽이 `NULL`인데, PostgreSQL에서 `NULL = NULL`은 참이 아니라 `NULL`이고 CHECK는 `NULL`을 통과시켜 제약이 **조용히 무력화**된다. `IS NOT DISTINCT FROM`이 그 경우까지 정확히 본다.

**index**: `(profile_id, created_at, id)`. 주 조회가 "한 프로필의 최신 event부터"이고, PostgreSQL은 B-tree를 역방향으로도 훑으므로 내림차순 전용 index를 따로 만들지 않았다.

### 19.4 `[중요]` migration은 과거를 만들어 내지 않는다

`upgrade()`는 **빈 표를 만든다.** 기존 `etl_profile_activations` row를 보고 과거 event를 채우지 않는다.

그 row 하나로는 누가 처음 활성화했는지, 몇 번 바꿨는지, 언제 내렸다 올렸는지 **알 수 없기 때문이다.** 모르는 것을 추측해 채우면 없는 기록보다 나쁜 **틀린 기록**이 남고, 나중에 읽는 사람이 그것을 사실로 믿는다.

그래서 이력은 `20260823_0015` 적용 **이후의 명령부터** 시작한다. 화면과 API 문서도 그렇게 말한다("이 기능이 추가된 이후 성공한 운영 명령만 표시합니다"). `downgrade()`는 이 표와 index만 지우고 `etl_profile_activations`는 건드리지 않는다.

### 19.5 `[중요]` 상태 변경과 기록은 같은 트랜잭션이다

```python
with session.begin():
    <current-state upsert 또는 delete>
    <같은 트랜잭션에서 resolve>
    <event INSERT>
```

두 쓰기를 나누면 둘 중 하나가 반드시 생긴다.

- 상태만 바뀌고 기록이 없다 → "기록에 없으니 아무도 안 했다"가 거짓이 되어 이력을 믿을 수 없다
- 기록만 있고 상태가 안 바뀌었다 → 일어나지 않은 일이 기록에 남는다

event가 담는 상태는 같은 트랜잭션 안에서 `resolve_etl_profile_activation()`으로 얻는다. effective 계산을 여기서 다시 구현하지 않는다는 규칙은 그대로다. `_record_activation_event()`는 `session.add()`만 하고 **commit하지 않는다.** 트랜잭션 경계는 `set_`/`reset_`이 소유한다.

`reset_etl_profile_activation()`은 이번에 actor를 받도록 확장됐다. request body가 아니라 인증된 `current_user`에서만 온다.

### 19.6 reset actor: 모순이 아니다

reset 직후 상태는 이렇다.

| 값 | 결과 |
| --- | --- |
| `ETLProfileActivationResponse.actor_username` | `null` |
| `ETLProfileActivationResponse.updated_at` | `null` |
| history의 `reset` event `actor_username` | **남는다** |

두 값은 서로 다른 질문에 답한다. 앞은 "지금 이 override를 만든 사람"이고(override 자체가 없으므로 없음), 뒤는 "그 override를 지운 명령을 내린 사람"이다. current-state 응답 계약은 그대로 유지된다.

같은 이유로 reset event를 화면에서 "비활성화"로 표시하지 않는다. override가 사라졌을 뿐이고, 배포 기본값이 활성이면 그 프로필은 reset과 동시에 실행 가능해진다. 화면은 `배포 기본값으로 되돌리기 / 실제 적용 버전: v2`처럼 둘을 함께 보여 준다.

### 19.7 API

```text
GET /api/v1/etl-profiles/{profile_id}/activation/history?limit=&offset=
```

| 항목 | 값 |
| --- | --- |
| 권한 | viewer 이상 (operator 포함). 새 role 없음 |
| pagination | `limit` 기본 20 (1~100), `offset` 기본 0 |
| 정렬 | `created_at DESC, id DESC` |
| 없는 프로필 | 404 |
| 잘못된 pagination | 422 |
| 빈 이력 | 200 + 빈 목록 (오류 아님) |

응답 item은 `event_id`, `profile_id`, `action`, 네 상태 값, `actor_username`, `created_at`이다. **`actor_user_id`는 노출하지 않는다** — DB 관계용 ID이고, 운영자에게 필요한 것은 사용자가 삭제된 뒤에도 남는 이름 snapshot이다.

기존 `PUT`/`DELETE` 응답에는 이력을 끼워 넣지 않았다. `ETLProfileActivationResponse` 계약은 그대로다.

### 19.8 append-only는 애플리케이션 계약이다

이 표에 대한 **UPDATE / DELETE / purge API를 만들지 않았다.** 쓰기 경로는 INSERT 하나뿐이고, client에도 조회 method 하나만 있다.

정확히 말해 두면, DB superuser가 직접 SQL을 실행하는 것까지 막는 WORM/immutable 저장소는 이번 범위가 아니다. append-only는 **애플리케이션이 지키는 계약**이다.

retention/purge 정책도 만들지 않았다. event가 계속 누적된다는 것이 append-only의 뜻이다. 현재 프로필 수와 운영 명령 빈도에서는 pagination + profile index로 충분하고, 대규모 운영에서 필요해지면 별도 Phase로 둔다.

### 19.9 동시성

기존 정책을 바꾸지 않았다. current-state mutation은 여전히 **last-write-wins**이고, optimistic lock도 version 컬럼도 `SELECT FOR UPDATE`도 serializable isolation도 더하지 않았다. history 도입이 activation의 동시성 의미를 바꾸지 않는다.

동시에 실행된 명령은 각각 성공하면 각각 event가 생긴다. 정렬은 `created_at DESC, id DESC`로 **결정적**이지만, 이것을 분산 환경의 절대적 인과 순서로 읽으면 안 된다. `created_at`은 트랜잭션 시각이고 `id`는 시퀀스 발급 순서라, 커밋 순서와 어긋날 수 있다.

### 19.10 Streamlit

"ETL 프로필 운영 관리" 아래에 read-only 구획 하나를 더했다.

- 선택한 관리 프로필의 이력만, 최신순으로
- 표시: 시각 / 동작 / 런타임 결과 / 실제 적용 버전 / 배포 기본 버전 / 사용자
- 동작 문구는 `버전 활성화` / `비활성화` / `배포 기본값으로 되돌리기` (원본 `action` 문자열은 API 계약으로 유지)
- 기록이 없으면 오류가 아니라 안내로 보여 준다
- pagination은 기존 ETL 이력과 같은 helper(`calculate_etl_pagination`)를 재사용하고, state key는 `etl_profile_admin_history_*`
- 프로필을 바꾸면 첫 페이지로 되돌린다
- viewer도 읽는다. 쓰기 control은 지금처럼 operator에게만 보인다

activate/deactivate/reset 성공 뒤에는 **기존 공통 경로**(`_commit_etl_profile_activation_change()`) 한 곳에서 이력 캐시까지 함께 비운다. 같은 무효화를 세 군데 복사하면 나중에 한쪽만 고쳐져 이력만 옛 화면으로 남는다.

이력 조회가 실패해도 관리 화면 전체가 사라지지 않는다. 현재 상태 확인과 조작은 계속 쓸 수 있고, 오류는 이력 구획 안에서만 기존 helper로 표시한다(서버 원문·토큰·비밀은 노출하지 않는다).

### 19.11 `[한계]` registry에서 사라진 프로필의 이력

이력 조회도 **현재 allowlist**를 기준으로 검증한다. registry에서 완전히 제거된 과거 프로필의 event는 표에 남아 있어도 이 API로는 읽을 수 없다(404).

registry가 allowlist이고 그 밖의 값을 DB row 하나로 되살리면 allowlist가 방어선이 아니게 되기 때문이다. 실제로 프로필을 제거하는 일이 생기면 별도 조회 경로를 설계해야 한다.

### 19.12 이번에 바뀌지 않은 것

- `PUT {"active_version": null}` = 명시적 비활성, `DELETE` = reset. 두 뜻 모두 그대로
- `GET`/`PUT`/`DELETE`의 응답 계약과 `ETLProfileActivationResponse` schema
- effective 계산 위치. 계속 `resolve_etl_profile_activation()` 한 곳뿐이다
- current-state 표의 스키마와 동시성 정책(last-write-wins)
- `INSPECTION_VERSION`, `PREVIEW_SCHEMA_VERSION`, profile semantic version, dedup identity, 프로필 JSON
- Airflow DAG, S3/HTTP의 fetch 전 사전 검사, 실패 코드 우선순위
- 기존 ETL/promotion audit 구조
- 의존성 (새 패키지 없음)

### 19.13 아직 없는 것

- Profile CRUD(등록·수정·삭제)가 없다. ProfileVersion DB 표도 없다
- 범용 Audit/Event framework를 만들지 않았다. 이 표는 activation 명령 전용이다
- history retention/purge 정책이 없다 — 19.8
- 여러 프로필의 이력을 한 번에 보는 조회가 없다
- 이 화면의 Chromium E2E가 없다. AppTest로만 검증한다
- 과거 배치의 런타임 재현은 여전히 없다(16.4)

---

## 참고

- `docs/etl_mvp.md` — 프로필 형식, dedup 기준, 웹 ETL 흐름, allowlist 보안 모델
- `etl/profile_loader.py` — `_ETL_PROFILE_REGISTRY`, `get_profile_path()`, `load_profile()`, `get_etl_profile_detail()`
- `etl/db_loader.py` — `load_standard_csv()`의 dedup 처리
- `db/models.py` — `ETLLoadRun`과 `ux_etl_load_runs_input_profile_version`
- `80e8ea4` — `profile_version`을 `"1"`에서 `"2"`로 올린 커밋과 그 근거
- `973882e` — Read-only Profile Detail 추가 커밋
