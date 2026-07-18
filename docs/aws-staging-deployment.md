# AWS EC2·RDS staging 배포 런북

## 1. 목적과 범위

이 문서는 CatalogGuard Lite FastAPI를 AWS의 별도 staging 환경에 수동 배포하기 위한 실행 절차입니다. 목표 경로는 다음과 같습니다.

```text
별도 Streamlit Community Cloud staging 앱
  -> HTTPS 443 / Nginx / EC2
  -> 127.0.0.1:8000 / FastAPI Docker 컨테이너
  -> 5432 / private RDS PostgreSQL
```

현재 Railway FastAPI·PostgreSQL은 production으로 계속 운영합니다. AWS staging은 Railway를 대체하지 않으며, production Streamlit 앱의 설정도 변경하지 않습니다. 이 저장소에 `Dockerfile.aws`와 절차를 준비했을 뿐 AWS 리소스는 아직 생성하지 않았습니다.

첫 배포에서 제외하는 범위는 Railway 데이터 이전, Redis, Celery, ECS, Kubernetes, Terraform, GitHub Actions 자동 배포입니다. 먼저 빈 RDS에서 수동 배포를 검증한 후 각각 별도 작업으로 진행합니다.

## 2. 배포 전 결정과 공식 정보 확인

AWS 리소스를 만들기 직전에 콘솔과 공식 문서에서 다음을 다시 확인합니다.

- 서울 리전에서 RDS PostgreSQL 18을 만들 수 있는지와 제공되는 최신 minor 버전
- EC2, EBS, RDS, 백업·스냅샷, 퍼블릭 IPv4의 현재 가격
- 선택한 EC2 AMI와 인스턴스 타입의 아키텍처가 Docker 이미지와 맞는지
- 도메인과 TLS 인증서의 소유·갱신 방법

CI와 로컬 DB는 PostgreSQL 18입니다. 따라서 RDS도 18을 우선 선택하되, 서울 리전에서 지원되지 않으면 임의로 낮추지 말고 호환성 테스트 계획을 먼저 세웁니다. minor 버전과 가격은 이 문서에 고정하지 않습니다. [RDS PostgreSQL 버전](https://docs.aws.amazon.com/AmazonRDS/latest/PostgreSQLReleaseNotes/postgresql-versions.html)과 [AWS Pricing Calculator](https://calculator.aws/)를 사용합니다.

## 3. 필요한 AWS 리소스

최소 리소스는 다음과 같습니다.

- VPC와 인터넷 게이트웨이
- EC2용 public subnet 1개
- RDS DB subnet group용 서로 다른 가용 영역의 private subnet 2개 이상
- FastAPI용 EC2 1대와 연결된 EBS root volume
- private RDS PostgreSQL 1개
- EC2용 보안 그룹과 RDS용 보안 그룹
- EC2용 IAM instance profile
- staging 도메인이 가리킬 안정적인 public IPv4. Elastic IP 사용 여부는 비용을 확인해 결정
- RDS 자동 백업과 필요 시 수동 snapshot

비용을 줄인 첫 staging은 single-AZ RDS로 시작할 수 있습니다. 이는 고가용성이 없으므로 production 수준의 장애 복구를 의미하지 않습니다. RDS DB subnet group은 single-AZ 인스턴스라도 서로 다른 가용 영역의 subnet을 포함해야 합니다.

## 4. VPC와 보안 그룹

### 네트워크 배치

- EC2는 인터넷 게이트웨이 경로가 있는 public subnet에 둡니다.
- RDS는 인터넷 게이트웨이로 직접 라우팅되지 않는 private subnet과 DB subnet group에 둡니다.
- RDS의 `Public access`는 `No`로 설정합니다.
- PostgreSQL `5432`를 `0.0.0.0/0` 또는 `::/0`에 공개하지 않습니다.

### EC2 보안 그룹

권장 inbound 규칙은 다음 하나입니다.

| 프로토콜 | 포트 | 소스 | 목적 |
| --- | ---: | --- | --- |
| TCP | 443 | staging 사용 범위 또는 `0.0.0.0/0` | Nginx HTTPS |

Streamlit staging 앱이 호출해야 하므로 일반적으로 443은 인터넷에서 도달 가능해야 합니다. 사용자 범위가 제한된 staging이면 애플리케이션 인증 또는 별도 접근 제어도 검토합니다. FastAPI 컨테이너의 8000은 EC2의 `127.0.0.1`에만 publish하며 보안 그룹에 열지 않습니다.

SSH 22는 기본적으로 열지 않습니다. EC2 IAM role에 `AmazonSSMManagedInstanceCore`를 연결하고 Systems Manager Session Manager를 사용합니다. 조직 정책상 SSH가 불가피한 짧은 작업만 관리자 고정 IP의 `/32` 또는 `/128`로 일시 허용하고 작업 직후 삭제합니다.

HTTPS 준비 전 외부 HTTP 포트를 임시로 열지 않고 Session Manager 안에서 localhost를 검사합니다. 첫 인증서는 DNS-01 방식으로 발급하면 80을 열지 않을 수 있습니다. 수동 DNS-01을 선택하면 인증서 만료 전 갱신을 일정에 넣고, 자동화가 필요해지면 특정 hosted zone에만 접근하는 최소 Route 53 권한을 별도 검토합니다.

outbound는 최소한 DNS, 패키지·이미지 다운로드와 AWS API를 위한 HTTPS 443, RDS 보안 그룹의 PostgreSQL 5432가 필요합니다. 처음에는 기본 outbound를 사용할 수 있지만 동작을 확인한 뒤 조직 정책에 맞게 줄입니다.

### RDS 보안 그룹

| 프로토콜 | 포트 | 소스 | 목적 |
| --- | ---: | --- | --- |
| TCP | 5432 | EC2 보안 그룹 ID | FastAPI와 관리용 psql 연결 |

IP CIDR 대신 EC2 보안 그룹을 source로 참조합니다. 개인 PC, Streamlit, 인터넷에는 RDS 접근을 허용하지 않습니다. 관련 근거는 [RDS의 VPC 배치](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html)와 [보안 그룹 규칙](https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html)을 확인합니다.

## 5. IAM과 호스트 접근

EC2 instance profile에는 우선 `AmazonSSMManagedInstanceCore`만 연결합니다. 애플리케이션은 RDS 사용자명·비밀번호로 연결하며 AWS access key를 사용하지 않습니다. access key를 `.env.aws`, 이미지, user data 또는 셸 프로필에 저장하지 않습니다.

CloudWatch Agent, Route 53 DNS-01 자동 갱신, Secrets Manager를 나중에 도입하면 필요한 리소스 ARN에만 허용하는 별도 최소 권한을 추가합니다. 이번 수동 첫 배포에는 과도한 관리형 정책을 연결하지 않습니다.

## 6. EC2 기본 준비

아래 예시는 Ubuntu LTS를 기준으로 하며 Session Manager 셸에서 실행합니다. 다른 AMI를 선택했다면 해당 배포판의 공식 패키지 절차로 바꿉니다.

```bash
sudo apt-get update
sudo apt-get install -y docker.io nginx postgresql-client curl ca-certificates
sudo systemctl enable --now docker
sudo systemctl enable --now nginx
sudo docker version
nginx -v
psql --version
```

저장소는 읽기 전용 deploy credential 또는 승인된 조직 방식으로 clone하고, 배포할 commit을 명시적으로 checkout합니다. mutable한 `latest` 대신 commit SHA를 이미지 tag로 사용합니다.

```bash
cd /opt
sudo git clone <repository-url> catalogguard-lite
sudo chown -R "$USER":"$USER" /opt/catalogguard-lite
cd /opt/catalogguard-lite
git fetch --prune origin
git checkout <approved-commit-sha>
IMAGE_TAG="$(git rev-parse --short=12 HEAD)"
sudo docker build --pull -f Dockerfile.aws -t "catalogguard-lite-api:${IMAGE_TAG}" .
```

`Dockerfile.aws`는 `requirements-api.txt`만 설치하고 API, DB, Alembic에 필요한 소스만 복사합니다. `catalogguard` UID/GID 10001로 실행하며 이미지에 secret이나 RDS CA 파일을 포함하지 않습니다. 루트 이름의 `Dockerfile`을 만들지 않으므로 Railway Railpack 자동 감지와 기존 production 명령은 그대로 유지됩니다.

## 7. RDS 생성과 빈 DB 초기화

RDS를 만들 때 다음을 적용합니다.

- PostgreSQL 18의 서울 리전 지원 minor 버전을 콘솔에서 확인
- storage encryption 활성화
- `Public access: No`
- private DB subnet group과 RDS 보안 그룹 연결
- 자동 백업 보존 기간 설정
- staging 운영 중에는 deletion protection 사용을 검토
- master 비밀번호는 저장소나 명령행에 넣지 않고 승인된 비밀 저장소에서 관리

첫 배포는 빈 RDS에서 시작합니다. RDS master 계정은 초기 역할 생성에만 사용하고 애플리케이션에는 주지 않습니다. EC2에서 TLS 검증을 켠 `psql`로 접속한 후 전용 application role과 database를 만듭니다. 비밀번호는 명령행이나 SQL history에 쓰지 말고 `\password <application-role>`의 대화형 입력을 사용합니다.

```sql
CREATE ROLE <application-role> LOGIN;
\password <application-role>
CREATE DATABASE <application-database> OWNER <application-role>;
REVOKE ALL ON DATABASE <application-database> FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE <application-database> TO <application-role>;
```

Railway production 데이터 이전은 이 초기 배포에 포함하지 않습니다. 나중에 별도 변경 창, export/import 검증, row count 및 rollback 계획을 갖춘 migration 작업으로 수행합니다.

## 8. RDS CA bundle과 환경변수

RDS CA bundle은 이미지에 굽지 않고 EC2 호스트에 둔 뒤 read-only mount합니다. 다운로드 URL과 인증서 갱신 공지는 배포 시점의 [AWS RDS TLS 문서](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)에서 확인합니다.

```bash
sudo install -d -m 755 /etc/catalogguard/rds-ca
sudo curl --fail --silent --show-error --location \
  --output /etc/catalogguard/rds-ca/global-bundle.pem \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
sudo chmod 644 /etc/catalogguard/rds-ca/global-bundle.pem
```

실제 환경변수 파일은 저장소 밖 `/etc/catalogguard/api.env`에 만들고 root만 읽게 합니다. `.env.aws.example`은 변수 이름만 제공하며 실제 `.env.aws`는 Git에서 제외됩니다.

```bash
sudo install -d -m 755 /etc/catalogguard
sudo install -m 600 /dev/null /etc/catalogguard/api.env
sudoedit /etc/catalogguard/api.env
sudo chmod 600 /etc/catalogguard/api.env
```

컨테이너 환경변수는 다음 세 개입니다.

| 이름 | 필수 | 비밀정보 | 코드 기본값 | 값 |
| --- | --- | --- | --- | --- |
| `DATABASE_URL` | 예 | 예 | 없음 | application role로 만든 RDS URL |
| `PGSSLMODE` | 예 | 아니요 | 안전한 코드 기본값 없음 | `verify-full` |
| `PGSSLROOTCERT` | 예 | 아니요 | 없음 | `/run/secrets/rds-ca-bundle.pem` |

`TEST_DATABASE_URL`은 EC2에서 설정하지 않습니다. `AWS_ACCESS_KEY_ID`와 `AWS_SECRET_ACCESS_KEY`도 사용하지 않습니다.

RDS 연결 문자열 형식은 다음과 같습니다.

```text
postgresql://<application-role>:<percent-encoded-password>@<rds-endpoint>:5432/<application-database>
```

비밀번호의 `@`, `:`, `/`, `?`, `#`, `%` 같은 예약 문자는 URL encoding해야 합니다. 현재 `config/database.py`는 이 driverless prefix를 `postgresql+psycopg://`로 바꾸므로 `requirements-api.txt`의 psycopg 3와 호환됩니다. 이미 `postgresql+psycopg://`인 URL도 그대로 사용할 수 있습니다. TLS는 위의 libpq 환경변수로 강제합니다. RDS SSL 동작은 [RDS PostgreSQL SSL 문서](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)를 기준으로 확인합니다.

## 9. Alembic 배포 gate와 컨테이너 시작

새 이미지를 서비스에 반영하기 전에 같은 image, env file, CA mount로 일회성 migration을 실행합니다.

```bash
cd /opt/catalogguard-lite
IMAGE_TAG="$(git rev-parse --short=12 HEAD)"

sudo docker run --rm \
  --env-file /etc/catalogguard/api.env \
  --mount type=bind,src=/etc/catalogguard/rds-ca/global-bundle.pem,dst=/run/secrets/rds-ca-bundle.pem,readonly \
  "catalogguard-lite-api:${IMAGE_TAG}" \
  python -m alembic upgrade head
```

종료 코드가 0일 때만 다음 단계로 진행합니다. 실패하면 기존 컨테이너를 교체하지 않고 로그에서 TLS, 보안 그룹, URL encoding, 권한, migration 충돌을 확인합니다. 임의의 `sleep`으로 실패를 숨기지 않습니다.

현재 revision과 repository head도 같은 실행 조건에서 확인합니다.

```bash
sudo docker run --rm \
  --env-file /etc/catalogguard/api.env \
  --mount type=bind,src=/etc/catalogguard/rds-ca/global-bundle.pem,dst=/run/secrets/rds-ca-bundle.pem,readonly \
  "catalogguard-lite-api:${IMAGE_TAG}" \
  python -m alembic current

sudo docker run --rm "catalogguard-lite-api:${IMAGE_TAG}" python -m alembic heads
```

`current`와 `heads`의 revision이 일치해야 합니다. `Dockerfile.aws`의 기본 `CMD`도 `python -m alembic upgrade head && exec uvicorn ...` 순서이므로, 최종 시작 시 migration이 다시 실패하면 Uvicorn은 시작되지 않습니다.

기존 staging 컨테이너가 없다면 다음처럼 시작합니다. 기존 컨테이너 교체 절차는 rollback 절에서 다룹니다.

```bash
sudo docker run -d \
  --name catalogguard-api-staging \
  --restart unless-stopped \
  --env-file /etc/catalogguard/api.env \
  --mount type=bind,src=/etc/catalogguard/rds-ca/global-bundle.pem,dst=/run/secrets/rds-ca-bundle.pem,readonly \
  --publish 127.0.0.1:8000:8000 \
  "catalogguard-lite-api:${IMAGE_TAG}"
```

DB URL이나 secret을 출력하는 `docker inspect` 형식은 사용하지 않습니다. 상태와 로그만 확인합니다.

```bash
sudo docker ps --filter name=catalogguard-api-staging
sudo docker inspect --format '{{.Config.User}} {{.State.Status}} {{.State.Health.Status}}' catalogguard-api-staging
sudo docker logs --tail 100 catalogguard-api-staging
```

`Config.User`는 `catalogguard`, 상태는 `running`, health는 `healthy`여야 합니다.

## 10. Nginx와 HTTPS

### HTTPS 적용 전

8000은 외부에 열지 않습니다. Session Manager 셸에서 직접 확인합니다.

```bash
curl --fail-with-body --include http://127.0.0.1:8000/health
curl --fail-with-body --include http://127.0.0.1:8000/ready
```

### Nginx reverse proxy

Nginx는 443에서 TLS를 종료하고 `http://127.0.0.1:8000`으로 proxy합니다. 인증서와 private key의 실제 경로는 선택한 발급 도구의 경로로 바꿉니다.

```nginx
server {
    listen 443 ssl;
    server_name <staging-api-domain>;

    ssl_certificate <certificate-path>;
    ssl_certificate_key <private-key-path>;

    client_max_body_size 6m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
    }
}
```

애플리케이션의 CSV 제한은 5 MiB이므로 Nginx `client_max_body_size`는 이를 조금 넘는 `6m`으로 둡니다. 더 작으면 애플리케이션에 도달하기 전에 413이 발생하고, 지나치게 크게 두면 방어 계층이 약해집니다.

설정 후 문법을 검사하고 reload합니다.

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### HTTPS 적용 후

외부에서 오직 staging 도메인의 443으로 검사합니다.

```bash
curl --fail-with-body --include https://<staging-api-domain>/health
curl --fail-with-body --include https://<staging-api-domain>/ready
```

인증서 hostname, chain, 만료일과 자동 또는 수동 갱신 일정을 확인합니다. public IP가 바뀌면 DNS와 Streamlit staging URL이 끊기므로 EC2 stop/start 전에 Elastic IP 사용 여부와 비용을 결정합니다.

## 11. Health, readiness, request ID와 로그 검증

검증 기준은 다음과 같습니다.

- `/health`: HTTP 200, body의 `status`가 `ok`
- `/ready`: HTTP 200, body의 `status`가 `ready`, `database`가 `ok`
- 두 응답 모두 `X-Request-ID` header 존재
- `docker inspect`의 health가 `healthy`
- 애플리케이션 로그에 JSON 구조의 `http_request_completed`, path, status code, request ID 존재
- Uvicorn 기본 access log는 `--no-access-log`로 비활성화

```bash
curl --silent --show-error --dump-header - --output /dev/null https://<staging-api-domain>/health
curl --silent --show-error --dump-header - --output /dev/null https://<staging-api-domain>/ready
sudo docker logs --since 5m catalogguard-api-staging
```

`/health`만 통과하고 `/ready`가 503이면 API 프로세스는 살아 있지만 RDS 연결이 준비되지 않은 상태입니다. RDS SG source, endpoint, DB 상태, CA mount, `PGSSLMODE`, URL encoding, application role 권한을 순서대로 확인합니다. 로그와 지원 요청에 비밀번호나 전체 `DATABASE_URL`을 붙이지 않습니다.

## 12. Streamlit staging 연결

production Streamlit 앱은 그대로 Railway URL을 사용합니다. AWS 검증용으로 별도의 Streamlit Community Cloud staging 앱을 만들고 그 앱의 Secrets에만 다음을 설정합니다.

```toml
CATALOGGUARD_API_BASE_URL = "https://<staging-api-domain>"
CATALOGGUARD_API_TIMEOUT_SECONDS = "10"
```

확인 항목은 다음과 같습니다.

- URL 끝에 불필요한 `/`가 없어도 현재 client가 정규화하는지
- 인증서가 공개 신뢰 chain이고 hostname과 일치하는지
- Streamlit에서 `/health`, CSV 검수, 저장·목록·상세 조회가 동작하는지
- 5 MiB 이하 CSV가 Nginx를 통과하고 초과 파일은 예상대로 거부되는지
- staging 데이터만 RDS에 저장되며 Railway production DB에는 쓰지 않는지

운영 Streamlit Secrets의 `CATALOGGUARD_API_BASE_URL`은 변경하지 않습니다.

## 13. 배포 교체와 rollback

새 image의 migration과 health 검증이 끝난 뒤 교체합니다. 짧은 중단을 허용하는 첫 staging은 다음 순서로 단순하게 운영할 수 있습니다.

1. 이전 image tag를 기록합니다.
2. 새 image로 일회성 migration을 성공시킵니다.
3. 기존 컨테이너를 stop하고 이름을 rollback용으로 변경합니다.
4. 새 컨테이너를 같은 이름·port로 시작합니다.
5. localhost `/health`, `/ready`, 외부 HTTPS를 확인합니다.
6. 실패하면 새 컨테이너를 중지하고 이전 image를 다시 실행합니다.

애플리케이션 image rollback은 DB schema가 이전 코드와 호환될 때만 안전합니다. 자동 `alembic downgrade`는 수행하지 않습니다. 호환되지 않는 migration이면 변경 전에 RDS snapshot을 만들고, 복구가 필요할 때 snapshot으로 새 RDS를 복원한 다음 env file의 endpoint를 바꾸는 별도 승인 절차를 사용합니다.

EC2 재부팅 후 `--restart unless-stopped` 컨테이너, Docker, Nginx 상태를 확인합니다. EC2 stop/start는 public IPv4를 바꿀 수 있습니다. EBS는 stop 시 유지되지만 terminate 시 `DeleteOnTermination` 설정에 따라 삭제될 수 있습니다.

AWS staging 장애 시 production 사용자는 계속 Railway를 사용하므로 영향이 없어야 합니다. 별도 Streamlit staging 앱만 Railway API 주소로 되돌리려면 해당 staging 앱의 `CATALOGGUARD_API_BASE_URL`을 기존 Railway 주소로 복원하고 앱을 재시작합니다. production Streamlit 설정과 Railway 환경변수, Pre-deploy Command, Start Command는 손대지 않습니다.

rollback 관찰 기간이 끝난 뒤에는 이름과 tag를 명시해 이전 컨테이너와 image만 정리합니다. 먼저 `docker ps -a`와 `docker image ls`로 대상을 확인하고 `docker rm <old-container-name>`, `docker image rm catalogguard-lite-api:<old-commit-sha>`를 사용합니다. 범위가 넓은 `docker system prune`은 다른 서비스의 복구용 image까지 지울 수 있으므로 사용하지 않습니다.

AWS staging 절차 자체는 Docker Compose를 사용하지 않습니다. 로컬 Compose로 별도 진단할 때도 `docker compose down -v`는 기존 PostgreSQL named volume과 데이터를 삭제하므로 실행하지 않습니다. 컨테이너 정리와 데이터 삭제를 같은 작업으로 취급하지 말고, 삭제 대상과 백업 여부를 먼저 확인합니다.

## 14. 백업과 장애 복구

- RDS 자동 백업 보존 기간과 backup window를 배포 전에 설정합니다.
- schema 변경 전 수동 snapshot을 생성하고 완료 상태를 확인합니다.
- snapshot 복원은 기존 DB를 덮어쓰지 않고 새 RDS instance를 만듭니다.
- 복원 후 SG, CA/TLS, application role, Alembic revision, `/ready`를 다시 검증합니다.
- 중요한 staging 데이터가 있다면 삭제 전에 별도 export도 검토합니다.
- backup은 실제 restore 연습을 통과해야 복구 수단으로 간주합니다.

자동 백업과 snapshot의 보존·삭제 동작은 [RDS 자동 백업](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.html)을 확인합니다.

## 15. 비용과 리소스 삭제

중지하거나 사용하지 않아도 비용이 계속될 수 있는 항목은 다음과 같습니다.

- 실행 중 EC2 instance와 연결된 EBS volume
- RDS instance, provisioned storage, I/O, backup 초과분
- 수동 RDS snapshot과 보존된 automated backup
- Elastic IP를 포함한 public IPv4
- CloudWatch logs·metrics, data transfer, Route 53 hosted zone 등 선택 서비스

EC2를 stop하면 compute 과금은 멈추지만 EBS와 public IPv4 등은 남을 수 있습니다. RDS는 stop해도 storage와 backup 비용이 남고, 장기간 계속 정지된 상태로 유지되지 않을 수 있으므로 임시 비용 절감 수단으로만 봅니다. 정확한 조건은 [EC2 lifecycle](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html), [RDS stop/start](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html), [VPC pricing](https://aws.amazon.com/vpc/pricing/)에서 확인합니다.

테스트 리소스를 삭제할 때는 다음 순서와 보존 결정을 기록합니다.

1. 별도 Streamlit staging 앱의 AWS URL 사용을 중지합니다.
2. 필요한 로그와 검증 증거를 저장합니다. secret은 저장하지 않습니다.
3. RDS 최종 snapshot을 만들지, 만들고 얼마나 보존할지, 건너뛸지를 명시적으로 결정합니다.
4. deletion protection을 해제해야 한다면 승인 후 해제합니다.
5. RDS를 삭제하고 retained automated backup과 manual snapshot을 별도로 확인합니다.
6. EC2를 terminate하고 EBS volume과 snapshot이 남았는지 확인합니다.
7. Elastic IP/public IPv4, ENI, 보안 그룹, subnet, route, internet gateway의 의존성을 확인해 불필요한 항목을 제거합니다.
8. DNS record와 인증서 갱신 작업을 제거합니다.
9. IAM instance profile·role과 추가한 최소 권한을 제거합니다.
10. Cost Explorer와 청구 대시보드에서 잔여 과금 리소스를 다음 날 다시 확인합니다.

RDS 삭제는 final snapshot과 automated backup 보존 선택에 따라 데이터 손실과 비용이 달라집니다. 콘솔 확인 문구를 읽고 [RDS 삭제 절차](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_DeleteInstance.html)를 확인한 후 실행합니다.

## 16. 첫 실제 구현 순서

1. 서울 리전 지원 버전과 비용을 확인합니다.
2. VPC, subnet, 두 보안 그룹, IAM role을 만듭니다.
3. private RDS를 만들고 자동 백업·암호화를 설정합니다.
4. EC2를 만들고 Session Manager 연결을 확인합니다.
5. Docker, Nginx, psql을 설치합니다.
6. RDS CA와 root 전용 env file을 준비합니다.
7. application role과 빈 database를 만듭니다.
8. 승인된 commit SHA로 `Dockerfile.aws` 이미지를 빌드합니다.
9. 일회성 Alembic migration과 `current`/`heads` 일치를 확인합니다.
10. 컨테이너를 loopback 8000으로 시작하고 localhost health/readiness를 확인합니다.
11. Nginx와 TLS를 구성하고 외부 443 검증을 수행합니다.
12. 별도 Streamlit staging 앱만 AWS URL로 연결합니다.
13. 실제 CSV 저장·목록·상세 조회와 데이터 보존을 확인합니다.
14. rollback 및 snapshot restore 절차를 연습합니다.
15. 수동 배포가 안정된 뒤에만 GitHub Actions 자동 배포를 별도 설계합니다.
