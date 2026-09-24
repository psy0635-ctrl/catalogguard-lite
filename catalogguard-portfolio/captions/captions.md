# CatalogGuard Lite — 포트폴리오 증거 화면 캡션

기준: main `2fb0594243a5ced1f5c7e583ebb4369e9c7efed8` · 합성 fixture · 로컬 데모 DB

| 번호 | 파일 | 화면과 강조점 | 포트폴리오 캡션 |
|---|---|---|---|
| 1 | 01_readme_overview.png | GitHub README 첫 화면, 프로젝트 목적 | 상품 카탈로그 CSV를 등록하기 전에 필수값, 가격, 중복, 카테고리, 개인정보 의심 패턴을 검사합니다. 공급사 ETL부터 검수 결과 저장과 비교까지 연결한 프로젝트입니다. |
| 2 | 02_etl_upload.png | ETL 적재 이력 → ETL 실행, 패션 공급사 프로필, CSV/XLSX 업로드 | 공급사별 컬럼을 선택한 ETL 프로필에 따라 공통 상품 형식으로 변환합니다. 웹 업로드 경로에서 CSV와 XLSX를 받습니다. |
| 3 | 03_etl_summary.png | 배치 1, 전체 3행·정상 2행·reject 1행 | 변환 가능한 행은 staging에 적재하고, 규칙에 맞지 않는 행은 전체 작업을 실패시키지 않고 reject로 분리합니다. |
| 4 | 04_etl_reject_detail.png | 원본 행 3, 오류 코드·이유·마스킹 원본 | 거부한 행에 오류 코드와 이유를 남겨 원인을 확인할 수 있습니다. 원본 값은 화면에서 마스킹해 보여줍니다. |
| 5 | 05_inspection_upload.png | CSV 검수, products_dev.csv, 상품 미리보기 | 업로드한 상품 CSV를 먼저 미리 보고 검수 규칙에 전달합니다. Inspection 업로드는 CSV를 사용합니다. |
| 6 | 06_inspection_result.png | run 1, 상품 5개·issue 6건, 이유·권장사항 | 어느 상품의 어떤 값이 문제인지와 사용자가 확인할 수정 방향을 함께 보여줍니다. 수정 작업표는 원본 행별 참고 자료이며 재업로드 파일은 아닙니다. |
| 7 | 07_comparison.png | 원본 run 1 → 수정본 run 2, common 5·base_only 1·target_only 0 | 같은 검수 버전의 두 실행에서 공통 문제와 각 실행에만 존재하는 문제를 구분합니다. 시스템은 차이를 자동으로 개선이나 악화로 단정하지 않습니다. |
| 8 | 08_trend.png | 버전 15, 서울 날짜 2026-09-24, 실행 2·상품 10·issue 11 | 저장된 검수 실행을 현재 검수 버전과 서울 날짜 기준으로 집계해 품질 변화를 이력으로 확인합니다. |
| 9 | 09_golden_ci.png | 기존 Actions run #35808803669의 5개 성공 job | 검수 규칙은 Golden fixture의 예상 결과와 비교해 회귀를 확인합니다. GitHub Actions에서는 테스트, 브라우저, Kubernetes, Terraform, Airflow 검증을 나누어 실행했습니다. Golden의 실제 출력은 `../demo-notes/golden-regression.txt`에 별도로 보관했습니다. |

9번 이미지는 GitHub Actions 화면입니다. Golden 테스트 출력은 별도 텍스트 증거이며 이미지 안에 합성하지 않았습니다. Golden 결과는 `2 passed`이고 fixture는 39행, 예상 issue는 31건, 활성 issue code는 24/24입니다. 이를 정확도 100%로 표현하지 않습니다.
