# 역할: Terraform과 AWS provider 버전을 고정해, 로컬/CI 실행 결과가 서로 다른 버전 때문에
# 달라지지 않도록 합니다. 이 저장소는 terraform apply/destroy를 실행하지 않으므로(README
# 참고) backend는 별도로 구성하지 않았습니다.
#
# required_version은 CI가 설치하는 실제 Terraform CLI(1.15.8, .github/workflows/test.yml
# 참고)와 맞춰 1.15.x 패치 범위만 허용하고 1.16.x 이상은 자동으로 허용하지 않습니다.
# AWS provider도 6.55.x 패치 범위만 허용해 provider 변경으로 인한 예기치 않은 동작
# 변화를 줄입니다. 실제 선택된 버전은 .terraform.lock.hcl에 고정되어 있습니다.
terraform {
  required_version = "~> 1.15.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.55.0"
    }
  }
}
