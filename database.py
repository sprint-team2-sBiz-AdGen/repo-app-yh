
"""데이터베이스 모델 및 세션 관리"""
########################################################
# created_at: 2025-11-20
# updated_at: 2025-12-03
# author: LEEYH205
# description: Database model and session management logic
# version: 1.1.2
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
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True)  # FK: Job 연결 (선택적)
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
    job_variants_id = Column(UUID(as_uuid=True), ForeignKey("jobs_variants.job_variants_id"), nullable=True)  # FK: Job Variant 연결 (병렬 실행 시 variant 구분)
    provider = Column(String(255))  # 'llava', etc.
    prompt_id = Column(UUID(as_uuid=True), ForeignKey("vlm_prompt_assets.prompt_asset_id"), nullable=True)  # FK: VLM 프롬프트 참조
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


class LLMTrace(Base):
    """LLM Traces 데이터베이스 모델"""
    __tablename__ = "llm_traces"
    
    llm_trace_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True)
    provider = Column(String(255), nullable=True)  # 'gpt', 'anthropic', etc.
    llm_model_id = Column(UUID(as_uuid=True), ForeignKey("llm_models.llm_model_id"), nullable=True)  # FK: 사용된 LLM 모델 참조
    tone_style_id = Column(UUID(as_uuid=True), ForeignKey("tone_styles.tone_style_id"), nullable=True)
    enhanced_img_id = Column(UUID(as_uuid=True), ForeignKey("image_assets.image_asset_id"), nullable=True)
    prompt_id = Column(UUID(as_uuid=True), nullable=True)
    operation_type = Column(String(255), nullable=True)  # 'translate', 'prompt', 'ad_copy_gen', 'eng_to_kor', 'feed_gen'
    request = Column(JSONB, nullable=True)
    response = Column(JSONB, nullable=True)
    latency_ms = Column(Float, nullable=True)
    # 토큰 사용량 정보 (모든 LLM 호출의 토큰 정보를 통합 관리)
    prompt_tokens = Column(Integer, nullable=True)  # 프롬프트 토큰 수 (입력)
    completion_tokens = Column(Integer, nullable=True)  # 생성 토큰 수 (출력)
    total_tokens = Column(Integer, nullable=True)  # 총 토큰 수
    token_usage = Column(JSONB, nullable=True)  # 토큰 사용량 정보 원본 (예: {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TxtAdCopyGeneration(Base):
    """Text Ad Copy Generations 데이터베이스 모델"""
    __tablename__ = "txt_ad_copy_generations"
    
    ad_copy_gen_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=False)  # FK: Job과 연결
    llm_trace_id = Column(UUID(as_uuid=True), ForeignKey("llm_traces.llm_trace_id"), nullable=True)  # FK: GPT API 호출 Trace 참조
    generation_stage = Column(String(255), nullable=False)  # 'kor_to_eng', 'ad_copy_eng', 'refined_ad_copy', 'eng_to_kor'
    ad_copy_kor = Column(Text, nullable=True)  # 한글 광고문구 (최종, eng_to_kor 단계에서 생성)
    ad_copy_eng = Column(Text, nullable=True)  # 영어 광고문구 (kor_to_eng, ad_copy_eng 단계에서 생성)
    refined_ad_copy_eng = Column(Text, nullable=True)  # 조정된 영어 광고문구 (refined_ad_copy 단계에서 생성, 선택적)
    status = Column(String(50), default='queued')  # 'queued', 'running', 'done', 'failed'
    pk = Column(Integer, autoincrement=True, nullable=True)  # SERIAL
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class InstagramFeed(Base):
    """Instagram Feeds 데이터베이스 모델 (최적화된 버전)"""
    __tablename__ = "instagram_feeds"
    
    instagram_feed_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.job_id"), nullable=True)  # FK: 파이프라인과 연결
    llm_trace_id = Column(UUID(as_uuid=True), ForeignKey("llm_traces.llm_trace_id"), nullable=True)  # FK: 인스타그램 피드글 생성 GPT API 호출 Trace (토큰 정보는 llm_traces에서 조회)
    overlay_id = Column(UUID(as_uuid=True), ForeignKey("overlay_layouts.overlay_id"), nullable=True)  # FK: 오버레이 결과와 연결 (선택적)
    tenant_id = Column(String(255), nullable=False)  # 테넌트 ID
    
    # 입력 데이터 (필수)
    refined_ad_copy_eng = Column(Text, nullable=False)  # 조정된 광고문구 (영어)
    ad_copy_kor = Column(Text, nullable=True)  # 한글 광고문구 (GPT Eng→Kor 변환 결과, txt_ad_copy_generations에서 조회)
    tone_style = Column(Text, nullable=False)  # 톤 & 스타일
    product_description = Column(Text, nullable=False)  # 제품 설명
    gpt_prompt = Column(Text, nullable=False)  # GPT 프롬프트 (llm_traces.request에서도 조회 가능하지만 빠른 조회를 위해 유지)
    
    # 출력 데이터 (핵심 결과물)
    instagram_ad_copy = Column(Text, nullable=False)  # 생성된 인스타그램 피드 글
    hashtags = Column(Text, nullable=False)  # 생성된 해시태그
    
    # LLM 실행 메타데이터 (llm_traces에 없는 것만, 선택적)
    used_temperature = Column(Float, nullable=True)  # 실제 사용된 temperature (llm_models 기본값과 다를 수 있음, llm_traces.request에서도 조회 가능)
    used_max_tokens = Column(Integer, nullable=True)  # 실제 사용된 최대 토큰 수 (llm_models 기본값과 다를 수 있음, llm_traces.request에서도 조회 가능)
    
    # 성능 메트릭 (간단한 것만, llm_traces.latency_ms와 동일하지만 빠른 조회를 위해 유지)
    latency_ms = Column(Float, nullable=True)  # GPT API 호출 소요 시간 (밀리초, llm_traces.latency_ms와 동일)
    
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

