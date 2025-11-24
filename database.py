
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

import datetime
import uuid
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
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


class ImageAsset(Base):
    """Image Assets 데이터베이스 모델"""
    __tablename__ = "image_assets"
    
    image_asset_id = Column(UUID(as_uuid=True), primary_key=True)
    image_type = Column(String(50))
    image_url = Column(Text, nullable=False)
    mask_url = Column(Text)
    width = Column(Integer)
    height = Column(Integer)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"), nullable=True)
    uid = Column(String(255), unique=True)
    pk = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LLMImage(Base):
    """LLM Image 데이터베이스 모델"""
    __tablename__ = "llm_image"
    
    llm_image_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"))
    prompt = Column(Text)
    uid = Column(String(255), unique=True)
    pk = Column(Integer, autoincrement=True, nullable=True)  # SERIAL 타입, DB에서 자동 생성
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LLMTraces(Base):
    """LLM Traces 데이터베이스 모델"""
    __tablename__ = "llm_traces"
    
    llm_trace_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    llm_image_id = Column(UUID(as_uuid=True), ForeignKey("llm_image.llm_image_id"))
    response = Column(JSONB)
    uid = Column(String(255), unique=True)
    pk = Column(Integer, autoincrement=True, nullable=True)  # SERIAL 타입, DB에서 자동 생성
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TestAsset(Base):
    """테스트용 Asset 테이블 (간단한 insert/delete 테스트용)"""
    __tablename__ = "test_assets"
    
    asset_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = Column(String(255), nullable=False)
    asset_url = Column(String(500), nullable=False)
    asset_kind = Column(String(100))  # forbidden_mask, final, etc.
    width = Column(Integer)
    height = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


def get_db():
    """DB 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

