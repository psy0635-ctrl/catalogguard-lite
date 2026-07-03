# 역할: 모든 SQLAlchemy ORM 모델이 함께 상속하는 Base 클래스를 정의합니다.
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # 모든 SQLAlchemy ORM 모델이 상속하는 공통 기준 클래스입니다.
    pass
