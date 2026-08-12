# AWS EC2·RDS staging 배포 런북

## 1. 목적과 범위

이 문서는 CatalogGuard Lite FastAPI를 AWS의 별도 staging 환경에 수동 배포한 절차와 2026-07-19 검증 결과를 기록합니다. 이후 2026-08-12에 같은 staging 환경에서 S3 Supplier CSV ingestion을 실제 AWS 자원으로 검증하고 runtime을 현재 `main` image로 교체했으며, 그 기록은 17절에 있습니다. 실제 내부 경로는 다음과 같습니다.

```text
AWS ap-northeast-2 / Default VPC
  -> EC2 127.0.0.1:8000 / FastAPI Docker 컨테이너
  -> TLSv1.3 / 5432 / RDS PostgreSQL
```

2026-07-19 배포 기준은 `main` 브랜치의 commit `57a713009c7c063f9abb0c9e8f9e1830a1aa086a`이며 Docker image tag는 앞 12자리인 `57a713009c7c`입니다. 해당 commit의 GitHub Actions가 성공했고 테스트 결과는 `696 passed, 25 skipped`였습니다. 2026-08-12에 이 runtime을 commit `081ae265bc60e67209450c841c94d66f1e3ea310`(image tag `081ae265bc60`)으로 교체했으므로, 아래 2~16절의 image tag와 commit은 2026-07-19 시점 기록으로 읽어야 합니다.

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

### 2026-08-02 현재 저장소 이미지 CI 재검증

아래 2026-07-19 배포 기록은 당시 `20260705_0002` head와 image tag를 사용한 이력이다. 현재 코드는 비동기 inspection API를 포함하므로 FastAPI import 시 `services` package가 필요하고, Celery task를 실행하려면 `workers` package도 이미지에 있어야 한다. `Dockerfile.aws`는 두 package를 명시적으로 복사하며, 현재 Alembic head는 `20260728_0006`이다.

현재 저장소에서는 실제 AWS 리소스를 시작하지 않고 GitHub Actions Ubuntu의 Docker runtime CI에서 다음 packaging 경계를 재검증했다. 최신 성공 run은 `30736143581`이며 commit `99c9859d3eb09b5bb6acfeea9c351faf03f41535`에 해당한다.

아래 명령은 CI에서 수행한 packaging·import 검증의 재현 형태이며, 실제 최신 검증은 해당 GitHub Actions run에서 수행했다.

```bash
docker build -f Dockerfile.aws -t catalogguard-lite-api:local-verify .
docker run --rm --user 10001 catalogguard-lite-api:local-verify \
  python -c "import api, services, workers; import api.main; import workers.inspection_tasks; print('api and worker imports ok')"
```

검증 결과 image build, `api`·`services`·`workers`와 FastAPI·Celery task import, 실행 UID `10001`, PostgreSQL migration, Dockerfile.aws 기본 CMD의 Uvicorn 시작과 `/health` HTTP `200`이 성공했다. 이 결과는 GitHub Actions Ubuntu의 Docker packaging/runtime smoke만 증명하며, 중지된 EC2·RDS의 현재 상태나 실제 RDS TLS 연결을 재검증한 것은 아니다. 다시 배포할 때는 새 image와 실제 staging `DATABASE_URL`·CA mount로 `alembic upgrade head`, `/health`, `/ready`를 순서대로 확인해야 한다.

### 2026-07-19 실제 AWS staging 배포 기록

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

## 17. 2026-08-12 S3 Supplier CSV ingestion 실제 E2E 검증

### 17.1 목적과 이전 상태와의 차이

`POST /api/v1/etl-loads/s3`는 commit `e84814c`에서 추가되었지만 그때까지 검증은 fake S3 client 기반 단위·API 테스트뿐이었습니다. 이번 작업은 새 기능을 만들지 않고, 이미 있는 이 기능을 실제 AWS staging 자원에 연결해 다음 경로를 끝까지 확인한 기록입니다.

```text
private S3 (ap-northeast-2)
  -> EC2 Instance Role 최소권한 (CatalogGuardEC2SSMRole)
  -> FastAPI POST /api/v1/etl-loads/s3
  -> read_s3_csv_object() -> run_web_etl() -> run_pipeline() -> load_standard_csv()
  -> RDS PostgreSQL staging (ETLLoadRun / staging row / Actor Audit)
```

작업에는 root가 아닌 IAM user profile 하나만 사용했고, 호스트 작업은 SSM Run Command로 수행했습니다. 애플리케이션 코드·테스트·workflow·Terraform·migration 파일은 수정하지 않았습니다.

### 17.2 S3 bucket과 합성 객체

전용 staging bucket을 `ap-northeast-2`에 두고 실제 CLI로 다음을 확인했습니다.

| 항목 | 확인 결과 |
|---|---|
| Block Public Access | `BlockPublicAcls`·`IgnorePublicAcls`·`BlockPublicPolicy`·`RestrictPublicBuckets` 4개 모두 `true` |
| bucket policy | 존재하지 않음(`NoSuchBucketPolicy`) — public 허용 경로 없음 |
| 기본 암호화 | SSE-S3 `AES256`, Bucket Key 활성, SSE-C 차단 |
| region | `ap-northeast-2` |

허용 prefix는 `incoming/catalogguard/`이며, 업로드한 객체는 저장소의 합성 fixture `tests/fixtures/etl/sample_vendor_valid.csv`(236 bytes) 1건뿐입니다. 업로드 전 파일 내용을 직접 읽어 개인정보·자격증명·실제 고객 데이터가 없고 `sample_fashion_vendor_v1` 프로필과 호환되는 것을 확인했습니다.

```text
s3://<staging-bucket>/incoming/catalogguard/e2e/sample_vendor_valid.csv
```

### 17.3 EC2 Instance Role 최소권한

기존 EC2 Role `CatalogGuardEC2SSMRole`에 inline policy `CatalogGuardStagingSupplierS3Read` 하나만 추가했습니다. `iam:GetInstanceProfile`로 instance profile이 실제로 이 role을 담고 있는 것을 확인했고, 정책 문서는 실제 IAM API 조회 결과로 검증했습니다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "CatalogGuardStagingSupplierS3Read",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::<staging-bucket>/incoming/catalogguard/*"
    }
  ]
}
```

`s3:PutObject`, `s3:DeleteObject`, `s3:ListBucket`, `s3:ListAllMyBuckets`, `s3:*`, `Resource: "*"`는 부여하지 않았습니다. 새 access key도 만들지 않았고 컨테이너에 AWS 자격증명을 주입하지 않았습니다. 컨테이너 안에서 확인한 결과는 다음과 같습니다.

| 확인 | 결과 |
|---|---|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | 둘 다 컨테이너 환경에 없음 |
| 컨테이너가 사용하는 principal | `assumed-role/CatalogGuardEC2SSMRole/<instance-id>` |
| 허용 prefix 객체 | `head_object`·`get_object` 모두 성공(236 bytes) |
| 허용 prefix 밖 객체 | `AccessDenied` / HTTP `403` |
| 허용 prefix 안의 없는 key | HTTP `403`(`ListBucket`이 없으므로 `404` 아님) |

### 17.4 네트워크 경계 재확인

| 대상 | 확인 결과 |
|---|---|
| EC2 Security Group | inbound 규칙 **0개**(SSH `22` 없음, `8000` 공개 없음, `0.0.0.0/0` 없음) |
| FastAPI bind | `127.0.0.1:8000`만 사용, public port 추가 없음 |
| RDS | `publicly_accessible=false`, 저장 암호화 활성 |
| RDS Security Group | `5432` 1개만 허용하고 source가 CIDR이 아니라 EC2 Security Group 참조 |
| 호스트 접근 | SSM Session Manager / Run Command만 사용, SSH key pair 없음 |

Security Group은 이번 작업에서 수정하지 않았습니다.

### 17.5 stale runtime 발견과 현재 main 재배포

검증을 시작할 때 EC2에서 실행 중이던 컨테이너는 image `catalogguard-lite-api:57a713009c7c`, checkout commit `57a713009c7c…`였습니다. 실제 `openapi.json`을 조회해 `/api/v1/etl-loads/s3` 경로가 없는 것을 확인했고, 이 runtime이 S3 connector 추가 commit `e84814c`보다 이전(현재 `main` 기준 104 commit 뒤)이라는 것을 git 이력으로 확정했습니다. 문서 추정이 아니라 실제 runtime 조회로 판단했습니다.

재배포는 기존 `Dockerfile.aws`를 그대로 사용했습니다.

- `/opt/catalogguard-lite`가 clean인 것을 먼저 확인하고(dirty면 중단) exact commit `081ae265bc60e67209450c841c94d66f1e3ea310`으로 detached checkout
- image tag는 commit SHA 앞 12자리인 `081ae265bc60`을 사용하고 `latest`에 의존하지 않음
- 새 image build와 검증(boto3 포함, `/api/v1/etl-loads/s3` 존재, `alembic heads`)이 끝난 뒤에야 기존 컨테이너를 교체
- 기존 컨테이너는 삭제하지 않고 `catalogguard-api-staging-57a7130-rollback`으로 이름만 바꿔 보존하고 구 image도 남김

### 17.6 RDS CA bundle 재현성 문제와 구조 개선

재배포 준비 중 발견한 문제입니다. 실행 중이던 컨테이너를 `docker inspect`로 확인하니 **bind mount가 하나도 없었는데**, 컨테이너 안에는 `PGSSLROOTCERT`가 가리키는 `/run/secrets/rds-ca-bundle.pem`이 존재했습니다. 같은 파일이 호스트에는 없었고 `Dockerfile.aws`도 인증서를 복사하지 않습니다.

즉 CA bundle이 **그 컨테이너의 writable layer 안에만** 있었습니다. 이 상태에서 새 컨테이너를 만들면 `PGSSLMODE=verify-full` 연결이 깨지므로, 재배포 자체가 재현 불가능한 구조였습니다.

해결은 다음과 같습니다.

```text
컨테이너 layer 안에만 있던 CA bundle
  -> docker cp 로 호스트에 분리 저장
     /etc/catalogguard/rds-ca-bundle.pem   (root:root 644, 165408 bytes)
  -> 새 컨테이너에 read-only mount
     /etc/catalogguard/rds-ca-bundle.pem : /run/secrets/rds-ca-bundle.pem : ro
```

`PGSSLROOTCERT` 값은 그대로 두고 마운트 경로만 맞췄기 때문에 환경파일은 이 목적으로 바꾸지 않았습니다. 8절의 2026-07-19 기록에 있는 `/etc/catalogguard/rds-ca/global-bundle.pem`도 호스트에 그대로 남아 있습니다.

이것은 애플리케이션 코드 변경이 아니라 AWS staging runtime·배포 구성 개선입니다.

### 17.7 환경변수 추가

`/etc/catalogguard/api.env`는 기존 방식을 유지하고 필요한 key만 멱등적으로 추가했습니다. 파일 전체를 다시 쓰지 않았고 기존 값을 덮어쓰지 않았으며 소유권·권한 `root:root`, `600`을 유지했습니다.

| key | 성격 | 비고 |
|---|---|---|
| `CATALOGGUARD_ETL_S3_BUCKET` | 비밀 아님 | staging bucket 이름 |
| `CATALOGGUARD_ETL_S3_PREFIX` | 비밀 아님 | `incoming/catalogguard/` |
| `CATALOGGUARD_JWT_SECRET` | **비밀** | 호스트에서 `openssl rand`로 생성, 값은 출력·기록하지 않음 |

`CATALOGGUARD_JWT_SECRET`은 이 staging 환경이 authentication 도입 이전에 만들어져 누락되어 있던 값입니다. 기존 `DATABASE_URL`·`PGSSLMODE`·`PGSSLROOTCERT`는 그대로 보존했습니다.

주의할 점이 하나 있습니다. `docker restart`는 `--env-file`을 다시 읽지 않습니다. 컨테이너 생성 이후에 추가한 환경변수는 반영되지 않으므로 **컨테이너를 재생성해야** 합니다. 이 순서를 지키지 않아 처음에는 로그인이 HTTP `500`으로 실패했고, 컨테이너를 재생성해 해결했습니다. 이때 애플리케이션은 `JWTConfigurationError`로 명확히 실패하고 secret을 노출하지 않았습니다.

### 17.8 Alembic migration

새 image의 head가 기존 DB revision보다 앞서 있었으므로 `upgrade`만 수행했습니다. `downgrade`·`drop`·`truncate`나 수동 파괴적 SQL은 실행하지 않았습니다.

```text
before : 20260705_0002
run    : python -m alembic upgrade head   (6개 revision 적용)
after  : 20260810_0012 (head), single head
```

### 17.9 실제 E2E 결과

로그인한 operator JWT로 EC2 localhost의 FastAPI를 호출했습니다. 요청 본문은 다음과 같습니다.

```json
{
  "profile_id": "sample_fashion_vendor_v1",
  "object_key": "incoming/catalogguard/e2e/sample_vendor_valid.csv"
}
```

첫 요청 응답은 HTTP `200`이며 내용은 다음과 같습니다.

```text
created         = true
etl_load_run_id = 1
profile         = sample_fashion_vendor / v1
source_filename = sample_vendor_valid.csv
total_rows      = 1
loaded_rows     = 1
rejected_rows   = 0
actor_username  = staging_e2e_operator
```

RDS에서 직접 조회한 결과도 응답과 일치했습니다. `etl_load_runs` 1건에 `input_file_sha256`이 64자리로 저장되어 있었고, 해당 run의 staging 상품 1건은 다음과 같습니다.

```text
product_id = 000123   product_group_id = 000123   category = TOP
price      = 12000    sale_price = 10000
color      = BLACK    size = M    stock = 10    seller = Sample Brand
rejected row 레코드 = 0건
```

입력 CSV의 가격 문자열 `"12,000"`이 기존 pipeline을 통해 정수 `12000`으로 표준화된 것을 실제 DB 값으로 확인했습니다. 한글 상품명은 SSM 터미널 출력에서만 깨져 보였고 Unicode codepoint로 비교한 결과 원본과 정확히 일치했으므로 데이터 손상이 아닙니다.

### 17.10 Idempotency와 Actor Audit

동일 S3 객체·동일 프로필로 한 번 더 호출했습니다.

```text
1회차 : created = true    etl_load_run_id = 1
2회차 : created = false   etl_load_run_id = 1
DB    : etl_load_runs 총 1건 (새 run 생성 없음)
```

`input_file_sha256`·`profile_name`·`profile_version` 기반 중복 방지가 실제 AWS staging DB에서 동작하는 것을 확인했습니다.

Actor Audit은 `actor_user_id`가 `users` 테이블의 실제 row를 가리키고 `actor_username` snapshot도 일치했으며, dedup 요청에서도 최초 run의 actor가 그대로 유지되었습니다. actor는 요청 본문이 아니라 인증된 JWT `current_user`에서만 가져옵니다.

### 17.11 인증·권한과 오류 경계

| 시나리오 | 실제 HTTP | code |
|---|---:|---|
| anonymous(토큰 없음) | `401` | `authentication_required` |
| viewer(유효 토큰) | `403` | `insufficient_role` |
| operator, 허용 prefix 밖 key | `400` | `s3_key_not_allowed` |
| operator, 허용 prefix 안의 없는 key | `502` | `s3_read_failed` |

마지막 줄이 `404 s3_object_not_found`가 아닌 이유는 최소권한 때문입니다. `s3:ListBucket`이 없는 principal에게 S3는 존재하지 않는 key를 `404`가 아니라 `403 AccessDenied`로 응답하고(키 존재 여부 노출 방지), 애플리케이션은 이를 안전한 `s3_read_failed`로 매핑합니다. `404`를 만들기 위해 `ListBucket`을 추가하지 않기로 했으므로 이는 결함이 아니라 선택의 결과입니다. fake S3 client 테스트는 `NoSuchKey`를 주입하므로 이 차이를 재현하지 못하며, 실제 AWS에서만 확인할 수 있는 동작입니다.

네 시나리오를 모두 실행한 뒤에도 `etl_load_runs`는 1건으로 유지되어, 실패 경로가 실행 이력을 만들지 않는 것도 확인했습니다.

### 17.12 로그 안전성

구조화 로그에서 다음 패턴을 검사한 결과 모두 0건이었습니다.

```text
Bearer / JWT 형태 / password / AWS access key 형태 / postgresql:// / AWS secret token
S3 bucket 이름
```

S3 실패는 `{"event":"etl_s3_source_failed","code":"s3_key_not_allowed"}`처럼 안전한 코드와 request ID만 남기고 SDK 예외 원문·객체 정보·자격증명을 남기지 않습니다.

### 17.13 cold start 재현성 검증

정리 작업에서 EC2를 완전히 `stopped` 상태로 만든 뒤 다시 시작해, 사람이 개입하지 않아도 최신 runtime이 복구되는지 확인했습니다.

| 확인 | 결과 |
|---|---|
| 컨테이너 자동 기동 | `restart=unless-stopped`로 자동 시작, `running` / `healthy` |
| image | `catalogguard-lite-api:081ae265bc60` |
| `/health`, `/ready` | 모두 `200`(CA read-only mount 기준 TLS 연결 정상) |
| 필요한 환경변수 6개 | 호스트 파일과 컨테이너 내부 양쪽에서 존재 확인 |

17.6의 CA bundle 구조 개선이 실제로 재현성을 확보했음을 이 단계에서 확인했습니다.

### 17.14 정리와 남은 자산

| 대상 | 처리 |
|---|---|
| 임시 E2E credential 파일(`/root/.catalogguard-e2e-creds`) | `shred`로 삭제 |
| 환경파일 백업(`api.env.bak.*`) | 현재 `api.env` 무결성과 cold start 검증 후 `shred`로 삭제, 잔여 백업 0개 |
| `/etc/catalogguard/api.env` | `root:root` `600`, 필요한 key 6개 유지 |
| RDS CA bundle | 유지 |
| 합성 S3 객체 | 유지(private bucket, 재사용 가능) |
| rollback 컨테이너·image | 유지 |
| staging 테스트 계정 2개와 E2E 실행 이력 | 유지(Actor Audit 증거 보존) |
| EC2 | 최종 `stopped` |
| RDS | `available` 유지(중지하지 않음) |

E2E 동안 operator에 임시로 부여했던 관리형 정책은 검증이 끝난 뒤 관리자 계정에서 연결 해제했습니다.

### 17.15 이번 검증의 범위 밖

- S3 bucket과 EC2 Role의 S3 read policy는 Console·CLI로 구성했습니다. `terraform apply`·`destroy`·`import`나 state 변경을 하지 않았으므로 **Terraform이 관리하는 자원이 아닙니다.** `terraform/` 코드에는 S3 리소스 자체가 없습니다.
- S3 event 알림·Lambda·SQS 기반 자동 수집, prefix 일괄 처리, 증분 수집은 구현하지 않았습니다.
- 이 E2E는 수동 검증이며 GitHub Actions에서 자동 재실행되지 않습니다.
- 합성 fixture 1건 기준 결과이며 실제 공급사 운영 데이터·production catalog와는 연동하지 않았습니다.
- Secrets Manager·Parameter Store를 도입하지 않았고 secret은 여전히 호스트 환경파일에 있습니다.
