# 역할: 다른 도구나 문서가 참조할 수 있는 최소한의 비민감 정보만 출력합니다. RDS
# endpoint·password 같은 민감 정보는 출력하지 않습니다(문서에서도 실제 endpoint와
# 비밀번호를 기록하지 않는 원칙을 따릅니다).

output "ec2_instance_id" {
  description = "FastAPI staging EC2 instance ID."
  value       = aws_instance.api.id
}

output "ec2_security_group_id" {
  description = "EC2 보안 그룹 ID. RDS 보안 그룹이 이 값을 source로 참조합니다."
  value       = aws_security_group.ec2.id
}

output "rds_security_group_id" {
  description = "RDS 보안 그룹 ID."
  value       = aws_security_group.rds.id
}

output "rds_instance_identifier" {
  description = "RDS 인스턴스 식별자(endpoint 아님)."
  value       = aws_db_instance.staging.identifier
}
