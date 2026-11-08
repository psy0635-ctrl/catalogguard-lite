# 상품 동기화 CSV·JSON 오프라인 무결성 확인

CatalogGuard Lite의 **상품 동기화 차이** 화면에서 한 번 준비한 CSV와 `.integrity.json`을
각각 다운로드한 뒤, 네트워크 접속 없이 **파일 쌍의 일치 여부를 확인**하는 CLI입니다.
파일 쌍 하나를 지정하거나 폴더에서 여러 쌍을 일괄 검증할 수 있습니다.

- 새 스크립트: `scripts/verify_reconciliation_export.py`
- 필요한 환경: Python 3.11 이상. **추가 라이브러리·DB·API·Docker가 필요하지 않습니다.**
- 동작: 입력 파일을 읽기만 하며 상품 데이터, 인증정보, 검증 결과를 서버로 전송하지 않습니다.
- 지원 범위: 기존 reconciliation export의 `schema_version=1`, 9개 필드와 상태 코드 5개.

## 1. 실행 방법 (Windows PowerShell)

### 파일 쌍 하나 검증

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

### 폴더 일괄 검증

프로젝트 루트에서 다운로드한 파일 쌍을 모아 둔 로컬 폴더를 지정합니다.
`--directory`는 `--csv`, `--manifest`와 함께 사용할 수 없습니다.

```powershell
python -X utf8 scripts/verify_reconciliation_export.py --directory "C:\sample\exports"
```

CSV와 JSON은 각각 `catalogguard_reconciliation_<배치 ID>_<상태>.csv`,
`catalogguard_reconciliation_<배치 ID>_<상태>.integrity.json`이어야 합니다.
배치 ID는 앞에 0이 없는 양의 정수이고, 상태는 아래 검증 항목에 나열된 코드 중 하나입니다.
두 이름에서 확장자를 뺀 부분이 대소문자까지 같아야 합니다.

폴더 최상위에서 `catalogguard_reconciliation_`로 시작하는 이름을 대소문자 구분 없이
찾은 뒤 정확한 파일명 규칙을 적용합니다. 이 접두사가 없는 일반 파일과 일반 하위 폴더는
건너뜁니다. 이름순으로 결과를 출력하고, 일치하는 쌍은 한 건으로 집계합니다.
짝이 없는 파일과 규칙에 맞지 않는 이름도 각각 실패로 집계하며 다음 항목을 계속 검사합니다.
잘못된 파일명에 개인정보가 있을 수 있으므로 해당 결과에는 파일명 대신 항목 번호를 표시합니다.

정상 출력 예시

```text
PASS catalogguard_reconciliation_42_changed.csv
PASS catalogguard_reconciliation_43_all.csv
검사 대상 2건 | 성공 2건 | 실패 0건
```

오류 출력 예시

```text
FAIL catalogguard_reconciliation_42_changed.csv: 대응하는 .integrity.json 파일이 없습니다.
PASS catalogguard_reconciliation_43_all.csv
검사 대상 2건 | 성공 1건 | 실패 1건
```

| 종료 코드 | 의미 |
| --- | --- |
| `0` | 단일 파일 쌍 검증 성공 또는 폴더에서 한 쌍 이상을 검사하고 모든 대상이 성공 |
| `1` | 파일 누락·변조·형식 오류 등 검증 실패. 폴더에 검사 대상이 없어도 이 코드 반환 |
| `2` | 잘못된 CLI 옵션 조합, 필수 옵션 누락 또는 잘못된 `--directory` 입력 경로 |

## 2. 무엇을 확인하나요?

- CSV 파일명·배치 ID·상태 코드와 JSON 파일명 조합
- JSON 9개 필드·지원 스키마·중복 필드·올바른 타입·UTC 생성 시각
- 실제 CSV 바이트 전체의 SHA-256과 JSON의 `csv_sha256` (UTF-8 BOM 포함)
- CSV의 실제 헤더 열 3개와 순서, 데이터 행 수 (셀 내부 줄바꿈은 한 행으로 셈)
- 기존 상태 `all`, `new`, `changed`, `unchanged`, `not_observed_in_batch`

잘못되거나 64 KiB를 초과하는 JSON은 거부하며, CSV는 블록 단위로 해시를 계산합니다.
JSON을 인식하지 못하거나 CSV 구조가 깨져 있으면 성공으로 처리하지 않습니다.

## 3. 보안 및 한계

두 모드 모두 입력 파일을 수정하거나 삭제하지 않으며, 오류 메시지에 CSV의 상품 원문,
개인정보, JSON 필드 값 또는 토큰을 출력하지 않습니다.

폴더 모드는 지정 폴더와 상위 경로, 검증 후보의 심볼릭 링크 및 Windows 재분석 지점
(예를 들어 디렉터리 정션)을 거부합니다. 파일이 여러 하드 링크로 공유된 경우에도
다른 경로의 위치를 확인할 수 없으므로 거부합니다. 안전성을 확인할 수 없는 경로 또는
후보는 실패로 처리합니다. Windows에서는 일반 로컬 드라이브 경로를 사용합니다.

Windows 폴더 모드는 드라이브 문자로 접근할 수 있는 로컬 NTFS에서 동작합니다. UNC,
네트워크 매핑, `SUBST`, 장치 경로와 `..` 구성 요소는 거부합니다. 드라이브 루트부터
지정 폴더까지 각 폴더를 쓰기·삭제 공유 없이 열고, 검증이 끝날 때까지 핸들을 유지합니다.
폴더 목록을 열린 핸들에서 읽고, 파일을 그 폴더 핸들에 상대적으로 열면서 재분석 지점은
따라가지 않습니다. 열린 파일에서 일반 파일 여부, 하드 링크 수, 목록의 파일 식별자와
쓰기 시각을 확인한 뒤에만 내용을 읽습니다. 핸들을 열 수 없거나 이 확인이 실패하면 해당
파일 쌍이나 폴더 검증을 실패로 처리합니다. 상위 폴더를 여는 데 필요한 권한도 있어야 합니다.

이 기능은 **파일 쌍의 일치 확인**이지 **상품 데이터 정확성 평가**가 아닙니다.
CSV와 JSON을 모두 다시 생성한 공격자는 일치하는 해시를 만들 수 있으므로
전자서명·출처 인증·악의적인 동시 변조 방지는 지원하지 않습니다.

여러 페이지 API를 동시에 조회할 때 단일 시점 Snapshot을 보장하지 않는 기존 한계,
CSV 준비 5,000건 상한도 그대로입니다. 이 도구는 운영 DB에 연결하거나 데이터를 변경하지 않습니다.
CSV 해시와 구조 검사는 같은 열린 파일에서 수행합니다. Windows 폴더 모드에서는 읽는
동안 CSV와 JSON의 쓰기·삭제 공유를 차단합니다. 폴더 목록 전체의 단일 시점 스냅샷은
제공하지 않으므로 새 항목이 검증 시작 후 추가될 때는 다시 실행하세요.
단일 파일 모드와 Windows 이외의 폴더 모드에는 이 Windows 핸들 보호가 적용되지 않습니다.
이들 모드는 다른 사용자가 검증 중 입력 경로나 파일을 교체할 수 없는 위치에서 실행하세요.

## 4. 테스트

프로젝트 루트의 PowerShell에서 다음을 실행합니다.

```powershell
python -m pytest tests/test_reconciliation_export_verifier.py -q
```

정상·변조·잘못된 JSON 필드·CSV BOM·행 수·파일명·종료 코드 등을 확인합니다.
폴더 모드는 합성 파일로 다중 쌍 검사, 실패 후 계속 진행, 누락, 이름 불일치,
하위 폴더 제외, 링크 거부, 입력 SHA-256 보존을 확인합니다.
Windows에서는 실제 NTFS에서 목록 수집 후 입력 폴더·상위 폴더의 정션 교체 시도,
CSV·JSON 교체와 수정, 검증 중 쓰기·이름 변경 차단도 검사합니다.
Windows에서 심볼릭 링크 생성 권한이 없으면 실제 CSV·JSON 심볼릭 링크 테스트 두 건은
건너뜁니다. 이 경우 정션과 모의 재분석 속성 검사는 각각 별도로 실행됩니다.
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
