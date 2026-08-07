# 역할: docs/aws-staging-deployment.md에서 2026-07-19 수동으로 만들고 검증한 AWS EC2·RDS
# staging 구성을 Terraform 코드로 나타냅니다. 이 저장소에서는 terraform apply/destroy를
# 실행하지 않으며(README 참고), fmt/validate/test(mock provider)로만 검증합니다.

provider "aws" {
  region = var.aws_region
}

locals {
  common_tags = merge(
    {
      Project     = "catalogguard-lite"
      Environment = var.environment
      ManagedBy   = "terraform"
    },
    var.additional_tags,
  )
}

# 기존 Default VPC를 그대로 사용합니다. custom VPC·private subnet 재구성은 이번 범위가
# 아닙니다(문서 3·4절).
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "amazon_linux_2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# EC2 보안 그룹: 실제 검증에서는 22(SSH)·80·443·8000 모두 inbound 규칙이 없었습니다(문서
# 4절). SSM Session Manager로만 접속하고 FastAPI는 EC2 loopback(127.0.0.1:8000)에만
# bind하므로, 이 그룹에는 ingress 블록 자체를 두지 않습니다.
resource "aws_security_group" "ec2" {
  name        = "${var.name_prefix}-ec2-sg"
  description = "CatalogGuard Lite AWS staging EC2. No inbound rules; SSM Session Manager only."
  vpc_id      = data.aws_vpc.default.id

  egress {
    description = "Allow outbound (SSM endpoints, RDS 5432, package installs)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-ec2-sg" })
}

# RDS 보안 그룹: 5432는 인터넷 CIDR이 아니라 EC2 보안 그룹에서만 허용합니다(문서 4절).
resource "aws_security_group" "rds" {
  name        = "${var.name_prefix}-rds-sg"
  description = "CatalogGuard Lite AWS staging RDS. 5432 only from the EC2 security group."
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "PostgreSQL from the EC2 security group only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2.id]
    cidr_blocks     = []
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-rds-sg" })
}

# EC2가 SSH key pair 없이 Systems Manager Session Manager로만 접속할 수 있도록 하는 IAM
# role입니다(문서 5절, 실제 role 이름 CatalogGuardEC2SSMRole).
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ec2_ssm" {
  name               = "${var.name_prefix}-ec2-ssm-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ec2_ssm_core" {
  role       = aws_iam_role.ec2_ssm.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ec2_ssm" {
  name = "${var.name_prefix}-ec2-ssm-profile"
  role = aws_iam_role.ec2_ssm.name
}

# 실제 검증은 Amazon Linux 2023, x86_64, t3.micro, 8 GiB gp3(문서 6절)입니다. SSH key
# pair를 지정하지 않아 key_name이 없고 SSM으로만 접속할 수 있습니다.
resource "aws_instance" "api" {
  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = var.ec2_instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.ec2.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_ssm.name

  # IMDSv2 강제와 루트 볼륨 암호화는 문서에 기록된 2026-07-19 수동 구성에는 없던 값이며,
  # 이번 IaC 작성 시 추가한 표준 보안 기본값입니다. apply하지 않으므로 실제 인스턴스에는
  # 아직 반영되지 않았습니다.
  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.ec2_root_volume_size_gib
    encrypted   = true
  }

  tags = merge(local.common_tags, { Name = "${var.name_prefix}-api" })
}

resource "aws_db_subnet_group" "staging" {
  name       = "${var.name_prefix}-db-subnet-group"
  subnet_ids = data.aws_subnets.default.ids
  tags       = local.common_tags
}

# 실제 검증은 PostgreSQL 18.3-R1, db.t3.micro, Single-AZ, 20 GiB gp2, Public access
# No입니다(문서 3·7절). 애플리케이션은 이 관리자 계정을 직접 쓰지 않고, 이 계정으로
# 접속해 만든 별도 role(catalogguard_app)만 사용합니다.
resource "aws_db_instance" "staging" {
  identifier     = "${var.name_prefix}-db"
  engine         = "postgres"
  engine_version = var.rds_postgres_engine_version
  instance_class = var.rds_instance_class

  allocated_storage = var.rds_allocated_storage_gib
  storage_type      = "gp2"
  storage_encrypted = true

  db_name  = var.rds_database_name
  username = var.rds_master_username
  password = var.rds_master_password

  multi_az                  = var.rds_multi_az
  publicly_accessible       = false
  vpc_security_group_ids    = [aws_security_group.rds.id]
  db_subnet_group_name      = aws_db_subnet_group.staging.name
  deletion_protection       = var.rds_deletion_protection
  skip_final_snapshot       = var.rds_skip_final_snapshot
  final_snapshot_identifier = var.rds_skip_final_snapshot ? null : var.rds_final_snapshot_identifier

  tags = local.common_tags
}
