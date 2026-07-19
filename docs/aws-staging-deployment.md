# AWS EC2·RDS staging 배포 런북

## 1. 목적과 범위

이 문서는 CatalogGuard Lite FastAPI를 AWS의 별도 staging 환경에 수동 배포한 절차와 2026-07-19 검증 결과를 기록합니다. 실제 내부 경로는 다음과 같습니다.

```text
AWS ap-northeast-2 / Default VPC
  -> EC2 127.0.0.1:8000 / FastAPI Docker 컨테이너
  -> TLSv1.3 / 5432 / RDS PostgreSQL
```

배포 기준은 `main` 브랜치의 commit `57a713009c7c063f9abb0c9e8f9e1830a1aa086a`이며 Docker image tag는 앞 12자리인 `57a713009c7c`입니다. 해당 commit의 GitHub Actions가 성공했고 테스트 결과는 `696 passed, 25 skipped`였습니다.

Railway FastAPI·PostgreSQL은 production으로 계속 운영합니다. AWS staging은 Railway를 대체하지 않으며 기존 production Streamlit 설정도 변경하지 않았습니다. Railway 데이터 이전, Redis, Celery, AWS 자동 배포는 이번 수동 배포 범위에 포함하지 않았습니다.

개인 도메인, 고정 DNS, Nginx, 정식 외부 HTTPS, Elastic IP, Load Balancer, custom VPC와 private subnet 재구성도 완료되지 않았습니다. 이 문서에서 해당 항목을 설명하더라도 2026-07-19 완료 구성으로 간주하지 않습니다.

## 2. 배포 전 결정과 공식 정보 확인

2026-07-19 배포에 사용한 기준과 결과는 다음과 같습니다.

| 항목 | 실제 값 |
| --- | --- |
| 기준일 | 2026-07-19 |
| 브랜치 | `main` |
| commit | `57a713009c7c063f9abb0c9e8f9e1830a1aa086a` |
| image tag | `57a713009c7c` |
| 리전 | 서울 `ap-northeast-2` |
| RDS | PostgreSQL `18.3-R1`, `db.t3.micro`, Single-AZ, 20 GiB gp2 |
| EC2 | Amazon Linux 2023, x86_64, `t3.micro`, 8 GiB gp3 |
| CI | GitHub Actions 성공, `696 passed, 25 skipped` |
| production 영향 | Railway production과 production Streamlit 설정 변경 없음 |

위 버전과 사양은 배포 당시 값입니다. 재배포하거나 리소스를 재생성할 때는 서울 리전에서 지원되는 버전, 현재 가격, AMI 아키텍처를 다시 확인합니다. 버전은 [RDS PostgreSQL 버전](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-versions.html), 비용은 [AWS Pricing Calculator](https://calculator.aws/)를 기준으로 확인합니다.

Secrets Manager, Parameter Store, CloudWatch, Redis, Celery는 도입하지 않았습니다. GitHub Actions는 테스트에 사용했지만 AWS 자동 배포는 구성하지 않았습니다.

## 3. 필요한 AWS 리소스

실제 배포에는 다음 리소스를 사용했습니다.

- 기존 Default VPC
- 같은 VPC에 배치한 FastAPI용 EC2 1대와 RDS PostgreSQL 1개
- EC2 `t3.micro`, Amazon Linux 2023 x86_64, 8 GiB gp3 root volume
- RDS PostgreSQL `18.3-R1`, `db.t3.micro`, Single-AZ, 20 GiB gp2
- EC2용 보안 그룹과 RDS용 보안 그룹
- EC2에 연결한 IAM role `CatalogGuardEC2SSMRole`

이번 배포에서는 custom VPC와 private subnet을 새로 구성하지 않았습니다. RDS의 `Public access`는 `No`이지만, 이를 custom private subnet 구성이 완료되었다는 의미로 기록하지 않습니다. custom VPC와 private subnet 재구성은 후속 작업입니다.

Single-AZ RDS는 고가용성이 없으므로 production 수준의 장애 복구 구성이 아닙니다. 개인 도메인, Elastic IP, Load Balancer와 정식 외부 HTTPS용 리소스도 생성하지 않았습니다.

## 4. VPC와 보안 그룹

### 네트워크 배치

- 서울 리전 `ap-northeast-2`의 Default VPC를 사용했습니다.
- EC2와 RDS는 같은 VPC에 배치했습니다.
- custom VPC와 private subnet 재구성은 완료하지 않았습니다.
- RDS의 `Public access`는 `No`입니다.
- FastAPI 컨테이너는 EC2의 `127.0.0.1:8000`에만 publish했습니다.
- 인터넷 CIDR을 source로 사용하는 inbound 규칙과 `0.0.0.0/0` 규칙은 추가하지 않았습니다.

### EC2 보안 그룹

EC2 보안 그룹에는 다음 포트의 inbound 규칙이 없습니다.

| 프로토콜 | 포트 | inbound 상태 | 설명 |
| --- | ---: | --- | --- |
| TCP | 22 | 없음 | SSH key pair 없이 SSM Session Manager 사용 |
| TCP | 80 | 없음 | HTTP 공개 안 함 |
| TCP | 443 | 없음 | Nginx와 정식 외부 HTTPS 미구성 |
| TCP | 8000 | 없음 | `127.0.0.1:8000`에만 bind |

SSH 22를 임시로 열지 않았고 EC2 key pair도 생성하지 않았습니다. 호스트 작업과 localhost 검증은 SSM Session Manager에서 수행했습니다. Nginx, 도메인, 고정 DNS와 정식 외부 HTTPS는 완료되지 않았습니다.

### RDS 보안 그룹

| 프로토콜 | 포트 | 소스 | 목적 |
| --- | ---: | --- | --- |
| TCP | 5432 | EC2 보안 그룹 ID | FastAPI와 관리용 psql 연결 |

실제 보안 그룹 ID는 문서에 기록하지 않고 EC2 보안 그룹을 source로 참조합니다. 개인 PC, Streamlit 또는 인터넷 CIDR에는 RDS 접근을 허용하지 않았습니다. 관련 근거는 [RDS의 VPC 배치](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html)와 [보안 그룹 규칙](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)을 확인합니다.

## 5. IAM과 호스트 접근

EC2에는 IAM role `CatalogGuardEC2SSMRole`을 연결하고 `AmazonSSMManagedInstanceCore` 정책을 사용했습니다. SSH key pair 없이 Systems Manager Session Manager 접속에 성공했으며 접속 셸의 `whoami` 결과는 `ssm-user`였습니다.

애플리케이션은 RDS 전용 사용자명과 비밀번호로 연결하며 AWS access key를 사용하지 않습니다. `AWS_ACCESS_KEY_ID`와 `AWS_SECRET_ACCESS_KEY`를 환경파일, 이미지, user data 또는 셸 프로필에 저장하지 않습니다.

Secrets Manager, Parameter Store와 CloudWatch는 이번 배포에 도입하지 않았습니다. 나중에 도입할 때는 필요한 리소스에만 허용하는 최소 권한을 별도 설계합니다.

## 6. EC2 기본 준비

실제 EC2는 Amazon Linux 2023, x86_64, `t3.micro`, 8 GiB gp3 구성입니다. SSM Session Manager의 `ssm-user` 셸에서 다음 명령으로 Docker와 Git을 설치하고 Docker 서비스를 활성화했습니다.

```bash
sudo dnf install -y docker git
sudo systemctl enable --now docker

docker --version
git --version
sudo systemctl is-active docker
sudo docker ps
```

확인된 버전은 Docker `25.0.14`, Git `2.50.1`입니다. Docker 서비스는 `active`이고 부팅 시 자동 시작하도록 설정했습니다. `ssm-user`를 `docker` 그룹에 추가하지 않고 모든 daemon 작업에 `sudo docker`를 사용합니다.

저장소는 `/opt/catalogguard-lite`에 clone했습니다. 배포 기준 전체 SHA를 사용해 detached HEAD로 checkout했으며 EC2에서 소스 파일을 수정하지 않았습니다.

```bash
cd /opt/catalogguard-lite
git checkout --detach 57a713009c7c063f9abb0c9e8f9e1830a1aa086a
git rev-parse HEAD
```

commit SHA를 image tag로 사용하고 mutable한 `latest` tag에 의존하지 않습니다. 실제 image build와 컨테이너 실행은 9절에서 다룹니다.

## 7. RDS 생성과 빈 DB 초기화

실제 RDS 구성은 다음과 같습니다.

| 항목 | 실제 값 |
| --- | --- |
| 엔진 | PostgreSQL `18.3-R1` |
| 인스턴스 | `db.t3.micro` |
| 가용성 | Single-AZ |
| 스토리지 | 20 GiB gp2 |
| 초기 database | `catalogguard_lite` |
| application role | `catalogguard_app` |
| Public access | `No` |

관리자 계정은 `catalogguard_app` 생성과 권한 부여에만 사용하고 애플리케이션에는 제공하지 않았습니다. 비밀번호는 명령행이나 SQL history에 기록하지 않고 대화형 입력을 사용합니다.

```sql
CREATE ROLE catalogguard_app LOGIN;
\password catalogguard_app
GRANT CONNECT, TEMPORARY ON DATABASE catalogguard_lite TO catalogguard_app;
\connect catalogguard_lite
GRANT USAGE, CREATE ON SCHEMA public TO catalogguard_app;
```

`catalogguard_app` 로그인, TLSv1.3 연결, 임시 테이블 생성과 `ROLLBACK`을 확인했습니다. RDS 5432는 EC2 보안 그룹에서만 접근할 수 있으며 실제 endpoint와 비밀번호는 문서에 기록하지 않습니다.

Railway production 데이터는 이전하지 않았습니다. 나중에 이전할 경우 별도 변경 창, export/import 검증, row count와 rollback 계획을 갖춘 migration 작업으로 수행합니다.

## 8. RDS CA bundle과 환경변수

RDS CA bundle은 image에 포함하지 않고 EC2 호스트의 `/etc/catalogguard/rds-ca/global-bundle.pem`에 저장한 뒤 컨테이너에 read-only mount합니다. 파일 소유권과 권한은 `root:root`, `644`입니다. 다운로드 URL과 인증서 갱신 공지는 [AWS RDS TLS 문서](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)에서 확인합니다.

```bash
sudo install -d -m 755 /etc/catalogguard/rds-ca
sudo curl --fail --silent --show-error --location \
  --output /etc/catalogguard/rds-ca/global-bundle.pem \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
sudo chown root:root /etc/catalogguard/rds-ca/global-bundle.pem
sudo chmod 644 /etc/catalogguard/rds-ca/global-bundle.pem
```

환경파일은 저장소 밖 `/etc/catalogguard/api.env`에 보관하며 소유권과 권한은 `root:root`, `600`입니다. 환경파일에는 `DATABASE_URL`, `PGSSLMODE=verify-full`, `PGSSLROOTCERT=/run/secrets/rds-ca-bundle.pem`만 설정합니다. `TEST_DATABASE_URL`과 AWS access key는 사용하지 않습니다.

다음 예시는 Python `getpass`로 비밀번호를 입력하고 예약 문자를 percent encoding한 뒤 환경파일을 생성합니다. `<rds-endpoint>`는 실제 값으로 바꾸되 실제 endpoint, 비밀번호와 전체 `DATABASE_URL`을 터미널에 출력하지 않습니다.

```bash
sudo python3 - <<'PY'
import os
from getpass import getpass
from pathlib import Path
from urllib.parse import quote

endpoint = "<rds-endpoint>".strip()
if not endpoint or endpoint == "<rds-endpoint>":
    raise SystemExit("RDS endpoint를 입력해야 합니다.")

password = getpass("catalogguard_app password: ")
if not password:
    raise SystemExit("DB password를 입력해야 합니다.")

encoded_password = quote(password, safe="")
env_dir = Path("/etc/catalogguard")
env_path = env_dir / "api.env"
env_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
env_path.write_text(
    "DATABASE_URL="
    f"postgresql://catalogguard_app:{encoded_password}@{endpoint}:5432/catalogguard_lite\n"
    "PGSSLMODE=verify-full\n"
    "PGSSLROOTCERT=/run/secrets/rds-ca-bundle.pem\n",
    encoding="utf-8",
)
os.chown(env_path, 0, 0)
os.chmod(env_path, 0o600)
PY
```

생성 후 URL을 검사할 때는 secret 값 대신 허용된 구성 정보만 출력합니다.

```bash
sudo python3 - <<'PY'
from pathlib import Path
from urllib.parse import urlsplit

env_path = Path("/etc/catalogguard/api.env")
database_url = next(
    (
        line.removeprefix("DATABASE_URL=")
        for line in env_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("DATABASE_URL=")
    ),
    "",
)
if not database_url:
    raise SystemExit("DATABASE_URL이 없습니다.")

try:
    parsed = urlsplit(database_url)
    port = parsed.port
except ValueError:
    raise SystemExit("DATABASE_URL 구조가 올바르지 않습니다.")

print(f"scheme={parsed.scheme}")
print(f"username_present={parsed.username is not None}")
print(f"hostname_present={parsed.hostname is not None}")
print(f"hostname_length={len(parsed.hostname or '')}")
print(f"port={port}")
print(f"database={parsed.path.removeprefix('/')}")
print(f"password_present={parsed.password is not None}")
PY
```

이 검사는 scheme, username 존재 여부, hostname 존재 여부와 길이, port, database, password 존재 여부만 보여 줍니다. 실제 hostname, 비밀번호와 전체 URL은 출력하지 않습니다.

컨테이너에서 사용하는 값은 다음 세 개입니다.

| 이름 | 필수 | 비밀정보 | 값 |
| --- | --- | --- | --- |
| `DATABASE_URL` | 예 | 예 | `catalogguard_app`의 percent-encoded RDS 연결 URL |
| `PGSSLMODE` | 예 | 아니요 | `verify-full` |
| `PGSSLROOTCERT` | 예 | 아니요 | `/run/secrets/rds-ca-bundle.pem` |

비밀번호의 `@`, `:`, `/`, `?`, `#`, `%` 같은 예약 문자는 반드시 percent encoding합니다. 현재 `config/database.py`는 driverless `postgresql://` prefix를 `postgresql+psycopg://`로 바꾸므로 psycopg 3와 호환됩니다. TLS 검증은 libpq 환경변수 `PGSSLMODE=verify-full`과 CA 경로로 강제하며 실제 연결에서 TLSv1.3을 확인했습니다. RDS SSL 동작은 [RDS PostgreSQL SSL 문서](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)를 기준으로 확인합니다.

## 9. Alembic 배포 gate와 컨테이너 시작

`Dockerfile.aws`로 `catalogguard-lite-api:57a713009c7c` image를 빌드했습니다. 빌드는 성공했고 당시 image 크기는 약 335 MB였습니다. image는 비루트 사용자 `catalogguard`로 실행되며 `/health` Healthcheck를 포함합니다. secret과 RDS CA 파일은 image에 포함하지 않습니다.

```bash
cd /opt/catalogguard-lite
IMAGE_TAG="57a713009c7c"
sudo docker build --pull -f Dockerfile.aws \
  -t "catalogguard-lite-api:${IMAGE_TAG}" .
```

서비스를 시작하기 전에 같은 image, env file과 CA mount로 일회성 migration을 실행합니다. 이 gate가 실패하면 API를 시작하지 않습니다.

```bash
sudo docker run --rm \
  --env-file /etc/catalogguard/api.env \
  --mount type=bind,src=/etc/catalogguard/rds-ca/global-bundle.pem,dst=/run/secrets/rds-ca-bundle.pem,readonly \
  "catalogguard-lite-api:${IMAGE_TAG}" \
  python -m alembic upgrade head
```

`upgrade head`가 성공했으며 적용된 migration은 다음과 같습니다.

- `20260703_0001`: create inspection tables
- `20260705_0002`: add inspection file identity

현재 revision과 repository head를 같은 실행 조건에서 확인했습니다.

```bash
sudo docker run --rm \
  --env-file /etc/catalogguard/api.env \
  --mount type=bind,src=/etc/catalogguard/rds-ca/global-bundle.pem,dst=/run/secrets/rds-ca-bundle.pem,readonly \
  "catalogguard-lite-api:${IMAGE_TAG}" \
  python -m alembic current

sudo docker run --rm "catalogguard-lite-api:${IMAGE_TAG}" python -m alembic heads
```

`current`와 `heads`는 모두 `20260705_0002 (head)`였습니다. `Dockerfile.aws`의 시작 순서도 Alembic 성공 후 Uvicorn을 실행하므로 최종 시작 시 migration이 실패하면 API가 시작되지 않습니다.

staging 컨테이너는 다음 조건으로 시작했습니다.

```bash
sudo docker run -d \
  --name catalogguard-api-staging \
  --restart unless-stopped \
  --env-file /etc/catalogguard/api.env \
  --mount type=bind,src=/etc/catalogguard/rds-ca/global-bundle.pem,dst=/run/secrets/rds-ca-bundle.pem,readonly \
  --publish 127.0.0.1:8000:8000 \
  "catalogguard-lite-api:${IMAGE_TAG}"
```

DB URL이나 secret을 출력하는 `docker inspect` 형식은 사용하지 않습니다. 실행 사용자, 상태, health, restart 횟수와 정책만 확인합니다.

```bash
sudo docker ps --filter name=catalogguard-api-staging
sudo docker inspect --format '{{.Config.User}} {{.State.Status}} {{.State.Health.Status}} {{.RestartCount}} {{.HostConfig.RestartPolicy.Name}}' catalogguard-api-staging
sudo docker logs --tail 100 catalogguard-api-staging
```

확인 결과는 다음과 같습니다.

| 항목 | 결과 |
| --- | --- |
| 컨테이너 이름 | `catalogguard-api-staging` |
| image | `catalogguard-lite-api:57a713009c7c` |
| 실행 사용자 | `catalogguard` |
| bind | `127.0.0.1:8000:8000` |
| restart policy | `unless-stopped` |
| 상태 | `running` |
| health | `healthy` |
| RestartCount | `0` |

Uvicorn 기본 access log는 비활성화하고 애플리케이션의 구조화 JSON 로그를 사용합니다. 로그를 공유할 때도 실제 endpoint, 비밀번호와 전체 `DATABASE_URL`이 포함되지 않았는지 먼저 확인합니다.

## 10. 임시 외부 HTTPS 검증과 향후 정식 구성

### Cloudflare Quick Tunnel 임시 검증

2026-07-19에는 개인 도메인이 없어 Cloudflare Quick Tunnel의 `trycloudflare.com` 임시 HTTPS 주소로 외부 통합을 검증하였습니다. Cloudflare 계정이나 개인 도메인 없이 사용했으며 EC2 inbound 80, 443, 8000을 열지 않았습니다. FastAPI는 계속 `127.0.0.1:8000`에만 bind하였습니다.

Quick Tunnel은 운영 배포 수단이 아니라 일회성 staging 통합 검증 수단입니다. tunnel을 다시 실행하면 URL이 바뀌며 영구적인 외부 API 주소를 제공하지 않습니다. 실제로 발급된 URL은 이 문서에 기록하지 않습니다.

SSM 세션이 종료되어도 tunnel 프로세스가 유지되도록 다음처럼 `nohup`으로 실행합니다.

```bash
nohup cloudflared tunnel \
  --url http://127.0.0.1:8000 \
  > /tmp/cloudflared-quick.log 2>&1 < /dev/null &

echo $! > /tmp/cloudflared-quick.pid
```

발급된 URL은 실행할 때 로그에서 확인하며 문서나 저장소에 고정하지 않습니다.

```bash
grep -Eo 'https://[[:alnum:]-]+\.trycloudflare\.com' \
  /tmp/cloudflared-quick.log | tail -n 1
```

종료할 때는 broad `pkill`을 사용하지 않습니다. 저장한 PID가 숫자인지, 해당 프로세스가 `cloudflared tunnel`인지 먼저 확인한 뒤 그 PID만 종료합니다.

```bash
if [ -f /tmp/cloudflared-quick.pid ]; then
  PID="$(cat /tmp/cloudflared-quick.pid)"
  case "$PID" in
    ''|*[!0-9]*)
      echo "invalid cloudflared PID" >&2
      ;;
    *)
      CMD="$(ps -p "$PID" -o cmd=)"
      if [ -n "$CMD" ] && printf '%s\n' "$CMD" | grep -q 'cloudflared tunnel'; then
        ps -p "$PID" -o pid=,cmd=
        kill "$PID"
        rm -f /tmp/cloudflared-quick.pid
      else
        echo "saved PID is not the expected cloudflared process" >&2
      fi
      ;;
  esac
fi
```

### 향후 정식 외부 구성

다음 항목은 2026-07-19에 완료하지 않았습니다.

- 개인 도메인
- 고정 DNS
- Nginx reverse proxy
- 정식 외부 HTTPS
- Elastic IP
- Load Balancer
- 영구적인 외부 API 주소

정식 외부 구성을 도입할 때는 도메인 소유, 인증서 발급·갱신, 접근 제어, 고정 주소와 비용을 별도 설계하고 검증해야 합니다. Quick Tunnel 검증을 정식 HTTPS 구성 완료로 간주하지 않습니다.

## 11. Health, readiness, request ID와 로그 검증

### 실제 health와 로그 결과

2026-07-19 실제 결과는 다음과 같습니다.

| 검증 항목 | 결과 |
| --- | --- |
| `GET /health` | HTTP 200, `status: ok` |
| `GET /ready` | HTTP 200, `status: ready`, `database: ok` |
| `X-Request-ID` | 두 응답 모두 존재 |
| Docker Health | `healthy` |
| 애플리케이션 로그 | JSON 구조화 로그 정상 |
| Uvicorn access log | 비활성화 유지 |

내부 검증은 EC2 localhost에서 수행할 수 있습니다.

```bash
curl --fail-with-body --include http://127.0.0.1:8000/health
curl --fail-with-body --include http://127.0.0.1:8000/ready
sudo docker logs --since 10m catalogguard-api-staging
```

### 실제 API 통합 결과

사용자 데이터나 실제 검증 파일명을 문서에 기록하지 않고 다음 결과만 확인하였습니다.

| 순서 | 요청과 결과 |
| --- | --- |
| 첫 CSV `POST` | HTTP 200, `inspection_run_id: 1`, `created: true`, `total_products: 1`, `total_issues: 0` |
| 상세 `GET` | HTTP 200 |
| 목록 `GET` | HTTP 200 |
| 동일 CSV 재요청 | HTTP 200, `inspection_run_id: 1`, `created: false` |
| 중복 요청 후 저장 건수 | 1건 유지 |

POST, 목록 GET, 상세 GET의 구조화 로그에서도 모두 HTTP 200을 확인하였습니다. Uvicorn 기본 access log는 계속 비활성화하고 요청 ID, path와 status code를 포함한 애플리케이션 JSON 로그를 사용합니다.

`/health`만 성공하고 `/ready`가 실패하면 API 프로세스와 DB 연결 상태를 구분합니다. RDS 상태와 보안 그룹 source, CA mount, `PGSSLMODE`, URL 구성 요소와 application role 권한을 확인하되 실제 endpoint, 비밀번호나 전체 `DATABASE_URL`을 출력하지 않습니다.

## 12. Streamlit staging 연결

AWS 검증에는 production 앱과 분리된 Streamlit Community Cloud 앱 `catalogguard-lite-aws-suyong`을 사용하였습니다. AWS 검증용 앱의 Secrets에만 다음 항목을 설정하였고 production Streamlit Secrets는 변경하지 않았습니다.

```toml
CATALOGGUARD_API_BASE_URL = "https://<current-quick-tunnel-host>"
CATALOGGUARD_API_TIMEOUT_SECONDS = "10"
```

실제 Quick Tunnel URL은 문서에 기록하지 않습니다. `CATALOGGUARD_API_BASE_URL`에는 실행 시 로그에서 확인한 현재 임시 URL을 AWS 검증용 앱에만 입력합니다.

실제 화면 검증 결과는 다음과 같습니다.

- AWS RDS의 기존 실행 ID `1` 조회 성공
- Streamlit 화면에서 CSV 업로드·검수·저장 성공
- 새 저장 결과는 실행 ID `2`, 상품 1개, 문제 0개
- 검수 이력에서 실행 ID `1`과 `2` 조회 성공
- Railway production과 production Streamlit 설정 변경 없음

EC2 또는 RDS를 중지하면 AWS 검증용 앱에서 연결 오류가 발생하는 것이 정상입니다. Quick Tunnel을 다시 실행하면 URL이 바뀌므로 `catalogguard-lite-aws-suyong`의 `CATALOGGUARD_API_BASE_URL`만 새 값으로 갱신합니다. production 앱의 Secrets는 변경하지 않습니다.

## 13. 재시작, 배포 교체와 rollback

### EC2와 RDS 재시작 체크리스트

중지된 AWS staging을 다시 검증할 때는 다음 순서를 사용합니다. 실제 리소스 ID나 endpoint는 문서나 명령 기록에 남기지 않습니다.

1. RDS를 먼저 시작합니다.
2. RDS 상태가 `available`인지 확인합니다.
3. EC2를 시작합니다.
4. EC2 상태 검사가 `2/2`인지 확인합니다.
5. SSM Session Manager로 접속합니다.
6. Docker 서비스가 `active`인지 확인합니다.
7. `catalogguard-api-staging` 컨테이너가 `running`인지 확인합니다.
8. Docker Health가 `healthy`인지 확인합니다.
9. `/health`가 HTTP 200인지 확인합니다.
10. `/ready`가 HTTP 200이고 `database: ok`인지 확인합니다.
11. 필요하면 Alembic `current`와 `heads`가 같은지 확인합니다.
12. 외부 검증이 필요할 때만 10절의 Quick Tunnel을 새로 실행합니다.
13. 새 임시 URL을 AWS 검증용 Streamlit 앱 Secrets에만 반영합니다.
14. production Streamlit Secrets가 변경되지 않았는지 확인합니다.

호스트와 컨테이너 상태는 다음처럼 확인합니다.

```bash
sudo systemctl is-active docker
sudo docker ps --filter name=catalogguard-api-staging
sudo docker inspect --format '{{.State.Status}} {{.State.Health.Status}} {{.RestartCount}}' \
  catalogguard-api-staging
curl --fail-with-body http://127.0.0.1:8000/health
curl --fail-with-body http://127.0.0.1:8000/ready
```

컨테이너 restart policy는 `unless-stopped`입니다. 비용 절감을 위해 EC2를 중지할 때 컨테이너를 먼저 `docker stop`하면 EC2 재시작 후 컨테이너가 자동 실행되지 않을 수 있습니다. 기본 중지 절차에서는 컨테이너를 별도로 stop하지 않고 EC2를 중지합니다. 재시작 후 컨테이너가 실행되지 않았다면 상태와 이전 종료 방식을 확인한 다음 이름을 지정해 시작합니다.

```bash
sudo docker start catalogguard-api-staging
```

### 배포 교체와 rollback

새 배포에도 commit SHA 기반 image tag를 사용합니다. 짧은 중단을 허용하는 staging은 다음 순서로 교체합니다.

1. 현재 정상 image tag를 rollback용으로 기록합니다.
2. 새 image로 일회성 migration을 성공시킵니다.
3. 새 image의 사용자, healthcheck와 구성을 확인합니다.
4. 기존 컨테이너를 stop하고 이름을 rollback용으로 변경합니다.
5. 새 컨테이너를 같은 이름과 loopback port로 시작합니다.
6. localhost `/health`, `/ready`와 필요한 API 통합 검증을 수행합니다.
7. 실패하면 새 컨테이너를 중지하고 이전 image tag로 복구합니다.

애플리케이션 image rollback은 DB schema가 이전 코드와 호환될 때만 안전합니다. 자동 `alembic downgrade`는 수행하지 않습니다. 호환되지 않는 migration이면 변경 전에 RDS snapshot을 만들고 복구 시 snapshot으로 새 RDS를 복원하는 별도 승인 절차를 사용합니다.

AWS staging 장애는 Railway production 사용자를 대상으로 하지 않아야 합니다. production Streamlit 설정, Railway 환경변수, Pre-deploy Command와 Start Command는 변경하지 않습니다.

rollback 관찰 기간이 끝난 뒤에는 이름과 tag를 명시해 이전 컨테이너와 image만 정리합니다. 먼저 `docker ps -a`와 `docker image ls`로 대상을 확인합니다. 범위가 넓은 `docker system prune`은 복구용 image까지 지울 수 있으므로 사용하지 않습니다. 로컬 진단에서도 `docker compose down -v`는 PostgreSQL named volume과 데이터를 삭제하므로 실행하지 않습니다.

## 14. 실제 오류와 해결 및 백업·장애 복구

### 실제 오류와 해결

Alembic `upgrade head` 실행 중 다음 로컬 소켓 접속 오류가 발생하였습니다.

```text
/var/run/postgresql/.s.PGSQL.5432
```

애플리케이션이 RDS가 아니라 컨테이너 내부의 로컬 PostgreSQL 소켓을 찾고 있었습니다. 원인은 `/etc/catalogguard/api.env`의 `DATABASE_URL`에 hostname이 빠진 것이었습니다. 환경변수 자체는 존재했지만 host가 없는 URL이었습니다.

오류 발생 전에 EC2에서 RDS 5432 연결과 `catalogguard_app`의 psql 로그인이 이미 성공하였으므로 네트워크나 보안 그룹 문제가 아니었습니다.

진단할 때 전체 `DATABASE_URL`이나 비밀번호를 출력하지 않았습니다. 8절의 `urllib.parse.urlsplit` 방식 또는 SQLAlchemy `make_url`을 사용해 다음 구성 요소만 확인합니다.

- scheme
- username 존재 여부
- hostname 존재 여부
- hostname 길이
- port
- database
- password 존재 여부

실제 진단에서는 hostname 존재 여부가 `False`임을 확인하였습니다. 환경변수가 있다는 사실만으로 URL이 올바르다고 판단하지 않습니다.

해결 순서는 다음과 같습니다.

1. 잠재적으로 노출되었을 수 있는 `catalogguard_app` 비밀번호를 교체하였습니다.
2. Python `getpass`로 새 비밀번호를 입력하였습니다.
3. `urllib.parse.quote`로 비밀번호를 percent encoding하였습니다.
4. endpoint가 비어 있지 않고 예상 형식인지 검사하였습니다.
5. `/etc/catalogguard/api.env`를 재생성하고 `root:root`, `600`을 적용하였습니다.
6. 호스트와 컨테이너 내부에서 hostname 존재 여부를 secret 없이 확인하였습니다.
7. Alembic `upgrade head`를 다시 실행해 성공하였습니다.

이 장애에서 확인한 교훈은 다음과 같습니다.

- 환경변수 존재 여부만으로는 연결 URL의 유효성을 보장할 수 없습니다.
- URL은 secret을 노출하지 않고 구성 요소 단위로 검증해야 합니다.
- psql 연결 성공과 애플리케이션 `DATABASE_URL` 검증은 별도로 수행해야 합니다.
- migration 실패 시 API를 시작하지 않는 gate가 정상적으로 작동하였습니다.

### 백업과 장애 복구

다음은 향후 변경과 영구 삭제 전에 적용할 운영 원칙입니다. 2026-07-19에는 snapshot 복원이나 장애 복구 훈련을 완료하지 않았습니다.

- RDS 자동 백업 보존 기간과 backup window를 변경 전에 확인합니다.
- schema 변경 전 수동 snapshot이 필요하면 생성 완료 상태까지 확인합니다.
- snapshot 복원은 기존 DB를 덮어쓰지 않고 새 RDS instance를 만듭니다.
- 복원 후 SG, CA/TLS, application role, Alembic revision과 `/ready`를 다시 검증합니다.
- 중요한 staging 데이터가 있다면 삭제 전에 별도 export도 검토합니다.
- backup은 실제 restore 훈련을 통과한 뒤 복구 수단으로 간주합니다.

자동 백업과 snapshot의 보존·삭제 동작은 [RDS 자동 백업](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.html)을 확인합니다.

## 15. 중지와 비용 절감

### 2026-07-19 실제 종료 결과

- Streamlit 화면 검증 종료
- Quick Tunnel 프로세스 종료
- EC2 중지 완료
- RDS 중지 완료

EC2와 RDS를 삭제하거나 terminate한 것이 아니라 비용 절감을 위해 중지한 상태입니다.

### 기본 중지 순서

1. 필요한 검증 결과와 로그를 기록하되 secret은 저장하지 않습니다.
2. 10절의 절차로 Quick Tunnel PID와 명령을 확인한 뒤 해당 프로세스만 종료합니다.
3. 컨테이너를 별도로 `docker stop`하지 않고 EC2를 중지합니다.
4. EC2 상태가 `stopped`인지 확인합니다.
5. RDS를 중지합니다.
6. RDS 상태가 `stopped`인지 확인합니다.
7. EBS, RDS storage와 backup의 잔여 비용을 확인합니다.
8. RDS가 최대 중지 가능 기간 이후 자동으로 시작되는지 추후 다시 확인합니다.

EC2를 중지하면 compute 과금은 멈추지만 연결된 EBS storage 비용은 남을 수 있습니다. RDS를 중지해도 provisioned storage와 backup 비용은 남을 수 있으며 최대 중지 가능 기간 이후 자동으로 시작될 수 있습니다. 중지는 임시 비용 절감 수단이며 삭제와 동일하지 않습니다.

정확한 조건은 [EC2 lifecycle](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html)과 [RDS stop/start](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html)에서 확인합니다.

### 영구 삭제 위험 구역

영구 삭제는 기본 중지 절차에 포함하지 않으며 2026-07-19에는 수행하지 않았습니다. 삭제가 필요하면 먼저 다음 사항을 별도 승인합니다.

1. 보존할 검증 결과와 데이터 범위를 결정합니다.
2. RDS final snapshot 생성 여부와 보존 기간을 결정합니다.
3. deletion protection 해제가 필요한지 확인합니다.
4. RDS 삭제 후 retained automated backup과 manual snapshot 보존 여부를 확인합니다.
5. EC2 terminate 전 EBS `DeleteOnTermination`과 snapshot 필요 여부를 확인합니다.
6. ENI, 보안 그룹과 IAM role 등 연결 리소스의 의존성을 확인합니다.
7. Cost Explorer와 청구 대시보드에서 잔여 과금을 다시 확인합니다.

RDS 삭제는 final snapshot과 automated backup 선택에 따라 데이터 손실과 비용이 달라집니다. 콘솔 확인 문구와 [RDS 삭제 절차](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)를 확인하기 전에는 삭제하지 않습니다.

## 16. 2026-07-19 완료 결과와 향후 개선

### 완료 결과

- [x] RDS와 EC2 생성
- [x] EC2와 RDS 보안 그룹 연결
- [x] SSM Session Manager 접속
- [x] Docker와 Git 설치
- [x] 저장소 clone과 지정 SHA detached checkout
- [x] RDS CA bundle 준비와 read-only mount
- [x] 애플리케이션 전용 DB 계정 생성과 권한 확인
- [x] TLSv1.3 연결 검증
- [x] root 전용 환경파일 생성
- [x] `Dockerfile.aws` image build
- [x] Alembic migration과 `current`/`heads` 일치 확인
- [x] FastAPI 컨테이너 실행과 Docker Health 확인
- [x] `/health`와 `/ready` 검증
- [x] API 저장·목록·상세 조회와 동일 CSV 중복 방지 검증
- [x] Quick Tunnel을 사용한 임시 외부 HTTPS 검증
- [x] 별도 Streamlit AWS 검증 앱 연결
- [x] Streamlit UI 저장과 실행 ID `1`, `2` 이력 조회
- [x] Quick Tunnel 종료
- [x] EC2와 RDS 중지

### 미완료 항목

- [ ] 개인 도메인
- [ ] 고정 DNS
- [ ] 정식 외부 HTTPS
- [ ] Nginx reverse proxy
- [ ] Elastic IP
- [ ] Load Balancer
- [ ] GitHub Actions AWS 자동 배포
- [ ] Secrets Manager 또는 Parameter Store
- [ ] CloudWatch
- [ ] backup 복원 훈련
- [ ] Redis와 Celery
- [ ] custom VPC와 private subnet 재구성

AWS staging은 production이 아니며 Railway production과 기존 production Streamlit 설정은 변경하지 않았습니다. 완료 여부가 확인되지 않은 항목은 완료로 표시하지 않습니다.
