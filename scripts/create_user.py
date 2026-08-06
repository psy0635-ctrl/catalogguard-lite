"""로그인 계정을 생성하는 bootstrap CLI입니다. 회원가입 API는 없으며 이 스크립트로만 계정을 만듭니다."""

import argparse
import getpass
import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from config.database import DatabaseConfigurationError  # noqa: E402
from db.auth_service import (  # noqa: E402
    VALID_ROLES,
    InvalidRoleError,
    UserAlreadyExistsError,
    create_user,
)
from db.session import get_session_factory  # noqa: E402


PASSWORD_ENV_VAR = "CATALOGGUARD_SEED_USER_PASSWORD"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CatalogGuard Lite 로그인 계정을 생성합니다 (bootstrap 전용, 회원가입 API 없음)."
    )
    parser.add_argument("--username", required=True, help="로그인 아이디 (고유해야 함)")
    parser.add_argument("--role", required=True, choices=VALID_ROLES, help="viewer 또는 operator")
    parser.add_argument(
        "--password",
        default=None,
        help=(
            "비밀번호. 생략하면 CATALOGGUARD_SEED_USER_PASSWORD 환경변수를 사용하고, "
            "그것도 없으면 대화형으로 입력받습니다. 셸 기록에 남으므로 로컬/테스트 계정에만 권장합니다."
        ),
    )
    parser.add_argument(
        "--inactive",
        action="store_true",
        help="생성 직후 계정을 비활성 상태로 만듭니다.",
    )
    return parser


def _resolve_password(cli_password: str | None) -> str:
    if cli_password:
        return cli_password

    env_password = os.environ.get(PASSWORD_ENV_VAR, "")
    if env_password:
        return env_password

    first_entry = getpass.getpass("비밀번호: ")
    second_entry = getpass.getpass("비밀번호 확인: ")
    if first_entry != second_entry:
        print("비밀번호 확인이 일치하지 않습니다.", file=sys.stderr)
        raise SystemExit(1)
    return first_entry


def main(argv: list[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    password = _resolve_password(arguments.password)
    if not password:
        print("비밀번호가 비어 있습니다.", file=sys.stderr)
        return 1

    try:
        with get_session_factory()() as session:
            user = create_user(
                session,
                username=arguments.username,
                password=password,
                role=arguments.role,
                is_active=not arguments.inactive,
            )
    except UserAlreadyExistsError:
        print(f"계정 생성 실패: 이미 존재하는 아이디입니다: {arguments.username}", file=sys.stderr)
        return 1
    except InvalidRoleError as error:
        print(f"계정 생성 실패: {error}", file=sys.stderr)
        return 1
    except (DatabaseConfigurationError, ValueError) as error:
        print(f"계정 생성 실패: {error}", file=sys.stderr)
        return 1

    print("계정 생성 완료")
    print(f"아이디: {user.username}")
    print(f"역할: {user.role}")
    print(f"활성 상태: {'예' if user.is_active else '아니오'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
