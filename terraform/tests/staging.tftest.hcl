# 역할: 실제 AWS 자격 증명·리소스 없이 mock_provider로 staging 구성의 핵심 보안 조건
# (문서 4·7절)을 검증합니다. command=apply를 쓰지만 mock_provider 하에서는 실제 AWS
# API를 호출하지 않고 로컬 mock 값만으로 계산되므로 실제 리소스는 전혀 생성되지 않습니다.

mock_provider "aws" {}

override_data {
  target = data.aws_vpc.default
  values = {
    id = "vpc-mock00000000"
  }
}

override_data {
  target = data.aws_subnets.default
  values = {
    ids = ["subnet-mock1111111", "subnet-mock2222222"]
  }
}

override_data {
  target = data.aws_ami.amazon_linux_2023
  values = {
    id = "ami-mock00000000"
  }
}

override_data {
  target = data.aws_iam_policy_document.ec2_assume_role
  values = {
    json = jsonencode({
      Version = "2012-10-17"
      Statement = [
        {
          Effect    = "Allow"
          Action    = "sts:AssumeRole"
          Principal = { Service = "ec2.amazonaws.com" }
        }
      ]
    })
  }
}

run "plan_staging_infrastructure" {
  command = apply

  variables {
    rds_master_password           = "MockOnly-NotARealSecret-123!"
    rds_skip_final_snapshot       = false
    rds_final_snapshot_identifier = "catalogguard-lite-staging-final-snapshot"
  }

  # EC2 보안 그룹에는 inbound 규칙이 전혀 없어야 합니다(22/80/443/8000 모두 없음).
  assert {
    condition     = length(aws_security_group.ec2.ingress) == 0
    error_message = "EC2 security group must not define any inbound rule; access is SSM Session Manager only (docs/aws-staging-deployment.md section 4)."
  }

  # RDS는 5432 하나만, 그것도 CIDR이 아니라 EC2 보안 그룹 참조로만 허용해야 합니다.
  assert {
    condition     = length(aws_security_group.rds.ingress) == 1
    error_message = "RDS security group must expose exactly one ingress rule."
  }

  assert {
    condition = (
      tolist(aws_security_group.rds.ingress)[0].from_port == 5432 &&
      tolist(aws_security_group.rds.ingress)[0].to_port == 5432 &&
      length(tolist(aws_security_group.rds.ingress)[0].cidr_blocks) == 0 &&
      length(tolist(aws_security_group.rds.ingress)[0].security_groups) == 1
    )
    error_message = "RDS must allow only TCP 5432 from the EC2 security group, never from a CIDR block."
  }

  # RDS는 공개 접근이 불가능하고 Single-AZ여야 합니다(문서 3·7절).
  assert {
    condition     = aws_db_instance.staging.publicly_accessible == false
    error_message = "RDS must not be publicly accessible."
  }

  assert {
    condition     = aws_db_instance.staging.multi_az == false
    error_message = "Staging RDS is intentionally Single-AZ per docs/aws-staging-deployment.md."
  }

  assert {
    condition     = aws_db_instance.staging.storage_encrypted == true
    error_message = "RDS storage must be encrypted at rest."
  }

  # RDS 삭제 시 final snapshot을 생략하지 않는 기본값을 유지합니다.
  assert {
    condition     = aws_db_instance.staging.skip_final_snapshot == false
    error_message = "RDS must not skip the final snapshot by default."
  }

  # EC2는 SSM instance profile을 사용합니다(key_name은 main.tf에서 아예 설정하지
  # 않으므로 SSH key pair가 만들어지지 않습니다 — mock provider는 미설정 속성에도
  # 임의 값을 채우므로 이 사실은 코드 리뷰로 확인하고 여기서는 검증하지 않습니다).
  assert {
    condition     = aws_instance.api.iam_instance_profile == aws_iam_instance_profile.ec2_ssm.name
    error_message = "EC2 instance must use the SSM instance profile."
  }

  # EC2 IAM role은 AmazonSSMManagedInstanceCore 정책만 사용해야 합니다.
  assert {
    condition     = aws_iam_role_policy_attachment.ec2_ssm_core.policy_arn == "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
    error_message = "EC2 IAM role must attach exactly the AmazonSSMManagedInstanceCore managed policy."
  }
}

run "no_open_internet_ingress" {
  command = apply

  variables {
    rds_master_password           = "MockOnly-NotARealSecret-123!"
    rds_skip_final_snapshot       = false
    rds_final_snapshot_identifier = "catalogguard-lite-staging-final-snapshot"
  }

  # publicly_accessible은 변수로 노출하지 않고 항상 false로 고정되어 있어야 합니다.
  assert {
    condition     = aws_db_instance.staging.publicly_accessible == false
    error_message = "publicly_accessible must stay hardcoded to false and not be configurable via a variable."
  }

  # 두 보안 그룹 중 어느 쪽도 0.0.0.0/0 inbound 규칙을 갖지 않아야 합니다. 이후 누군가
  # ingress 블록을 추가하는 회귀가 생기면 이 assertion이 실패해야 합니다.
  assert {
    condition = alltrue([
      for rule in aws_security_group.ec2.ingress : !contains(coalesce(rule.cidr_blocks, []), "0.0.0.0/0")
    ])
    error_message = "EC2 security group must never allow inbound traffic from 0.0.0.0/0."
  }

  assert {
    condition = alltrue([
      for rule in aws_security_group.rds.ingress : !contains(coalesce(rule.cidr_blocks, []), "0.0.0.0/0")
    ])
    error_message = "RDS security group must never allow inbound traffic from 0.0.0.0/0."
  }
}
