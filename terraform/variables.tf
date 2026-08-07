# 역할: docs/aws-staging-deployment.md에서 실제 수동 검증한 AWS EC2·RDS staging 구성을
# 코드로 나타내기 위한 입력값을 정의합니다. 기본값은 그 문서에 기록된 실제 값을 따릅니다.

variable "aws_region" {
  description = "리소스를 배치할 AWS 리전. 실제 검증은 서울 리전에서 수행했습니다."
  type        = string
  default     = "ap-northeast-2"
}

variable "name_prefix" {
  description = "생성하는 리소스 이름과 태그에 사용하는 접두어."
  type        = string
  default     = "catalogguard-lite-staging"
}

variable "environment" {
  description = "환경 태그 값. staging 전용이며 production Railway 배포와는 분리됩니다."
  type        = string
  default     = "staging"
}

variable "ec2_instance_type" {
  description = "FastAPI를 실행하는 EC2 인스턴스 타입."
  type        = string
  default     = "t3.micro"
}

variable "ec2_root_volume_size_gib" {
  description = "EC2 루트 볼륨 크기(GiB, gp3)."
  type        = number
  default     = 8
}

variable "rds_instance_class" {
  description = "RDS PostgreSQL 인스턴스 클래스."
  type        = string
  default     = "db.t3.micro"
}

variable "rds_allocated_storage_gib" {
  description = "RDS 스토리지 크기(GiB, gp2)."
  type        = number
  default     = 20
}

variable "rds_postgres_engine_version" {
  description = "RDS PostgreSQL 엔진 버전. 실제 배포 시점의 서울 리전 지원 버전을 다시 확인한 뒤 지정합니다."
  type        = string
  default     = "18.3"
}

variable "rds_database_name" {
  description = "RDS에 생성할 초기 database 이름."
  type        = string
  default     = "catalogguard_lite"
}

variable "rds_master_username" {
  description = "RDS 관리자 계정 이름. 애플리케이션은 이 계정을 직접 사용하지 않고, 이 계정으로 접속해 별도 애플리케이션 role(catalogguard_app)을 만듭니다(문서 7절 참고)."
  type        = string
  default     = "catalogguard_admin"
}

variable "rds_master_password" {
  description = "RDS 관리자 계정 비밀번호. default를 두지 않으므로 실제 사용 시 TF_VAR_rds_master_password 환경변수나 별도 secret 저장소에서 반드시 값을 주입해야 합니다. 저장소에는 실제 값을 커밋하지 않습니다."
  type        = string
  sensitive   = true
}

variable "rds_multi_az" {
  description = "RDS Multi-AZ 여부. 실제 검증은 Single-AZ(false)로 수행했습니다."
  type        = bool
  default     = false
}

variable "rds_deletion_protection" {
  description = "RDS 삭제 방지 여부. 기본값은 false이며, 이 값을 true로 바꿔도 이번 MVP는 apply를 수행하지 않습니다."
  type        = bool
  default     = false
}

variable "rds_final_snapshot_identifier" {
  description = "RDS 삭제 시 남길 final snapshot 식별자. skip_final_snapshot=false일 때만 사용합니다."
  type        = string
  default     = null
}

variable "rds_skip_final_snapshot" {
  description = "RDS 삭제 시 final snapshot 생략 여부. 기본값은 false로, 문서 14절의 백업 원칙(삭제 전 snapshot 확인)에 맞춰 실수로 데이터를 잃지 않도록 합니다."
  type        = bool
  default     = false
}

variable "additional_tags" {
  description = "모든 리소스에 추가로 붙일 태그."
  type        = map(string)
  default     = {}
}
