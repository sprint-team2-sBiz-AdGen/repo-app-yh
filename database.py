
"""데이터베이스 모델 및 세션 관리"""
########################################################
# TODO: Implement the actual database model and session management logic
#       - OverlayLayout
#       - get_db
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: Database model and session management logic
# version: 0.1.0
# status: development
# tags: database
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.dialects.postgresql import UUID, JSONB
from config import DATABASE_URL

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class OverlayLayout(Base):
    """OverlayLayout 데이터베이스 모델"""
    __tablename__ = "overlay_layouts"
    
    overlay_id = Column(UUID(as_uuid=True), primary_key=True)
    proposal_id = Column(UUID(as_uuid=True), ForeignKey("planner_proposals.proposal_id"))
    layout = Column(JSONB)
    x_ratio = Column(Float)
    y_ratio = Column(Float)
    width_ratio = Column(Float)
    height_ratio = Column(Float)
    text_margin = Column(String(50))
    uid = Column(String(255))
    pk = Column(Integer)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))


def get_db():
    """DB 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

