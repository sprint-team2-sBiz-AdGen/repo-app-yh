
"""데이터베이스 모델 및 세션 관리"""
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-30
# author: LEEYH205
# description: Database model and session management logic
# version: 1.1.0
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
    job_variants_id = Column(UUID(as_uuid=True), ForeignKey("jobs_variants.job_variants_id"), nullable=True)  # job_variants 연결
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


class JobVariant(Base):
    """Job Variants 데이터베이스 모델"""
    __tablename__ = "jobs_variants"
    
    job_variants_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"))
    img_asset_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"))
    overlaid_img_asset_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"), nullable=True)  # 최종 overlay 이미지 에셋 참조
    creation_order = Column(Integer, nullable=False)
    selected = Column(String(10), default='false')  # BOOLEAN -> String으로 처리 (DB에서 'true'/'false' 문자열)
    status = Column(String(50), default='queued')  # queued, running, done, failed
    current_step = Column(String(255), default='vlm_analyze')  # 'vlm_analyze', 'yolo_detect', 'planner', 'overlay', 'vlm_judge', 'ocr_eval', 'readability_eval', 'iou_eval'
    retry_count = Column(Integer, default=0)  # 재시도 횟수
    pk = Column(Integer, autoincrement=True, nullable=True)  # SERIAL
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


class LLMModel(Base):
    """LLM Models 데이터베이스 모델"""
    __tablename__ = "llm_models"
    
    llm_model_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name = Column(String(255), nullable=False)  # 모델 이름 (예: "gpt-4o-mini")
    model_version = Column(String(255), nullable=True)  # 모델 버전 (예: "2024-07-18")
    provider = Column(String(255), nullable=False)  # 제공자 (예: "openai", "anthropic")
    default_temperature = Column(Float, nullable=True)  # 기본 temperature 설정
    default_max_tokens = Column(Integer, nullable=True)  # 기본 최대 토큰 수
    prompt_token_cost_per_1m = Column(Float, nullable=True)  # 입력 토큰당 비용 (per 1M tokens, USD)
    completion_token_cost_per_1m = Column(Float, nullable=True)  # 출력 토큰당 비용 (per 1M tokens, USD)
    description = Column(Text, nullable=True)  # 모델 설명
    is_active = Column(String(10), default='true')  # 활성화 여부 ('true', 'false')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class InstagramFeed(Base):
    """Instagram Feeds 데이터베이스 모델"""
    __tablename__ = "instagram_feeds"
    
    instagram_feed_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True)  # 파이프라인과 연결 시 사용
    overlay_id = Column(UUID(as_uuid=True), ForeignKey("overlay_layouts.overlay_id"), nullable=True)  # 오버레이 결과와 연결 시 사용
    llm_model_id = Column(UUID(as_uuid=True), ForeignKey("llm_models.llm_model_id"), nullable=True)  # 사용된 LLM 모델
    tenant_id = Column(String(255), nullable=False)  # 테넌트 ID
    
    # 입력 데이터 (요청 시 받은 정보)
    refined_ad_copy_eng = Column(Text, nullable=False)  # 조정된 광고문구 (영어)
    tone_style = Column(Text, nullable=False)  # 톤 & 스타일
    product_description = Column(Text, nullable=False)  # 제품 설명
    store_information = Column(Text, nullable=False)  # 스토어 정보
    gpt_prompt = Column(Text, nullable=False)  # GPT 프롬프트
    
    # 출력 데이터 (생성된 결과)
    instagram_ad_copy = Column(Text, nullable=False)  # 생성된 인스타그램 피드 글
    hashtags = Column(Text, nullable=False)  # 생성된 해시태그
    
    # LLM 실행 메타데이터 (실제 실행 시 사용된 값)
    used_temperature = Column(Float, nullable=True)  # 실제 사용된 temperature (기본값과 다를 수 있음)
    used_max_tokens = Column(Integer, nullable=True)  # 실제 사용된 최대 토큰 수
    gpt_prompt_used = Column(Text, nullable=True)  # 실제 사용된 전체 프롬프트 (디버깅용)
    gpt_response_raw = Column(JSONB, nullable=True)  # GPT API 원본 응답 (디버깅/재생성용)
    
    # 성능 메트릭
    latency_ms = Column(Float, nullable=True)  # GPT API 호출 소요 시간 (밀리초)
    prompt_tokens = Column(Integer, nullable=True)  # 프롬프트 토큰 수 (입력)
    completion_tokens = Column(Integer, nullable=True)  # 생성 토큰 수 (출력)
    total_tokens = Column(Integer, nullable=True)  # 총 토큰 수
    token_usage = Column(JSONB, nullable=True)  # 토큰 사용량 정보 (원본 JSON, 모니터링용)
    
    # 메타데이터
    # pk는 DB에서 자동 생성되므로 SQLAlchemy 모델에서는 제외 (DB 스키마에 따라 다를 수 있음)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


def get_db():
    """DB 세션 의존성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

