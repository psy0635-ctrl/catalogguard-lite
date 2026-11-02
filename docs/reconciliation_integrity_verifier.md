# 상품 동기화 CSV·JSON 오프라인 무결성 확인

CatalogGuard Lite의 **상품 동기화 차이** 화면에서 한 번 준비한 CSV와 `.integrity.json`을
각각 다운로드한 뒤, 네트워크 접속 없이 **동일한 파일 쌍인지 확인**하는 CLI입니다.

- 새 스크립트: `scripts/verify_reconciliation_export.py`
- 필요한 환경: Python 3.11 이상. **추가 라이브러리·DB·API·Docker가 필요하지 않습니다.**
- 동작: 두 파일을 읽기만 합니다. 상품 데이터, 인증정보, 검증 결과를 서버로 보내거나 수정하지 않습니다.
- 지원 범위: 기존 reconciliation export의 `schema_version=1`, 9개 필드와 상태 코드 5개.

## 1. 실행 방법 (Windows PowerShell)

1. Streamlit의 **상품 동기화 차이 전체 CSV 준비**를 실행하고, CSV와
   **CSV 무결성 검증 보고서** JSON 두 파일을 같은 폴더에 다운로드합니다.
2. VS Code 터미널 또는 Windows PowerShell에서 프로젝트 폴더로 이동합니다.
3. 실제 다운로드 파일명과 위치에 맞게 다음 명령을 실행합니다.

```powershell
cd C:\study\catalogguard-lite
python scripts/verify_reconciliation_export.py `
  --csv "C:\Users\사용자\Downloads\catalogguard_reconciliation_42_changed.csv" `
  --manifest "C:\Users\사용자\Downloads\catalogguard_reconciliation_42_changed.integrity.json"
```

위 `42_changed`는 **예시**입니다. 실제 다운로드한 배치 ID와 상태 코드를 사용해야 합니다.
Windows에서 `python` 명령이 없다면 Python 3.11이 설치된 경로의 실행 파일을 지정합니다.

성공 출력:

```text
검증 성공: CSV와 JSON의 SHA-256·행 수·열·파일명이 일치합니다.
주의: 파일 일치는 상품 데이터의 정확성이나 작성자의 신원을 증명하지 않습니다.
```

불일치·손상·형식 오류는 `검증 실패`로 표시되며, 명령의 종료 코드는 `1`입니다.
`0`은 파일 검증 성공, `2`는 잘못된 CLI 옵션 사용을 의미합니다. 실패 화면에
CSV의 상품 원문·개인정보·토큰을 출력하지 않습니다.

## 2. 무엇을 확인하나요?

- CSV 파일명·배치 ID·상태 코드와 JSON 파일명 조합
- JSON 9개 필드·지원 스키마·중복 필드·올바른 타입·UTC 생성 시각
- 실제 CSV 바이트 전체의 SHA-256과 JSON의 `csv_sha256` (UTF-8 BOM 포함)
- CSV의 실제 헤더 열 3개와 순서, 데이터 행 수 (셀 내부 줄바꿈은 한 행으로 셈)
- 기존 상태 `all`, `new`, `changed`, `unchanged`, `not_observed_in_batch`

잘못되거나 64 KiB를 초과하는 JSON은 거부하며, CSV는 블록 단위로 해시를 계산합니다.
JSON을 인식하지 못하거나 CSV 구조가 깨져 있으면 성공으로 처리하지 않습니다.

## 3. 보안 및 한계

이 기능은 **파일 쌍의 일치 확인**이지 **상품 데이터 정확성 평가**가 아닙니다.
CSV와 JSON을 모두 다시 생성한 공격자는 일치하는 해시를 만들 수 있으므로
전자서명·출처 인증·악의적인 동시 변조 방지는 지원하지 않습니다.

여러 페이지 API를 동시에 조회할 때 단일 시점 Snapshot을 보장하지 않는 기존 한계,
CSV 준비 5,000건 상한도 그대로입니다. 이 도구는 운영 DB에 연결하거나 데이터를 변경하지 않습니다.
검증 중에는 다른 프로그램에서 두 파일을 편집하거나 교체하지 마세요. 파일 잠금이나
동시 변경 방지를 제공하지 않으며, CSV 해시 계산과 구조 검사는 별도로 파일을 읽습니다.

## 4. 테스트

프로젝트 루트의 PowerShell에서 다음을 실행합니다.

```powershell
python -m pytest tests/test_reconciliation_export_verifier.py -q
```

정상·변조·잘못된 JSON 필드·CSV BOM·행 수·파일명·종료 코드 등을 확인합니다.
GitHub Actions PR 테스트에도 기존 `test` Job의 일반 pytest 범위로 포함됩니다.

### 2026-11-02 학교 PC 로컬 검증

Windows, `.venv-e2e` Python 3.11.9에서 실제 실행한 결과입니다.

| 명령 | 결과 |
| --- | --- |
| `.\.venv-e2e\Scripts\python.exe -m pytest tests/test_reconciliation_export_verifier.py -q` | 36 PASS, FAIL/SKIP 0 |
| `.\.venv-e2e\Scripts\python.exe -m pytest tests/test_result_exporter.py tests/test_reconciliation_export_verifier.py -q` | 73 PASS, FAIL/SKIP 0 |

제공 ZIP의 첫 실행은 26 PASS, 1 FAIL이었습니다. CLI 테스트의 UTF-8 출력과 Windows
기본 CP949 디코딩 불일치를 수정하고, 깊게 중첩된 JSON 거부 및 기존 CSV·JSON 생성기와의
상태 코드 5종 호환성, 입력 파일 보존, 헤더 순서, 0행, JSON 누락 검증을 추가했습니다.

합성 파일만 있는 독립 임시 폴더에서 실제 CLI 10개 시나리오도 확인했습니다.
정상 쌍은 종료 코드 0, CSV 한 글자 변경·JSON 해시 변경·CSV 행 추가·헤더 변경·잘못된
JSON·CSV 누락·JSON 누락·깊은 중첩 JSON은 1, 필수 옵션 누락은 2였습니다.
행·헤더 검증 시에는 수정한 CSV의 해시도 갱신해 각 검사를 독립적으로 확인했습니다.
`python -I -S -X utf8` 실행으로 외부 패키지 없이 동작함을 확인했고 입력 파일의 실행 전후
SHA-256이 같았습니다. 전체 통합·브라우저 E2E·운영 데이터 검증·원격 CI는 실행하지 않았습니다.
