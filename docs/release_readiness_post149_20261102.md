# PR #149 이후 Release 준비 상태 분석

## 기준과 결론

2026-11-02 확인 기준 최신 공식 Release는 [v0.3.0](https://github.com/psy0635-ctrl/catalogguard-lite/releases/tag/v0.3.0), 비교 대상 main은 [`b5f7ed560dfce4b19c611bccbfe5ce9735483b52`](https://github.com/psy0635-ctrl/catalogguard-lite/commit/b5f7ed560dfce4b19c611bccbfe5ce9735483b52)이다. 이 보고서는 해당 시점의 스냅샷이며 이후 문서 커밋이나 main 이동까지 숫자에 포함하지 않는다.

**추천은 신규 마이너 Release 준비다. 후보는 `v0.4.0`이며, 현재 즉시 발행을 권하지 않는다.** 기능 추가 범위가 패치 Release로 설명하기에는 크다. 운영 배포 SHA·DB revision·백업 및 복구 검증이 미확인이므로 먼저 릴리스 후보의 호환성·운영 검증 범위를 확정해야 한다. 이번 작업에서는 Release·Tag·Push·PR·운영 배포를 수행하지 않는다.

## 실제 비교 범위

| 항목 | 확인 결과 |
|---|---|
| 최신 공식 Release | v0.3.0, 2026-09-15 게시; 정식 Release이며 draft/prerelease 아님 |
| v0.3.0의 실제 Tag 대상 | `b2f809b3c1214a3cfcdcc8cd21b732a9ae48a152` |
| 비교 main | `b5f7ed560dfce4b19c611bccbfe5ce9735483b52` |
| GitHub Compare | ahead 68, behind 0; 112개 변경 파일 = **신규 18 + 수정 94**, 삭제 0 |
| Git 교차 확인 | `git rev-list --count v0.3.0..origin/main` = 68; `git diff --shortstat v0.3.0...origin/main` = 112 files, 14,806 insertions, 451 deletions |
| 검수 결과 버전 | Release의 `INSPECTION_VERSION="14"` → main의 `"18"` |
| Alembic | Release `20260908_0019` → main `20260915_0020` |
| 추가 API 의존성 | `openpyxl==3.1.5`, `defusedxml==0.7.1`; 두 비교 커밋 사이에서 다른 requirements 파일은 변경 없음 |

근거: [고정 SHA 간 GitHub 비교](https://github.com/psy0635-ctrl/catalogguard-lite/compare/v0.3.0...b5f7ed560dfce4b19c611bccbfe5ce9735483b52), [v0.3.0 Release 본문](https://github.com/psy0635-ctrl/catalogguard-lite/releases/tag/v0.3.0), [현재 API 의존성](../requirements-api.txt). Release의 `targetCommitish=main`이라는 문자열 대신 Tag가 실제 가리키는 커밋을 사용했다. 112는 신규 파일 수가 아니며, 비교 양 끝에서의 파일 차이다.

## 주요 변경과 확인한 근거

| 분류 | v0.3.0 이후 주요 변경 | 코드·커밋 근거 |
|---|---|---|
| 데이터·규칙 | duplicate 관계 행을 명시 저장하고 legacy NULL은 기존 fallback 유지. 상품 그룹 이름 일관성·카테고리/사이즈 호환 검수와 검수 버전 변경 | [관계 행 저장 커밋](https://github.com/psy0635-ctrl/catalogguard-lite/commit/146064b), [검수 버전 정책](inspection_version_policy.md), [규칙 구현](../core/rules.py) |
| 개인정보·인증 | v18 reason 저장 및 legacy 출력 경계 마스킹, 계좌 의심 값 보호. 로그인 rate limiting·인증 관측 metric 추가 | [PR #142](https://github.com/psy0635-ctrl/catalogguard-lite/pull/142), [rate limiter](../services/login_rate_limiter.py), [인증 route](../api/routes/auth.py) |
| Web ETL | CSV 외 XLSX multipart 업로드, 저장 전 Preflight와 파일 교체 후 오류 복구. reserved rejection metadata header 차단 | [XLSX 추가](https://github.com/psy0635-ctrl/catalogguard-lite/commit/ebce0e6), [Preflight 추가](https://github.com/psy0635-ctrl/catalogguard-lite/commit/425fb1c), [Web ETL service](../etl/web_service.py) |
| 조회·내보내기 | 공급사 vocabulary coverage·unknown token 상품 drilldown/페이지/CSV, 오류 코드별 reject 조회·CSV. Reconciliation 상태 필터 → 전체 CSV → JSON → 오프라인 CLI | [공급사 coverage](https://github.com/psy0635-ctrl/catalogguard-lite/commit/d50315b), [거부 행 CSV](https://github.com/psy0635-ctrl/catalogguard-lite/commit/7b3f15e), [Reconciliation 계약](catalog_reconciliation.md), [PR #149](https://github.com/psy0635-ctrl/catalogguard-lite/pull/149) |
| 테스트·실행 환경 | Golden Rule Quality Regression, schema-aware readiness, PostgreSQL 개인정보 개별 결과 확인과 실제 Chromium 다운로드·CLI 검증. XLSX lazy import로 CSV-only Airflow runtime 격리 | [Golden fixture](../tests/quality/test_rule_quality_golden.py), [readiness](../db/session.py), [Airflow 격리 수정](https://github.com/psy0635-ctrl/catalogguard-lite/commit/bd04f6e), [CI](../.github/workflows/test.yml) |
| 문서·설정 | MVP 검증 근거·기능 동결·시연 절차·후속 PR별 포트폴리오. Compose JWT 설정 및 업로드 제한 안내 정합성 보완 | [MVP 기록](mvp_validation.md), [시연 런북](demo_runbook.md), [환경변수 예시](../.env.local.example) |

68개 커밋을 개별 나열하지 않았으며, 위 항목은 실제 커밋·파일 차이가 있는 범위만 요약했다. Kubernetes·Terraform·Airflow 전체를 이번 Release 이후 새로 만든 기능으로 소급하지 않는다. 기존 인프라가 최신 코드에서도 동작하는지는 CI의 제한된 시나리오로 확인한다.

## 호환성·배포 위험

| 영역 | 실제 변경과 위험 | Release 전 확인 |
|---|---|---|
| DB migration | 새 revision 하나가 `inspection_results.related_source_rows` nullable JSONB와 array/NULL CHECK를 추가한다. backfill은 없다. additive schema이지만 운영 migration의 lock·권한·소요 시간은 미검증 | [migration](../alembic/versions/20260915_0020_add_inspection_related_source_rows.py)을 운영 복제/복구 DB에서 적용하고 결과·권한·소요 시간 확인. downgrade는 컬럼을 제거하므로 무손실 복구 수단으로 간주하지 않음 |
| 검수 결과·과거 데이터 | v14와 v18은 같은 파일에도 다른 run이 생길 수 있고, 다른 inspection version 간 비교는 거부한다. 과거 reason은 DB에서 보존하면서 출력 시 보호 | 버전별 dedup·이력·비교·legacy NULL 경로 확인. 과거 데이터를 자동 갱신하거나 전체 재검수하지 않음 |
| API 동작 | 조회 endpoint·Preflight가 추가됐다. `/ready`는 DB 연결뿐 아니라 revision 일치도 요구해 불일치 시 503이다. limiter 활성화 시 로그인 429가 추가되고 출력 reason은 마스킹될 수 있음 | 기존 Client의 오류 처리·nullable 필드·응답 계약과 배포 순서 확인. route가 유지된다는 사실만으로 완전한 하위 호환을 단정하지 않음 |
| 의존성 | API runtime에 openpyxl·defusedxml이 추가됐다. XLSX는 Web multipart만 지원하며 CLI·S3·HTTP feed·Airflow는 CSV-only. Airflow에는 lazy import 격리가 필요 | 실제 배포 이미지의 설치 파일·import 경로·XLSX 제한을 격리 환경에서 확인 |
| 설정·Redis | `.env.example`에 로그인 제한 설정 4개가 추가됐다. 기본 비활성이며 활성화 시 `REDIS_JOB_URL`을 사용한다. Redis 연결/timeout 시 인증을 계속하는 fail-open 정책과 metric이 있음. Compose는 JWT secret 명시가 필요 | 실제 설정값을 공개하지 않고 이름·활성 여부·Redis 도달성·proxy IP 정책 확인. 모든 환경에 rate limit이 적용된다고 홍보하지 않음 |
| 배포 실행 명령 | [Dockerfile.aws](../Dockerfile.aws)는 시작 시 migration을 실행하고, README Railway 구성도 pre-deploy migration을 포함한다 | 백업·복구 및 schema 적용 순서를 먼저 검토. 이번 분석에서 기존 서버를 시작하거나 재배포하지 않음 |
| 내보내기 | CLI 자체는 추가 DB/API/패키지·쓰기·전송이 없다. CSV 준비는 최대 5,000건의 메모리 기반 수집이며 Snapshot Token이 없음 | 실제 운영 부하·단일 시점 정합성·발행자 인증을 이번 성공으로 확대하지 않음 |

종합 위험은 **PR #149 단독보다 v0.3.0 → 최신 main 전체 배포에서 더 크다**. nullable migration만 있는 것으로 끝나지 않고 검수 결과 버전·readiness·인증 제한·의존성·출력 정책이 함께 달라진다. 실운영 호환성과 복구 확인 전에는 배포 준비 완료로 판단하지 않는다.

## 검증 근거와 미검증 영역

| 실행 시점·범위 | 확인한 결과 |
|---|---|
| PR #149 병합 후 main | [Run 41403060834](https://github.com/psy0635-ctrl/catalogguard-lite/actions/runs/41403060834), 위 main SHA의 push 이벤트. `test`, `browser-e2e`, `kubernetes-smoke`, `terraform-validate`, `airflow-smoke` 모두 **completed / success** |
| 2026-11-02 병합 후 로컬 main | Windows Python 3.11.9, 내보내기·신규 검증기 회귀 **73 PASS, FAIL/SKIP 0** |
| 같은 날 병합 전 독립 통합 | 새 PostgreSQL 18.6·실제 FastAPI·Streamlit·Playwright Chromium의 다운로드 E2E **1 PASS**. CSV·JSON 다섯 쌍(전체 208행·네 상태 각 52행), 정상 종료 0·변조/잘못된 입력 1·원본 보존 |

이들은 별도 실행이며 합산하지 않는다. 이번 문서 작업에서는 기능·전체 pytest·브라우저 테스트를 재실행하지 않았다. 최신 전체 pytest 건수는 해당 CI 원문에서 새로 확인하지 않았으므로 **CI 5/5 성공**만 표시한다. 과거 문서의 날짜별 전체 테스트 수치는 당시 기록이다.

독립 통합의 일회성 보조 스크립트는 마지막 테이블명 오타로 종료 코드 1을 반환했다. 기능 테스트는 앞서 통과했고 별도 읽기 전용 조회로 Fixture 0건·신규 자원 정리를 확인했다. 이를 보조 스크립트 전체 성공으로 표시하지 않는다. 상세 경위는 [포트폴리오 PR #149 기록](portfolio_project.md#630-오프라인-무결성-검증기-pr-149)에 보존했다.

CI는 합성 테스트 DB·Chromium, kind, Terraform mock provider, 격리 Airflow의 계약 검증이다. 실제 공급사 호환성·운영 데이터 정확성·운영 규모 성능·장기 안정성·Firefox/WebKit·실제 AWS `terraform apply` 결과를 입증하지 않는다. SHA-256은 파일 대응 확인이며 전자서명·출처 인증·동시 변조 방지가 아니다.

## 운영 배포 상태

| 출처 | 확인 결과 | 해석 |
|---|---|---|
| Railway 연결 | 프로젝트 조회 시 재인증 필요(`UNAUTHORIZED`) | 현재 서비스·배포 SHA·DB revision·설정·의존성을 조회하지 못함. 접근을 우회하거나 변경하지 않음 |
| GitHub Deployment 기록 | 조회된 최신 레코드는 2026-08-09, `railway-app[bot]`, SHA `56a40766eb359f27a2a2e77df28eb7e763d4c2b5`; 이 레코드의 최신 상태는 8월 10일 `inactive` | [과거 레코드](https://api.github.com/repos/psy0635-ctrl/catalogguard-lite/deployments/5816634137)는 현재 실제 Railway 배포 SHA의 증거가 아님 |
| Streamlit | [공개 앱 URL](https://catalogguard-lite-p6jtwmdhwqcapphpghfzduo.streamlit.app/)은 기존 문서에 있음. 현재 배포 Commit 조회 근거는 없음 | 접속 가능 여부와 최신 main 배포를 동일시하지 않음. 현재 SHA·PR #149 반영 여부 미확인 |
| 저장소 설정 | [README의 Railway 구성 기록](../README.md#railway-fastapi-배포-설정), API 의존성·migration·Client 코드 확인 | 구성 예시가 현재 production 설정이나 적용 완료를 증명하지 않음 |

**운영 반영 여부는 미확인이다.** 공개 서비스에 업로드·로그인·migration·설정 변경·재배포·재시작을 수행하지 않았다. 최신 main의 오프라인 CLI는 내려받은 로컬 소스에서 사용할 수 있지만 운영 UI가 대응 CSV·JSON을 생성하는지는 별도로 확인해야 한다.

## Release 선택지

| 선택 | 사용자 가치·포트폴리오 | 범위·호환성·배포 난이도 | 테스트 신뢰도·유지관리 부담 | 판단 |
|---|---|---|---|---|
| A. v0.3.0 유지 | 현재 안정 기준은 유지하나 최신 검증 기능을 공식 산출물로 제공하지 못함 | 즉시 변경 위험은 낮음. Release·main·운영 차이를 계속 설명해야 함 | 새 CI 결과는 main에만 적용됨. 두 기준의 문서 관리 부담 지속 | 검증 준비 중의 현 상태로는 타당하나 장기 전략으로는 부족 |
| B. 신규 패치 Release | 소규모 수정 전달에는 적합하나 XLSX·Preflight·조회/내보내기·검수 버전 변경을 충분히 설명하기 어려움 | 후보 범위를 일부 수정만으로 별도 선정하지 않는 한 실제 변화가 큼. 배포 위험이 버전 이름 때문에 줄어들지 않음 | 제한한 패치 범위를 다시 검증해야 하며 지원 기준이 하나 더 생김 | 이번 전체 변경 묶음에는 비추천 |
| C. 신규 마이너 Release 준비 | 새 사용자 흐름과 실패 입력 검증을 공식 기준으로 소개할 수 있고 취업용 재현 근거도 선명해짐 | migration·출력/버전 정책·새 의존성 확인이 필요해 준비 비용이 가장 큼 | main CI와 독립 통합 증거가 있으나 운영 차이는 남음. 발행 후 하나의 기준으로 관리 가능 | **추천. 검증 조건 충족 후 발행 판단** |

기존 공식 Release는 `v0.1.0` → `v0.2.0` → `v0.3.0`으로 기능 확장 때 minor 숫자를 올렸지만, 저장소에서 제품 Release용 엄격한 Semantic Versioning 정책은 찾지 못했다. `INSPECTION_VERSION`과 ETL profile version 정책은 별도이며 제품 Release의 SemVer 정책으로 해석하지 않는다. 따라서 `v0.4.0`은 기존 이력과 변경 범위에 근거한 **검토 후보**이고, 정책 확정·Tag 생성·Release 약속이 아니다.

## 다음 최우선 작업과 발행 전 조건

**가장 먼저 실제 Railway·Streamlit 배포 SHA와 DB revision을 읽기 전용으로 확인한다.** 현 배포가 v0.3.0인지 그보다 오래된 코드인지도 확정되지 않아, main과의 차이·적용할 migration·필요 설정을 정확히 정할 수 없기 때문이다. 사용자 연결이 복구되면 Codex에서 이 인벤토리를 이어서 작성할 수 있다.

그 결과를 기준으로 다음 순서로 Release 준비를 진행한다. 아래는 제안이며 이번에 실행한 작업이 아니다.

1. 실제 배포 SHA·DB revision·환경변수 이름·설치 의존성을 비밀 값 없이 기록하고 고정 후보 SHA와 비교한다.
2. 백업과 복구가 가능한 독립 복제/테스트 DB에서 필요한 migration·새 API 이미지·동일 버전 UI의 호환성과 read-only 조회를 검증한다. 단순 downgrade를 복구 계획으로 대체하지 않는다.
3. 후보 SHA에 CI 5/5 성공과 검수 버전·legacy 데이터·rate limit·Preflight·CSV/JSON 회귀 결과를 연결하고, 실패 시 복구 기준을 확정한다.
4. 별도 배포 승인이 있는 경우에만 반영한다. 이후 `/health`·schema-aware `/ready`·인증된 조회와 기존 합성 배치의 CSV/JSON·오프라인 CLI로 읽기 전용 점검한다. 적절한 합성 배치가 없으면 운영 데이터를 새로 적재하지 않고 미검증으로 남긴다.
5. 공개 가능한 변경사항·호환성·제약을 Release Notes에 정리하고 `v0.4.0` 후보 발행 여부를 별도로 승인받는다. Release 발행과 서비스 배포는 각각 구분해 기록한다.

현재는 준비 상태 분석과 문서 최신화까지 완료했으며, 운영 배포 준비·Release 발행 승인을 대신하지 않는다.
