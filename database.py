
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
    latency_ms = Column(Float, nullable=True)  # Overlay 실행 시간 (밀리초)
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
    pk = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Tenant(Base):
    """Tenants 데이터베이스 모델"""
    __tablename__ = "tenants"
    
    tenant_id = Column(String(255), primary_key=True)
    display_name = Column(String(255))
    uid = Column(String(255), unique=True)
    pk = Column(Integer, autoincrement=True, nullable=True)  # SERIAL 타입, DB에서 자동 생성
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Job(Base):
    """Jobs 데이터베이스 모델"""
    __tablename__ = "jobs"
    
    job_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), ForeignKey("tenants.tenant_id"))
    store_id = Column(UUID(as_uuid=True), nullable=True)
    status = Column(String(50), default='queued')  # queued, running, done, failed
    current_step = Column(String(255), nullable=True)  # 'vlm_analyze', 'vlm_planner', 'vlm_judge', 'llm_translate', 'llm_prompt', etc.
    version = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class JobInput(Base):
    """Job Inputs 데이터베이스 모델"""
    __tablename__ = "job_inputs"
    
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), primary_key=True)
    img_asset_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"))
    tone_style_id = Column(UUID(as_uuid=True), ForeignKey("tone_styles.tone_style_id"), nullable=True)
    desc_kor = Column(Text, nullable=True)
    desc_eng = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class VLMTrace(Base):
    """VLM Traces 데이터베이스 모델"""
    __tablename__ = "vlm_traces"
    
    vlm_trace_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"))
    provider = Column(String(255))  # 'llava', etc.
    prompt_id = Column(UUID(as_uuid=True), nullable=True)
    operation_type = Column(String(255))  # 'analyze', 'planner', 'judge'
    request = Column(JSONB, nullable=True)
    response = Column(JSONB, nullable=True)
    latency_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Detection(Base):
    """Detections 데이터베이스 모델"""
    __tablename__ = "detections"
    
    detection_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True)  # 같은 job의 detections를 그룹화
    image_asset_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"))
    model_id = Column(UUID(as_uuid=True), ForeignKey("gen_models.model_id"), nullable=True)
    box = Column(JSONB)  # [x1, y1, x2, y2] 형식
    label = Column(String(255))
    score = Column(Float)  # DECIMAL(5,4) -> Float
    pk = Column(Integer, autoincrement=True, nullable=True)  # SERIAL
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class YOLORun(Base):
    """YOLO 실행 결과 메타데이터 모델"""
    __tablename__ = "yolo_runs"
    
    yolo_run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), unique=True)  # 한 job당 하나의 yolo_run
    image_asset_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"))
    forbidden_mask_url = Column(Text, nullable=True)  # 금지 영역 마스크 URL
    model_name = Column(String(255), nullable=True)  # 사용된 모델 이름
    detection_count = Column(Integer, default=0)  # 감지된 객체 개수
    latency_ms = Column(Float, nullable=True)  # YOLO 실행 시간 (밀리초)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlannerProposal(Base):
    """Planner Proposals 데이터베이스 모델"""
    __tablename__ = "planner_proposals"
    
    proposal_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_asset_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"))
    prompt = Column(Text, nullable=True)
    layout = Column(JSONB, nullable=True)  # 레이아웃 정보 (전체 proposals 정보 포함)
    latency_ms = Column(Float, nullable=True)  # Planner 실행 시간 (밀리초)
    pk = Column(Integer, autoincrement=True, nullable=True)  # SERIAL
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


class Evaluation(Base):
    """Evaluations 데이터베이스 모델"""
    __tablename__ = "evaluations"
    
    evaluation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True)
    overlay_id = Column(UUID(as_uuid=True), ForeignKey("overlay_layouts.overlay_id"), nullable=True)
    evaluation_type = Column(String(50), nullable=False)  # 'ocr', 'readability', 'iou', 'llava_judge'
    metrics = Column(JSONB, nullable=False)  # 평가 메트릭
    pk = Column(Integer, autoincrement=True, nullable=True)  # SERIAL
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def get_db():
    """DB 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

