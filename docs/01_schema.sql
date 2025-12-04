-- FeedlyAI Database Schema
-- Version: 2.0
-- Created: 2025-11-16
-- Updated: 2025-12-03

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone to Korea (Asia/Seoul)
SET timezone = 'Asia/Seoul';

-- ============================================
-- 1. 핵심 엔티티 (Core Entities)
-- ============================================

-- USERS 테이블
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    uid VARCHAR(255) UNIQUE,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- TENANTS 테이블 (멀티테넌시)
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(255) PRIMARY KEY,
    display_name VARCHAR(255),
    uid VARCHAR(255) UNIQUE,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- IMAGE_ASSETS 테이블
CREATE TABLE IF NOT EXISTS image_assets (
    image_asset_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    image_type VARCHAR(50),
    image_url TEXT NOT NULL,
    mask_url TEXT,
    width INTEGER,
    height INTEGER,
    creator_id UUID REFERENCES users(user_id),
    tenant_id VARCHAR(255) REFERENCES tenants(tenant_id),
    job_id UUID REFERENCES jobs(job_id),  -- FK: Job 연결 (선택적, 파이프라인에서 생성된 이미지의 경우)
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- STORES 테이블
-- 스토어 정보를 저장하는 테이블
-- jobs.store_id를 통해 참조하여 스토어 정보 조회
CREATE TABLE IF NOT EXISTS stores (
    store_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(user_id),  -- FK: 사용자 ID
    image_id UUID REFERENCES image_assets(image_asset_id),  -- FK: 이미지 ID
    title VARCHAR(500),  -- 스토어 제목
    body TEXT,  -- 스토어 설명 (스토어 정보로 사용, 위치, 인스타 아이디, 링크 등 포함 가능)
    store_category TEXT,  -- 스토어 카테고리
    auto_scoring_flag BOOLEAN DEFAULT FALSE,  -- 자동 점수 계산 플래그
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 2. 생성 모델 파이프라인 (Generative Models)
-- ============================================

-- TONE_STYLES 테이블
CREATE TABLE IF NOT EXISTS tone_styles (
    tone_style_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code TEXT,
    kor_name TEXT,
    eng_name TEXT,
    description TEXT,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PBG_PROMPT_ASSETS 테이블
CREATE TABLE IF NOT EXISTS pbg_prompt_assets (
    prompt_asset_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tone_style_id UUID REFERENCES tone_styles(tone_style_id),
    prompt_type TEXT,
    prompt_version TEXT,
    prompt JSONB,
    negative_prompt JSONB,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PBG_PLACEMENT_PRESETS 테이블
CREATE TABLE IF NOT EXISTS pbg_placement_presets (
    placement_preset_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_type TEXT NOT NULL,  -- prompt_type으로 연결 (pbg_prompt_assets.prompt_type과 동일)
    preset_order INTEGER,  -- 같은 prompt_type 내에서의 순서
    x DECIMAL(5,4) NOT NULL,  -- 0.0 ~ 1.0
    y DECIMAL(5,4) NOT NULL,  -- 0.0 ~ 1.0
    size DECIMAL(5,4) NOT NULL,  -- 0.0 ~ 1.0
    rotation DECIMAL(5,2) NOT NULL DEFAULT 0.0,  -- 회전 각도
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- GEN_MODELS 테이블
CREATE TABLE IF NOT EXISTS gen_models (
    model_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT,  -- Example: "Photo-Background-Generation"
    repo TEXT,  -- Example: "hf repo" (Hugging Face repository)
    version TEXT,
    defaults JSONB,  -- 파라미터들 값 (Parameters' values)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- GEN_RUNS 테이블
CREATE TABLE IF NOT EXISTS gen_runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID REFERENCES jobs(job_id),  -- FK
    tenant_id VARCHAR(255) REFERENCES tenants(tenant_id),  -- FK
    src_asset_id UUID REFERENCES image_assets(image_asset_id),  -- FK, 원본 이미지 (Original image)
    cutout_asset_id UUID REFERENCES image_assets(image_asset_id),  -- FK, 누끼 이미지 (Cutout image)
    model_id UUID REFERENCES gen_models(model_id),  -- FK, 사용 모델 (Used model)
    prompt_version TEXT,  -- FK, 사용 프롬프트 버전 (Used prompt version)
    bg_width INTEGER,  -- 이미지 가로 크기 (Image width)
    bg_height INTEGER,  -- 이미지 세로 크기 (Image height)
    status TEXT DEFAULT 'queued',  -- Possible values: queued/running/done/failed
    latency_ms FLOAT,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE  -- 상태가 done/failed 일때만 (Only when status is done/failed)
);

-- GEN_VARIANTS 테이블
CREATE TABLE IF NOT EXISTS gen_variants (
    gen_variant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID REFERENCES gen_runs(run_id),  -- FK
    index INTEGER,  -- 같은 run 내에서 순번 (Sequence number within the same run)
    canvas_asset_id UUID REFERENCES image_assets(image_asset_id),  -- FK, 캔버스 이미지 id (Canvas image ID)
    mask_asset_id UUID REFERENCES image_assets(image_asset_id),  -- FK, 마스크 이미지 id (Mask image ID)
    bg_asset_id UUID REFERENCES image_assets(image_asset_id),  -- FK, 생성 이미지 id (Generated image ID)
    placement_preset_id UUID REFERENCES pbg_placement_presets(placement_preset_id),  -- FK, 피사체 위치/크기 (Subject position/size)
    prompt_en TEXT,  -- 프롬프트 (prompt)
    negative_en TEXT,  -- 네거티브 프롬프트 (Negative prompt)
    seed_base INTEGER DEFAULT 13,  -- 13 (일단 고정) (13 (fixed for now))
    steps INTEGER DEFAULT 20,  -- 20 (일단 고정) (20 (fixed for now))
    infer_ms FLOAT,  -- 추론시간(ms) (Inference time (ms))
    latency_ms FLOAT,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 3. Job 파이프라인 (Job Pipeline)
-- ============================================

-- JOBS 테이블
CREATE TABLE IF NOT EXISTS jobs (
    job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(255) REFERENCES tenants(tenant_id),  -- FK
    store_id UUID REFERENCES stores(store_id),  -- FK: 스토어 정보 조회용 (stores 테이블 참조)
    status TEXT DEFAULT 'queued',  -- Possible values: queued, running, done, failed
    current_step TEXT,  -- Current pipeline step: 'vlm_analyze', 'vlm_planner', 'vlm_judge', 'llm_translate', 'llm_prompt', etc.
    version TEXT,
    retry_count INTEGER DEFAULT 0,  -- Job 재시도 횟수 (자동 복구 로직에 의해 증가)
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- JOB_INPUTS 테이블
CREATE TABLE IF NOT EXISTS job_inputs (
    job_id UUID PRIMARY KEY REFERENCES jobs(job_id),  -- PK, FK
    img_asset_id UUID REFERENCES image_assets(image_asset_id),  -- FK
    tone_style_id UUID REFERENCES tone_styles(tone_style_id),  -- FK
    desc_kor TEXT,  -- 사용자 입력: 한국어 설명 (30자 이내)
    desc_eng TEXT,  -- GPT Kor→Eng 변환 결과 또는 영어 광고문구
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
-- 참고: 스토어 정보는 jobs.store_id를 통해 stores 테이블에서 조회

-- JOBS_VARIANTS 테이블
CREATE TABLE IF NOT EXISTS jobs_variants (
    job_variants_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID REFERENCES jobs(job_id),  -- FK
    img_asset_id UUID REFERENCES image_assets(image_asset_id),  -- FK
    creation_order INTEGER NOT NULL,
    selected BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'queued',  -- queued, running, done, failed
    current_step TEXT DEFAULT 'vlm_analyze',  -- 'vlm_analyze', 'yolo_detect', 'planner', 'overlay', 'vlm_judge', 'ocr_eval', 'readability_eval', 'iou_eval'
    retry_count INTEGER DEFAULT 0,  -- Variant 재시도 횟수 (자동 복구 로직에 의해 증가)
    overlaid_img_asset_id UUID REFERENCES image_assets(image_asset_id),  -- 최종 오버레이 이미지 asset 참조 (image_type='overlaid')
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- VLM_PROMPT_ASSETS 테이블
CREATE TABLE IF NOT EXISTS vlm_prompt_assets (
    prompt_asset_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_type TEXT,
    prompt_version TEXT,
    prompt JSONB,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- VLM_TRACES 테이블
CREATE TABLE IF NOT EXISTS vlm_traces (
    vlm_trace_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID REFERENCES jobs(job_id),  -- FK
    job_variants_id UUID REFERENCES jobs_variants(job_variants_id) ON DELETE SET NULL,  -- FK: Job Variant 연결 (병렬 실행 시 variant 구분)
    provider TEXT,  -- Example: 'llava'
    prompt_id UUID REFERENCES vlm_prompt_assets(prompt_asset_id) ON DELETE SET NULL,  -- FK: VLM 프롬프트 참조
    operation_type TEXT,  -- Possible values: analyze, planner, judge
    request JSONB,
    response JSONB,
    latency_ms FLOAT,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 4. AI 파이프라인 (app-yh 관련)
-- ============================================

-- DETECTIONS 테이블
CREATE TABLE IF NOT EXISTS detections (
    detection_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    image_asset_id UUID REFERENCES image_assets(image_asset_id),
    model_id UUID REFERENCES gen_models(model_id),
    job_id UUID REFERENCES jobs(job_id),
    box JSONB,  -- [x1, y1, x2, y2] 형식
    label VARCHAR(255),
    score DECIMAL(5,4),
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- YOLO_RUNS 테이블
CREATE TABLE IF NOT EXISTS yolo_runs (
    yolo_run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID UNIQUE REFERENCES jobs(job_id),
    image_asset_id UUID REFERENCES image_assets(image_asset_id),
    forbidden_mask_url TEXT,
    model_name VARCHAR(255),
    detection_count INTEGER DEFAULT 0,
    latency_ms FLOAT,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- PLANNER_PROPOSALS 테이블
CREATE TABLE IF NOT EXISTS planner_proposals (
    proposal_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    image_asset_id UUID REFERENCES image_assets(image_asset_id),
    prompt TEXT,
    layout JSONB,  -- 레이아웃 정보
    latency_ms FLOAT,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- OVERLAY_LAYOUTS 테이블
CREATE TABLE IF NOT EXISTS overlay_layouts (
    overlay_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    proposal_id UUID REFERENCES planner_proposals(proposal_id),
    job_variants_id UUID REFERENCES jobs_variants(job_variants_id),  -- job_variants 연결
    layout JSONB,
    x_ratio DECIMAL(5,4),
    y_ratio DECIMAL(5,4),
    width_ratio DECIMAL(5,4),
    height_ratio DECIMAL(5,4),
    text_margin VARCHAR(50),
    latency_ms FLOAT,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- RENDERS 테이블
CREATE TABLE IF NOT EXISTS renders (
    render_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    overlay_id UUID REFERENCES overlay_layouts(overlay_id),
    image_asset_id UUID REFERENCES image_assets(image_asset_id),  -- 렌더링된 이미지
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- EVALUATIONS 테이블 (평가 결과 저장)
CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID REFERENCES jobs(job_id),  -- FK
    overlay_id UUID REFERENCES overlay_layouts(overlay_id),  -- FK
    evaluation_type VARCHAR(50) NOT NULL,  -- 'llava_judge', 'ocr', 'readability', 'iou'
    metrics JSONB NOT NULL,  -- 평가 메트릭 (타입별로 다른 구조)
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 5. LLM 통합 (LLM Integration)
-- ============================================

-- LLM_MODELS 테이블
CREATE TABLE IF NOT EXISTS llm_models (
    llm_model_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- 모델 기본 정보
    model_name VARCHAR(255) NOT NULL,  -- 모델 이름 (예: "gpt-4o-mini")
    model_version VARCHAR(255),  -- 모델 버전 (예: "2024-07-18")
    provider VARCHAR(255) NOT NULL,  -- 제공자 (예: "openai", "anthropic", "google")
    
    -- 모델 설정 (기본값)
    default_temperature FLOAT,  -- 기본 temperature 설정
    default_max_tokens INTEGER,  -- 기본 최대 토큰 수
    
    -- 비용 정보 (USD per 1M tokens)
    prompt_token_cost_per_1m FLOAT,  -- 입력 토큰당 비용 (per 1M tokens)
    completion_token_cost_per_1m FLOAT,  -- 출력 토큰당 비용 (per 1M tokens)
    
    -- 메타데이터
    description TEXT,  -- 모델 설명
    is_active VARCHAR(10) DEFAULT 'true',  -- 활성화 여부 ('true', 'false')
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- LLM_TRACES 테이블
CREATE TABLE IF NOT EXISTS llm_traces (
    llm_trace_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID REFERENCES jobs(job_id),  -- FK
    provider TEXT,  -- Example: 'gpt'
    llm_model_id UUID REFERENCES llm_models(llm_model_id) ON DELETE SET NULL,  -- FK: 사용된 LLM 모델 참조
    tone_style_id UUID REFERENCES tone_styles(tone_style_id),  -- FK
    enhanced_img_id UUID REFERENCES image_assets(image_asset_id),  -- FK
    prompt_id UUID,  -- FK (pbg_prompt_assets 참조 가능)
    operation_type TEXT,  -- Possible values: translate, prompt
    request JSONB,
    response JSONB,
    latency_ms FLOAT,
    -- 토큰 사용량 정보 (모든 LLM 호출의 토큰 정보를 통합 관리)
    prompt_tokens INTEGER,  -- 프롬프트 토큰 수 (입력)
    completion_tokens INTEGER,  -- 생성 토큰 수 (출력)
    total_tokens INTEGER,  -- 총 토큰 수
    token_usage JSONB,  -- 토큰 사용량 정보 원본 (예: {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300})
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 6. 텍스트 생성 및 광고문구 관리 (Text Generation & Ad Copy Management)
-- ============================================

-- TXT_AD_COPY_GENERATIONS 테이블
-- 광고문구 생성 과정의 모든 단계를 추적하는 테이블
-- JS 파트와 YH 파트 간 데이터 공유 및 Trace 관리
CREATE TABLE IF NOT EXISTS txt_ad_copy_generations (
    ad_copy_gen_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,  -- FK: Job과 연결 (이미지 처리와 동일한 Job)
    llm_trace_id UUID REFERENCES llm_traces(llm_trace_id) ON DELETE SET NULL,  -- FK: GPT API 호출 Trace 참조
    generation_stage TEXT NOT NULL,  -- 생성 단계: 'kor_to_eng', 'ad_copy_eng', 'refined_ad_copy', 'eng_to_kor'
    ad_copy_kor TEXT,  -- 한글 광고문구 (최종, eng_to_kor 단계에서 생성)
    ad_copy_eng TEXT,  -- 영어 광고문구 (kor_to_eng, ad_copy_eng 단계에서 생성)
    refined_ad_copy_eng TEXT,  -- 조정된 영어 광고문구 (refined_ad_copy 단계에서 생성, 선택적)
    status TEXT DEFAULT 'queued',  -- 상태: 'queued', 'running', 'done', 'failed'
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 7. 인스타그램 피드 생성 (Instagram Feed Generation)
-- ============================================

-- INSTAGRAM_FEEDS 테이블 (최적화된 버전)
CREATE TABLE IF NOT EXISTS instagram_feeds (
    instagram_feed_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Foreign Keys (핵심 연결)
    job_id UUID REFERENCES jobs(job_id),  -- FK: 파이프라인과 연결
    llm_trace_id UUID REFERENCES llm_traces(llm_trace_id) ON DELETE SET NULL,  -- FK: 인스타그램 피드글 생성 GPT API 호출 Trace (토큰 정보는 llm_traces에서 조회)
    overlay_id UUID REFERENCES overlay_layouts(overlay_id),  -- FK: 오버레이 결과와 연결 (선택적)
    
    -- Tenant 정보
    tenant_id VARCHAR(255) NOT NULL,  -- 테넌트 ID
    
    -- 입력 데이터 (필수)
    refined_ad_copy_eng TEXT NOT NULL,  -- 조정된 광고문구 (영어)
    ad_copy_kor TEXT,  -- 한글 광고문구 (GPT Eng→Kor 변환 결과, txt_ad_copy_generations에서 조회)
    tone_style TEXT NOT NULL,  -- 톤 & 스타일
    product_description TEXT NOT NULL,  -- 제품 설명
    gpt_prompt TEXT NOT NULL,  -- GPT 프롬프트 (llm_traces.request에서도 조회 가능하지만 빠른 조회를 위해 유지)
    
    -- 출력 데이터 (핵심 결과물)
    instagram_ad_copy TEXT NOT NULL,  -- 생성된 인스타그램 피드 글
    hashtags TEXT NOT NULL,  -- 생성된 해시태그 (예: "#태그1 #태그2 #태그3")
    
    -- LLM 실행 메타데이터 (llm_traces에 없는 것만, 선택적)
    used_temperature FLOAT,  -- 실제 사용된 temperature (llm_models 기본값과 다를 수 있음, llm_traces.request에서도 조회 가능)
    used_max_tokens INTEGER,  -- 실제 사용된 최대 토큰 수 (llm_models 기본값과 다를 수 있음, llm_traces.request에서도 조회 가능)
    
    -- 성능 메트릭 (간단한 것만, llm_traces.latency_ms와 동일하지만 빠른 조회를 위해 유지)
    latency_ms FLOAT,  -- GPT API 호출 소요 시간 (밀리초, llm_traces.latency_ms와 동일)
    
    -- 메타데이터
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 8. 시스템 이벤트 (System Events)
-- ============================================

-- WORKER_EVENTS 테이블
CREATE TABLE IF NOT EXISTS worker_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_type VARCHAR(100),
    status VARCHAR(50),
    start_time TIMESTAMP WITH TIME ZONE,
    end_time TIMESTAMP WITH TIME ZONE,
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- CONNECTED_NODES 테이블
CREATE TABLE IF NOT EXISTS connected_nodes (
    node_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    node_type VARCHAR(100),
    status VARCHAR(50),
    pk SERIAL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 인덱스 생성
-- ============================================

-- Foreign Key 인덱스
CREATE INDEX IF NOT EXISTS idx_image_assets_creator_id ON image_assets(creator_id);
CREATE INDEX IF NOT EXISTS idx_image_assets_tenant_id ON image_assets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_image_assets_job_id ON image_assets(job_id);
CREATE INDEX IF NOT EXISTS idx_stores_user_id ON stores(user_id);
CREATE INDEX IF NOT EXISTS idx_stores_image_id ON stores(image_id);
CREATE INDEX IF NOT EXISTS idx_gen_runs_job_id ON gen_runs(job_id);
CREATE INDEX IF NOT EXISTS idx_gen_runs_tenant_id ON gen_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_gen_runs_model_id ON gen_runs(model_id);
CREATE INDEX IF NOT EXISTS idx_gen_runs_src_asset_id ON gen_runs(src_asset_id);
CREATE INDEX IF NOT EXISTS idx_gen_runs_cutout_asset_id ON gen_runs(cutout_asset_id);
CREATE INDEX IF NOT EXISTS idx_gen_runs_status ON gen_runs(status);
CREATE INDEX IF NOT EXISTS idx_gen_variants_run_id ON gen_variants(run_id);
CREATE INDEX IF NOT EXISTS idx_gen_variants_run_id_index ON gen_variants(run_id, index);
CREATE INDEX IF NOT EXISTS idx_gen_variants_canvas_asset_id ON gen_variants(canvas_asset_id);
CREATE INDEX IF NOT EXISTS idx_gen_variants_mask_asset_id ON gen_variants(mask_asset_id);
CREATE INDEX IF NOT EXISTS idx_gen_variants_bg_asset_id ON gen_variants(bg_asset_id);
CREATE INDEX IF NOT EXISTS idx_gen_variants_placement_preset_id ON gen_variants(placement_preset_id);
CREATE INDEX IF NOT EXISTS idx_detections_image_id ON detections(image_asset_id);
CREATE INDEX IF NOT EXISTS idx_detections_job_id ON detections(job_id);
CREATE INDEX IF NOT EXISTS idx_yolo_runs_job_id ON yolo_runs(job_id);
CREATE INDEX IF NOT EXISTS idx_yolo_runs_image_asset_id ON yolo_runs(image_asset_id);
CREATE INDEX IF NOT EXISTS idx_planner_proposals_image_id ON planner_proposals(image_asset_id);
CREATE INDEX IF NOT EXISTS idx_overlay_layouts_proposal_id ON overlay_layouts(proposal_id);
CREATE INDEX IF NOT EXISTS idx_overlay_layouts_job_variants_id ON overlay_layouts(job_variants_id);
CREATE INDEX IF NOT EXISTS idx_renders_overlay_id ON renders(overlay_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_job_id ON evaluations(job_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_overlay_id ON evaluations(overlay_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_type ON evaluations(evaluation_type);
CREATE INDEX IF NOT EXISTS idx_pbg_prompt_assets_tone_style_id ON pbg_prompt_assets(tone_style_id);
CREATE INDEX IF NOT EXISTS idx_vlm_prompt_assets_prompt_type ON vlm_prompt_assets(prompt_type);
CREATE INDEX IF NOT EXISTS idx_pbg_placement_presets_prompt_type ON pbg_placement_presets(prompt_type);
CREATE INDEX IF NOT EXISTS idx_pbg_placement_presets_prompt_type_order ON pbg_placement_presets(prompt_type, preset_order);
CREATE INDEX IF NOT EXISTS idx_jobs_tenant_id ON jobs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_jobs_store_id ON jobs(store_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_current_step ON jobs(current_step);
CREATE INDEX IF NOT EXISTS idx_jobs_retry_count ON jobs(retry_count);
CREATE INDEX IF NOT EXISTS idx_jobs_status_retry_count ON jobs(status, retry_count);
CREATE INDEX IF NOT EXISTS idx_job_inputs_img_asset_id ON job_inputs(img_asset_id);
CREATE INDEX IF NOT EXISTS idx_job_inputs_tone_style_id ON job_inputs(tone_style_id);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_job_id ON jobs_variants(job_id);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_img_asset_id ON jobs_variants(img_asset_id);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_creation_order ON jobs_variants(creation_order);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_selected ON jobs_variants(selected);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_status ON jobs_variants(status);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_current_step ON jobs_variants(current_step);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_job_id_status ON jobs_variants(job_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_retry_count ON jobs_variants(retry_count);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_status_retry_count ON jobs_variants(status, retry_count);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_job_id_retry_count ON jobs_variants(job_id, retry_count);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_overlaid_img_asset_id ON jobs_variants(overlaid_img_asset_id);
CREATE INDEX IF NOT EXISTS idx_vlm_traces_job_id ON vlm_traces(job_id);
CREATE INDEX IF NOT EXISTS idx_vlm_traces_job_variants_id ON vlm_traces(job_variants_id);
CREATE INDEX IF NOT EXISTS idx_vlm_traces_prompt_id ON vlm_traces(prompt_id);
CREATE INDEX IF NOT EXISTS idx_vlm_traces_operation_type ON vlm_traces(operation_type);
CREATE INDEX IF NOT EXISTS idx_vlm_traces_job_id_variants_id ON vlm_traces(job_id, job_variants_id);
CREATE INDEX IF NOT EXISTS idx_llm_traces_job_id ON llm_traces(job_id);
CREATE INDEX IF NOT EXISTS idx_llm_traces_llm_model_id ON llm_traces(llm_model_id);
CREATE INDEX IF NOT EXISTS idx_llm_traces_tone_style_id ON llm_traces(tone_style_id);
CREATE INDEX IF NOT EXISTS idx_llm_traces_enhanced_img_id ON llm_traces(enhanced_img_id);
CREATE INDEX IF NOT EXISTS idx_llm_traces_prompt_id ON llm_traces(prompt_id);
CREATE INDEX IF NOT EXISTS idx_llm_traces_operation_type ON llm_traces(operation_type);
CREATE INDEX IF NOT EXISTS idx_llm_traces_prompt_tokens ON llm_traces(prompt_tokens);
CREATE INDEX IF NOT EXISTS idx_llm_traces_completion_tokens ON llm_traces(completion_tokens);
CREATE INDEX IF NOT EXISTS idx_llm_traces_total_tokens ON llm_traces(total_tokens);
CREATE INDEX IF NOT EXISTS idx_llm_models_provider ON llm_models(provider);
CREATE INDEX IF NOT EXISTS idx_llm_models_model_name ON llm_models(model_name);
CREATE INDEX IF NOT EXISTS idx_llm_models_is_active ON llm_models(is_active);
CREATE INDEX IF NOT EXISTS idx_txt_ad_copy_generations_job_id ON txt_ad_copy_generations(job_id);
CREATE INDEX IF NOT EXISTS idx_txt_ad_copy_generations_llm_trace_id ON txt_ad_copy_generations(llm_trace_id);
CREATE INDEX IF NOT EXISTS idx_txt_ad_copy_generations_generation_stage ON txt_ad_copy_generations(generation_stage);
CREATE INDEX IF NOT EXISTS idx_txt_ad_copy_generations_status ON txt_ad_copy_generations(status);
CREATE INDEX IF NOT EXISTS idx_txt_ad_copy_generations_job_id_stage ON txt_ad_copy_generations(job_id, generation_stage);
CREATE INDEX IF NOT EXISTS idx_instagram_feeds_job_id ON instagram_feeds(job_id);
CREATE INDEX IF NOT EXISTS idx_instagram_feeds_overlay_id ON instagram_feeds(overlay_id);
CREATE INDEX IF NOT EXISTS idx_instagram_feeds_llm_trace_id ON instagram_feeds(llm_trace_id);
CREATE INDEX IF NOT EXISTS idx_instagram_feeds_tenant_id ON instagram_feeds(tenant_id);

-- 시간 기반 인덱스 (조회 성능 향상)
CREATE INDEX IF NOT EXISTS idx_image_assets_created_at ON image_assets(created_at);
CREATE INDEX IF NOT EXISTS idx_stores_created_at ON stores(created_at);
CREATE INDEX IF NOT EXISTS idx_gen_runs_created_at ON gen_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_job_inputs_created_at ON job_inputs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_variants_created_at ON jobs_variants(created_at);
CREATE INDEX IF NOT EXISTS idx_vlm_traces_created_at ON vlm_traces(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_traces_created_at ON llm_traces(created_at);
CREATE INDEX IF NOT EXISTS idx_txt_ad_copy_generations_created_at ON txt_ad_copy_generations(created_at);
CREATE INDEX IF NOT EXISTS idx_evaluations_created_at ON evaluations(created_at);
CREATE INDEX IF NOT EXISTS idx_instagram_feeds_created_at ON instagram_feeds(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_traces_created_at_tokens ON llm_traces(created_at, total_tokens);

-- JSONB 인덱스 (GIN 인덱스)
CREATE INDEX IF NOT EXISTS idx_detections_box ON detections USING GIN (box);
CREATE INDEX IF NOT EXISTS idx_planner_proposals_layout ON planner_proposals USING GIN (layout);
CREATE INDEX IF NOT EXISTS idx_evaluations_metrics ON evaluations USING GIN (metrics);
CREATE INDEX IF NOT EXISTS idx_pbg_prompt_assets_prompt ON pbg_prompt_assets USING GIN (prompt);
CREATE INDEX IF NOT EXISTS idx_pbg_prompt_assets_negative_prompt ON pbg_prompt_assets USING GIN (negative_prompt);
CREATE INDEX IF NOT EXISTS idx_vlm_prompt_assets_prompt ON vlm_prompt_assets USING GIN (prompt);
CREATE INDEX IF NOT EXISTS idx_gen_models_defaults ON gen_models USING GIN (defaults);
CREATE INDEX IF NOT EXISTS idx_vlm_traces_request ON vlm_traces USING GIN (request);
CREATE INDEX IF NOT EXISTS idx_vlm_traces_response ON vlm_traces USING GIN (response);
CREATE INDEX IF NOT EXISTS idx_llm_traces_request ON llm_traces USING GIN (request);
CREATE INDEX IF NOT EXISTS idx_llm_traces_response ON llm_traces USING GIN (response);
CREATE INDEX IF NOT EXISTS idx_llm_traces_token_usage ON llm_traces USING GIN (token_usage);

-- ============================================
-- 테이블 주석 (Table Comments)
-- ============================================

-- 1. 핵심 엔티티 (Core Entities)
COMMENT ON TABLE users IS 
    '사용자 정보를 저장하는 테이블. 멀티테넌시 환경에서 사용자 식별 및 관리';

COMMENT ON TABLE tenants IS 
    '테넌트 정보를 저장하는 테이블. 멀티테넌시 지원을 위한 테넌트 관리';

COMMENT ON TABLE image_assets IS 
    '이미지 자산을 저장하는 테이블. 원본 이미지, 마스크 이미지, 생성된 이미지 등 모든 이미지 타입 관리';

COMMENT ON TABLE stores IS 
    '스토어 정보를 저장하는 테이블. jobs.store_id를 통해 참조하여 스토어 정보 조회';

-- 2. 생성 모델 파이프라인 (Generative Models)
COMMENT ON TABLE tone_styles IS 
    '톤 & 스타일 정보를 저장하는 테이블. 광고문구 생성 시 사용되는 톤 스타일 정의';

COMMENT ON TABLE pbg_prompt_assets IS 
    'Photo Background Generation 프롬프트 자산을 저장하는 테이블. 배경 생성에 사용되는 프롬프트 관리';

COMMENT ON TABLE pbg_placement_presets IS 
    'Photo Background Generation 피사체 배치 프리셋을 저장하는 테이블. 프롬프트 타입별 피사체 위치/크기/회전 정보';

COMMENT ON TABLE gen_models IS 
    '생성 모델 정보를 저장하는 테이블. Hugging Face 등에서 사용하는 이미지 생성 모델 정의';

COMMENT ON TABLE gen_runs IS 
    '생성 모델 실행 정보를 저장하는 테이블. 배경 생성 작업의 실행 상태 및 메타데이터 관리';

COMMENT ON TABLE gen_variants IS 
    '생성 모델 변형 결과를 저장하는 테이블. 하나의 gen_run에서 생성된 여러 변형 이미지 관리';

-- 3. Job 파이프라인 (Job Pipeline)
COMMENT ON TABLE jobs IS 
    '작업 정보를 저장하는 테이블. 전체 파이프라인 작업의 상태 및 진행 단계 관리';

COMMENT ON TABLE job_inputs IS 
    '작업 입력 정보를 저장하는 테이블. 작업 실행에 필요한 이미지, 톤 스타일, 설명 등 입력 데이터';

COMMENT ON TABLE jobs_variants IS 
    '작업 변형 정보를 저장하는 테이블. 하나의 작업에서 생성된 여러 변형 결과 관리';

COMMENT ON TABLE vlm_prompt_assets IS 
    'Vision Language Model 프롬프트 자산을 저장하는 테이블. VLM 분석, 플래너, 판단에 사용되는 프롬프트 관리';

COMMENT ON TABLE vlm_traces IS 
    'Vision Language Model 실행 추적 정보를 저장하는 테이블. VLM API 호출의 요청/응답 및 성능 메트릭 관리';

-- 4. AI 파이프라인 (app-yh 관련)
COMMENT ON TABLE detections IS 
    '객체 탐지 결과를 저장하는 테이블. YOLO 모델을 통한 이미지 내 객체 탐지 결과 (박스, 라벨, 점수)';

COMMENT ON TABLE yolo_runs IS 
    'YOLO 실행 정보를 저장하는 테이블. YOLO 모델 실행 상태 및 탐지 결과 요약';

COMMENT ON TABLE planner_proposals IS 
    '플래너 제안 결과를 저장하는 테이블. 텍스트 오버레이 레이아웃 제안 정보';

COMMENT ON TABLE overlay_layouts IS 
    '오버레이 레이아웃 정보를 저장하는 테이블. 텍스트 오버레이의 위치, 크기, 여백 등 레이아웃 정보';

COMMENT ON TABLE renders IS 
    '렌더링 결과를 저장하는 테이블. 오버레이 레이아웃을 적용한 최종 렌더링 이미지';

COMMENT ON TABLE evaluations IS 
    '평가 결과를 저장하는 테이블. VLM 판단, OCR 평가, 가독성 평가, IoU 평가 등 다양한 평가 메트릭';

-- 5. LLM 통합 (LLM Integration)
COMMENT ON TABLE llm_models IS 
    'LLM 모델 정보를 저장하는 테이블. OpenAI, Anthropic, Google 등 LLM 제공자의 모델 정의 및 비용 정보';

COMMENT ON TABLE llm_traces IS 
    'LLM 실행 추적 정보를 저장하는 테이블. LLM API 호출의 요청/응답, 토큰 사용량, 성능 메트릭 통합 관리';

-- 6. 텍스트 생성 및 광고문구 관리
COMMENT ON TABLE txt_ad_copy_generations IS 
    '광고문구 생성 과정의 모든 단계를 추적하는 테이블. JS 파트(kor_to_eng, ad_copy_eng)와 YH 파트(refined_ad_copy, eng_to_kor) 간 데이터 공유 및 Trace 관리';

-- 7. 인스타그램 피드 생성
COMMENT ON TABLE instagram_feeds IS 
    '인스타그램 피드 생성 결과를 저장하는 테이블. 생성된 인스타그램 피드 글, 해시태그 및 관련 메타데이터';

-- 8. 시스템 이벤트 (System Events)
COMMENT ON TABLE worker_events IS 
    '워커 이벤트 정보를 저장하는 테이블. 시스템 워커의 실행 상태 및 이벤트 추적';

COMMENT ON TABLE connected_nodes IS 
    '연결된 노드 정보를 저장하는 테이블. 시스템 내 연결된 노드의 상태 관리';

COMMENT ON COLUMN txt_ad_copy_generations.generation_stage IS 
    '생성 단계: kor_to_eng (한→영 변환, JS 파트), ad_copy_eng (영어 광고문구 생성, JS 파트), refined_ad_copy (조정, YH 파트, 선택적), eng_to_kor (영→한 변환, YH 파트)';

COMMENT ON COLUMN txt_ad_copy_generations.llm_trace_id IS 
    'llm_traces 테이블 참조. 각 단계의 GPT API 호출 Trace. vlm_traces와 동일한 패턴으로 관리';

COMMENT ON COLUMN txt_ad_copy_generations.ad_copy_eng IS 
    '영어 광고문구. kor_to_eng 단계에서는 영어 설명, ad_copy_eng 단계에서는 영어 광고문구 저장';

COMMENT ON COLUMN txt_ad_copy_generations.refined_ad_copy_eng IS 
    '조정된 영어 광고문구. vlm_analyze 검증 결과에 따라 refined_ad_copy 단계에서 생성 (선택적)';

COMMENT ON COLUMN txt_ad_copy_generations.ad_copy_kor IS 
    '한글 광고문구. eng_to_kor 단계에서 생성된 최종 한글 광고문구';

-- llm_traces 테이블 토큰 관련 주석 추가
COMMENT ON COLUMN llm_traces.prompt_tokens IS 
    '프롬프트 토큰 수 (입력). 모든 LLM 호출의 토큰 정보를 통합 관리';

COMMENT ON COLUMN llm_traces.completion_tokens IS 
    '생성 토큰 수 (출력). 모든 LLM 호출의 토큰 정보를 통합 관리';

COMMENT ON COLUMN llm_traces.total_tokens IS 
    '총 토큰 수. prompt_tokens + completion_tokens';

COMMENT ON COLUMN llm_traces.token_usage IS 
    '토큰 사용량 정보 원본 (JSONB). 예: {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300}';

-- instagram_feeds 테이블 주석 추가
COMMENT ON COLUMN instagram_feeds.llm_trace_id IS 
    'llm_traces 테이블 참조. 인스타그램 피드글 생성 GPT API 호출 Trace. 토큰 정보는 llm_traces에서 조회';

COMMENT ON COLUMN instagram_feeds.ad_copy_kor IS 
    '한글 광고문구. GPT Eng→Kor 변환 결과. txt_ad_copy_generations.ad_copy_kor에서 조회';

COMMENT ON COLUMN instagram_feeds.latency_ms IS 
    'GPT API 호출 소요 시간 (밀리초). llm_traces.latency_ms와 동일하지만 빠른 조회를 위해 유지';

-- jobs 테이블 주석 추가
COMMENT ON COLUMN jobs.store_id IS 
    'stores 테이블 참조. 스토어 정보는 jobs.store_id를 통해 stores 테이블에서 조회 (stores.title, stores.body, stores.store_category 등)';

-- ============================================
-- 컬럼 주석 (Column Comments)
-- ============================================

-- 1. 핵심 엔티티 (Core Entities)
-- users 테이블 컬럼 주석
COMMENT ON COLUMN users.user_id IS '사용자 고유 식별자 (UUID)';
COMMENT ON COLUMN users.uid IS '사용자 고유 ID (문자열, UNIQUE)';
COMMENT ON COLUMN users.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN users.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN users.updated_at IS '레코드 수정 시간';

-- tenants 테이블 컬럼 주석
COMMENT ON COLUMN tenants.tenant_id IS '테넌트 고유 식별자 (PRIMARY KEY)';
COMMENT ON COLUMN tenants.display_name IS '테넌트 표시 이름';
COMMENT ON COLUMN tenants.uid IS '테넌트 고유 ID (문자열, UNIQUE)';
COMMENT ON COLUMN tenants.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN tenants.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN tenants.updated_at IS '레코드 수정 시간';

-- image_assets 테이블 컬럼 주석
COMMENT ON COLUMN image_assets.image_asset_id IS '이미지 자산 고유 식별자 (UUID)';
COMMENT ON COLUMN image_assets.image_type IS '이미지 타입 (예: original, mask, generated, overlaid 등)';
COMMENT ON COLUMN image_assets.image_url IS '이미지 URL (필수)';
COMMENT ON COLUMN image_assets.mask_url IS '마스크 이미지 URL (선택적)';
COMMENT ON COLUMN image_assets.width IS '이미지 가로 크기 (픽셀)';
COMMENT ON COLUMN image_assets.height IS '이미지 세로 크기 (픽셀)';
COMMENT ON COLUMN image_assets.creator_id IS 'FK: 이미지 생성자 ID (users 테이블 참조)';
COMMENT ON COLUMN image_assets.tenant_id IS 'FK: 테넌트 ID (tenants 테이블 참조)';
COMMENT ON COLUMN image_assets.job_id IS 'FK: Job ID (jobs 테이블 참조, 선택적, 파이프라인에서 생성된 이미지의 경우)';
COMMENT ON COLUMN image_assets.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN image_assets.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN image_assets.updated_at IS '레코드 수정 시간';

-- stores 테이블 컬럼 주석 (일부는 이미 있음)
COMMENT ON COLUMN stores.store_id IS '스토어 고유 식별자 (UUID)';
COMMENT ON COLUMN stores.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN stores.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN stores.updated_at IS '레코드 수정 시간';

-- 2. 생성 모델 파이프라인 (Generative Models)
-- tone_styles 테이블 컬럼 주석
COMMENT ON COLUMN tone_styles.tone_style_id IS '톤 스타일 고유 식별자 (UUID)';
COMMENT ON COLUMN tone_styles.code IS '톤 스타일 코드';
COMMENT ON COLUMN tone_styles.kor_name IS '톤 스타일 한글 이름';
COMMENT ON COLUMN tone_styles.eng_name IS '톤 스타일 영어 이름';
COMMENT ON COLUMN tone_styles.description IS '톤 스타일 설명';
COMMENT ON COLUMN tone_styles.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN tone_styles.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN tone_styles.updated_at IS '레코드 수정 시간';

-- pbg_prompt_assets 테이블 컬럼 주석
COMMENT ON COLUMN pbg_prompt_assets.prompt_asset_id IS '프롬프트 자산 고유 식별자 (UUID)';
COMMENT ON COLUMN pbg_prompt_assets.tone_style_id IS 'FK: 톤 스타일 ID (tone_styles 테이블 참조)';
COMMENT ON COLUMN pbg_prompt_assets.prompt_type IS '프롬프트 타입 (예: Hero Dish Focus, Seasonal 등)';
COMMENT ON COLUMN pbg_prompt_assets.prompt_version IS '프롬프트 버전 (예: v1)';
COMMENT ON COLUMN pbg_prompt_assets.prompt IS '프롬프트 내용 (JSONB, 다국어 지원)';
COMMENT ON COLUMN pbg_prompt_assets.negative_prompt IS '네거티브 프롬프트 내용 (JSONB)';
COMMENT ON COLUMN pbg_prompt_assets.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN pbg_prompt_assets.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN pbg_prompt_assets.updated_at IS '레코드 수정 시간';

-- pbg_placement_presets 테이블 컬럼 주석
COMMENT ON COLUMN pbg_placement_presets.placement_preset_id IS '배치 프리셋 고유 식별자 (UUID)';
COMMENT ON COLUMN pbg_placement_presets.prompt_type IS '프롬프트 타입 (pbg_prompt_assets.prompt_type과 동일, 필수)';
COMMENT ON COLUMN pbg_placement_presets.preset_order IS '같은 prompt_type 내에서의 순서';
COMMENT ON COLUMN pbg_placement_presets.x IS '피사체 X 좌표 (0.0 ~ 1.0, 필수)';
COMMENT ON COLUMN pbg_placement_presets.y IS '피사체 Y 좌표 (0.0 ~ 1.0, 필수)';
COMMENT ON COLUMN pbg_placement_presets.size IS '피사체 크기 (0.0 ~ 1.0, 필수)';
COMMENT ON COLUMN pbg_placement_presets.rotation IS '피사체 회전 각도 (기본값: 0.0)';
COMMENT ON COLUMN pbg_placement_presets.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN pbg_placement_presets.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN pbg_placement_presets.updated_at IS '레코드 수정 시간';

-- gen_models 테이블 컬럼 주석
COMMENT ON COLUMN gen_models.model_id IS '생성 모델 고유 식별자 (UUID)';
COMMENT ON COLUMN gen_models.name IS '모델 이름 (예: Photo-Background-Generation)';
COMMENT ON COLUMN gen_models.repo IS '모델 저장소 (예: Hugging Face repository)';
COMMENT ON COLUMN gen_models.version IS '모델 버전';
COMMENT ON COLUMN gen_models.defaults IS '모델 기본 파라미터 값 (JSONB)';
COMMENT ON COLUMN gen_models.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN gen_models.updated_at IS '레코드 수정 시간';

-- gen_runs 테이블 컬럼 주석
COMMENT ON COLUMN gen_runs.run_id IS '생성 실행 고유 식별자 (UUID)';
COMMENT ON COLUMN gen_runs.job_id IS 'FK: 작업 ID (jobs 테이블 참조)';
COMMENT ON COLUMN gen_runs.tenant_id IS 'FK: 테넌트 ID (tenants 테이블 참조)';
COMMENT ON COLUMN gen_runs.src_asset_id IS 'FK: 원본 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN gen_runs.cutout_asset_id IS 'FK: 누끼 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN gen_runs.model_id IS 'FK: 사용 모델 ID (gen_models 테이블 참조)';
COMMENT ON COLUMN gen_runs.prompt_version IS '사용 프롬프트 버전';
COMMENT ON COLUMN gen_runs.bg_width IS '생성 이미지 가로 크기 (픽셀)';
COMMENT ON COLUMN gen_runs.bg_height IS '생성 이미지 세로 크기 (픽셀)';
COMMENT ON COLUMN gen_runs.status IS '실행 상태 (queued, running, done, failed)';
COMMENT ON COLUMN gen_runs.latency_ms IS '실행 소요 시간 (밀리초)';
COMMENT ON COLUMN gen_runs.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN gen_runs.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN gen_runs.finished_at IS '실행 완료 시간 (status가 done/failed일 때만)';

-- gen_variants 테이블 컬럼 주석
COMMENT ON COLUMN gen_variants.gen_variant_id IS '생성 변형 고유 식별자 (UUID)';
COMMENT ON COLUMN gen_variants.run_id IS 'FK: 생성 실행 ID (gen_runs 테이블 참조)';
COMMENT ON COLUMN gen_variants.index IS '같은 run 내에서의 순번';
COMMENT ON COLUMN gen_variants.canvas_asset_id IS 'FK: 캔버스 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN gen_variants.mask_asset_id IS 'FK: 마스크 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN gen_variants.bg_asset_id IS 'FK: 생성된 배경 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN gen_variants.placement_preset_id IS 'FK: 피사체 위치/크기 프리셋 ID (pbg_placement_presets 테이블 참조)';
COMMENT ON COLUMN gen_variants.prompt_en IS '사용된 프롬프트 (영어)';
COMMENT ON COLUMN gen_variants.negative_en IS '사용된 네거티브 프롬프트 (영어)';
COMMENT ON COLUMN gen_variants.seed_base IS '시드 값 (기본값: 13)';
COMMENT ON COLUMN gen_variants.steps IS '추론 스텝 수 (기본값: 20)';
COMMENT ON COLUMN gen_variants.infer_ms IS '추론 소요 시간 (밀리초)';
COMMENT ON COLUMN gen_variants.latency_ms IS '전체 소요 시간 (밀리초)';
COMMENT ON COLUMN gen_variants.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN gen_variants.created_at IS '레코드 생성 시간';

-- 3. Job 파이프라인 (Job Pipeline)
-- jobs 테이블 컬럼 주석
COMMENT ON COLUMN jobs.job_id IS '작업 고유 식별자 (UUID)';
COMMENT ON COLUMN jobs.tenant_id IS 'FK: 테넌트 ID (tenants 테이블 참조)';
COMMENT ON COLUMN jobs.status IS '작업 상태 (queued, running, done, failed)';
COMMENT ON COLUMN jobs.current_step IS '현재 파이프라인 단계 (vlm_analyze, vlm_planner, vlm_judge, llm_translate, llm_prompt 등)';
COMMENT ON COLUMN jobs.version IS '작업 버전';
COMMENT ON COLUMN jobs.retry_count IS '작업 재시도 횟수 (자동 복구 로직에 의해 증가)';
COMMENT ON COLUMN jobs.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN jobs.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN jobs.updated_at IS '레코드 수정 시간';

-- job_inputs 테이블 컬럼 주석
COMMENT ON COLUMN job_inputs.job_id IS 'PK, FK: 작업 ID (jobs 테이블 참조)';
COMMENT ON COLUMN job_inputs.img_asset_id IS 'FK: 입력 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN job_inputs.tone_style_id IS 'FK: 톤 스타일 ID (tone_styles 테이블 참조)';
COMMENT ON COLUMN job_inputs.desc_kor IS '사용자 입력: 한국어 설명 (30자 이내)';
COMMENT ON COLUMN job_inputs.desc_eng IS 'GPT Kor→Eng 변환 결과 또는 영어 광고문구';
COMMENT ON COLUMN job_inputs.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN job_inputs.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN job_inputs.updated_at IS '레코드 수정 시간';

-- jobs_variants 테이블 컬럼 주석
COMMENT ON COLUMN jobs_variants.job_variants_id IS '작업 변형 고유 식별자 (UUID)';
COMMENT ON COLUMN jobs_variants.job_id IS 'FK: 작업 ID (jobs 테이블 참조)';
COMMENT ON COLUMN jobs_variants.img_asset_id IS 'FK: 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN jobs_variants.creation_order IS '생성 순서 (NOT NULL)';
COMMENT ON COLUMN jobs_variants.selected IS '선택 여부 (기본값: FALSE)';
COMMENT ON COLUMN jobs_variants.status IS '변형 상태 (queued, running, done, failed)';
COMMENT ON COLUMN jobs_variants.current_step IS '현재 단계 (vlm_analyze, yolo_detect, planner, overlay, vlm_judge, ocr_eval, readability_eval, iou_eval)';
COMMENT ON COLUMN jobs_variants.retry_count IS '변형 재시도 횟수 (자동 복구 로직에 의해 증가)';
COMMENT ON COLUMN jobs_variants.overlaid_img_asset_id IS 'FK: 최종 오버레이 이미지 ID (image_assets 테이블 참조, image_type=overlaid)';
COMMENT ON COLUMN jobs_variants.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN jobs_variants.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN jobs_variants.updated_at IS '레코드 수정 시간';

-- vlm_prompt_assets 테이블 컬럼 주석
COMMENT ON COLUMN vlm_prompt_assets.prompt_asset_id IS 'VLM 프롬프트 자산 고유 식별자 (UUID)';
COMMENT ON COLUMN vlm_prompt_assets.prompt_type IS '프롬프트 타입 (analyze, planner, judge 등)';
COMMENT ON COLUMN vlm_prompt_assets.prompt_version IS '프롬프트 버전';
COMMENT ON COLUMN vlm_prompt_assets.prompt IS '프롬프트 내용 (JSONB)';
COMMENT ON COLUMN vlm_prompt_assets.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN vlm_prompt_assets.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN vlm_prompt_assets.updated_at IS '레코드 수정 시간';

-- vlm_traces 테이블 컬럼 주석
COMMENT ON COLUMN vlm_traces.vlm_trace_id IS 'VLM 추적 고유 식별자 (UUID)';
COMMENT ON COLUMN vlm_traces.job_id IS 'FK: 작업 ID (jobs 테이블 참조)';
COMMENT ON COLUMN vlm_traces.job_variants_id IS 'FK: 작업 변형 ID (jobs_variants 테이블 참조, 병렬 실행 시 variant 구분)';
COMMENT ON COLUMN vlm_traces.provider IS 'VLM 제공자 (예: llava)';
COMMENT ON COLUMN vlm_traces.prompt_id IS 'FK: VLM 프롬프트 ID (vlm_prompt_assets 테이블 참조)';
COMMENT ON COLUMN vlm_traces.operation_type IS '작업 타입 (analyze, planner, judge)';
COMMENT ON COLUMN vlm_traces.request IS 'VLM API 요청 내용 (JSONB)';
COMMENT ON COLUMN vlm_traces.response IS 'VLM API 응답 내용 (JSONB)';
COMMENT ON COLUMN vlm_traces.latency_ms IS 'VLM API 호출 소요 시간 (밀리초)';
COMMENT ON COLUMN vlm_traces.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN vlm_traces.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN vlm_traces.updated_at IS '레코드 수정 시간';

-- 4. AI 파이프라인 (app-yh 관련)
-- detections 테이블 컬럼 주석
COMMENT ON COLUMN detections.detection_id IS '탐지 결과 고유 식별자 (UUID)';
COMMENT ON COLUMN detections.image_asset_id IS 'FK: 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN detections.model_id IS 'FK: 사용 모델 ID (gen_models 테이블 참조)';
COMMENT ON COLUMN detections.job_id IS 'FK: 작업 ID (jobs 테이블 참조)';
COMMENT ON COLUMN detections.box IS '객체 박스 좌표 (JSONB, [x1, y1, x2, y2] 형식)';
COMMENT ON COLUMN detections.label IS '객체 라벨';
COMMENT ON COLUMN detections.score IS '탐지 신뢰도 점수 (0.0 ~ 1.0)';
COMMENT ON COLUMN detections.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN detections.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN detections.updated_at IS '레코드 수정 시간';

-- yolo_runs 테이블 컬럼 주석
COMMENT ON COLUMN yolo_runs.yolo_run_id IS 'YOLO 실행 고유 식별자 (UUID)';
COMMENT ON COLUMN yolo_runs.job_id IS 'FK: 작업 ID (jobs 테이블 참조, UNIQUE)';
COMMENT ON COLUMN yolo_runs.image_asset_id IS 'FK: 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN yolo_runs.forbidden_mask_url IS '금지 영역 마스크 URL';
COMMENT ON COLUMN yolo_runs.model_name IS '사용된 YOLO 모델 이름';
COMMENT ON COLUMN yolo_runs.detection_count IS '탐지된 객체 개수 (기본값: 0)';
COMMENT ON COLUMN yolo_runs.latency_ms IS 'YOLO 실행 소요 시간 (밀리초)';
COMMENT ON COLUMN yolo_runs.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN yolo_runs.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN yolo_runs.updated_at IS '레코드 수정 시간';

-- planner_proposals 테이블 컬럼 주석
COMMENT ON COLUMN planner_proposals.proposal_id IS '플래너 제안 고유 식별자 (UUID)';
COMMENT ON COLUMN planner_proposals.image_asset_id IS 'FK: 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN planner_proposals.prompt IS '플래너 프롬프트';
COMMENT ON COLUMN planner_proposals.layout IS '레이아웃 정보 (JSONB)';
COMMENT ON COLUMN planner_proposals.latency_ms IS '플래너 실행 소요 시간 (밀리초)';
COMMENT ON COLUMN planner_proposals.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN planner_proposals.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN planner_proposals.updated_at IS '레코드 수정 시간';

-- overlay_layouts 테이블 컬럼 주석
COMMENT ON COLUMN overlay_layouts.overlay_id IS '오버레이 레이아웃 고유 식별자 (UUID)';
COMMENT ON COLUMN overlay_layouts.proposal_id IS 'FK: 플래너 제안 ID (planner_proposals 테이블 참조)';
COMMENT ON COLUMN overlay_layouts.job_variants_id IS 'FK: 작업 변형 ID (jobs_variants 테이블 참조)';
COMMENT ON COLUMN overlay_layouts.layout IS '레이아웃 정보 (JSONB)';
COMMENT ON COLUMN overlay_layouts.x_ratio IS '텍스트 X 위치 비율 (0.0 ~ 1.0)';
COMMENT ON COLUMN overlay_layouts.y_ratio IS '텍스트 Y 위치 비율 (0.0 ~ 1.0)';
COMMENT ON COLUMN overlay_layouts.width_ratio IS '텍스트 너비 비율 (0.0 ~ 1.0)';
COMMENT ON COLUMN overlay_layouts.height_ratio IS '텍스트 높이 비율 (0.0 ~ 1.0)';
COMMENT ON COLUMN overlay_layouts.text_margin IS '텍스트 여백';
COMMENT ON COLUMN overlay_layouts.latency_ms IS '오버레이 레이아웃 생성 소요 시간 (밀리초)';
COMMENT ON COLUMN overlay_layouts.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN overlay_layouts.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN overlay_layouts.updated_at IS '레코드 수정 시간';

-- renders 테이블 컬럼 주석
COMMENT ON COLUMN renders.render_id IS '렌더링 결과 고유 식별자 (UUID)';
COMMENT ON COLUMN renders.overlay_id IS 'FK: 오버레이 레이아웃 ID (overlay_layouts 테이블 참조)';
COMMENT ON COLUMN renders.image_asset_id IS 'FK: 렌더링된 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN renders.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN renders.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN renders.updated_at IS '레코드 수정 시간';

-- evaluations 테이블 컬럼 주석
COMMENT ON COLUMN evaluations.evaluation_id IS '평가 결과 고유 식별자 (UUID)';
COMMENT ON COLUMN evaluations.job_id IS 'FK: 작업 ID (jobs 테이블 참조)';
COMMENT ON COLUMN evaluations.overlay_id IS 'FK: 오버레이 레이아웃 ID (overlay_layouts 테이블 참조)';
COMMENT ON COLUMN evaluations.evaluation_type IS '평가 타입 (llava_judge, ocr, readability, iou)';
COMMENT ON COLUMN evaluations.metrics IS '평가 메트릭 (JSONB, 타입별로 다른 구조)';
COMMENT ON COLUMN evaluations.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN evaluations.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN evaluations.updated_at IS '레코드 수정 시간';

-- 5. LLM 통합 (LLM Integration)
-- llm_models 테이블 컬럼 주석
COMMENT ON COLUMN llm_models.llm_model_id IS 'LLM 모델 고유 식별자 (UUID)';
COMMENT ON COLUMN llm_models.model_name IS '모델 이름 (예: gpt-4o-mini, 필수)';
COMMENT ON COLUMN llm_models.model_version IS '모델 버전 (예: 2024-07-18)';
COMMENT ON COLUMN llm_models.provider IS '제공자 (예: openai, anthropic, google, 필수)';
COMMENT ON COLUMN llm_models.default_temperature IS '기본 temperature 설정';
COMMENT ON COLUMN llm_models.default_max_tokens IS '기본 최대 토큰 수';
COMMENT ON COLUMN llm_models.prompt_token_cost_per_1m IS '입력 토큰당 비용 (USD per 1M tokens)';
COMMENT ON COLUMN llm_models.completion_token_cost_per_1m IS '출력 토큰당 비용 (USD per 1M tokens)';
COMMENT ON COLUMN llm_models.description IS '모델 설명';
COMMENT ON COLUMN llm_models.is_active IS '활성화 여부 (true, false, 기본값: true)';
COMMENT ON COLUMN llm_models.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN llm_models.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN llm_models.updated_at IS '레코드 수정 시간';

-- llm_traces 테이블 컬럼 주석 (일부는 이미 있음)
COMMENT ON COLUMN llm_traces.llm_trace_id IS 'LLM 추적 고유 식별자 (UUID)';
COMMENT ON COLUMN llm_traces.job_id IS 'FK: 작업 ID (jobs 테이블 참조)';
COMMENT ON COLUMN llm_traces.provider IS 'LLM 제공자 (예: gpt)';
COMMENT ON COLUMN llm_traces.llm_model_id IS 'FK: 사용된 LLM 모델 ID (llm_models 테이블 참조)';
COMMENT ON COLUMN llm_traces.tone_style_id IS 'FK: 톤 스타일 ID (tone_styles 테이블 참조)';
COMMENT ON COLUMN llm_traces.enhanced_img_id IS 'FK: 향상된 이미지 ID (image_assets 테이블 참조)';
COMMENT ON COLUMN llm_traces.prompt_id IS 'FK: 프롬프트 ID (pbg_prompt_assets 테이블 참조 가능)';
COMMENT ON COLUMN llm_traces.operation_type IS '작업 타입 (translate, prompt)';
COMMENT ON COLUMN llm_traces.request IS 'LLM API 요청 내용 (JSONB)';
COMMENT ON COLUMN llm_traces.response IS 'LLM API 응답 내용 (JSONB)';
COMMENT ON COLUMN llm_traces.latency_ms IS 'LLM API 호출 소요 시간 (밀리초)';
COMMENT ON COLUMN llm_traces.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN llm_traces.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN llm_traces.updated_at IS '레코드 수정 시간';

-- 6. 텍스트 생성 및 광고문구 관리
-- txt_ad_copy_generations 테이블 컬럼 주석 (일부는 이미 있음)
COMMENT ON COLUMN txt_ad_copy_generations.ad_copy_gen_id IS '광고문구 생성 고유 식별자 (UUID)';
COMMENT ON COLUMN txt_ad_copy_generations.job_id IS 'FK: 작업 ID (jobs 테이블 참조, NOT NULL, CASCADE DELETE)';
COMMENT ON COLUMN txt_ad_copy_generations.status IS '생성 상태 (queued, running, done, failed, 기본값: queued)';
COMMENT ON COLUMN txt_ad_copy_generations.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN txt_ad_copy_generations.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN txt_ad_copy_generations.updated_at IS '레코드 수정 시간';

-- 7. 인스타그램 피드 생성
-- instagram_feeds 테이블 컬럼 주석 (일부는 이미 있음)
COMMENT ON COLUMN instagram_feeds.instagram_feed_id IS '인스타그램 피드 고유 식별자 (UUID)';
COMMENT ON COLUMN instagram_feeds.job_id IS 'FK: 작업 ID (jobs 테이블 참조)';
COMMENT ON COLUMN instagram_feeds.overlay_id IS 'FK: 오버레이 레이아웃 ID (overlay_layouts 테이블 참조, 선택적)';
COMMENT ON COLUMN instagram_feeds.tenant_id IS '테넌트 ID (필수)';
COMMENT ON COLUMN instagram_feeds.refined_ad_copy_eng IS '조정된 광고문구 (영어, 필수)';
COMMENT ON COLUMN instagram_feeds.tone_style IS '톤 & 스타일 (필수)';
COMMENT ON COLUMN instagram_feeds.product_description IS '제품 설명 (필수)';
COMMENT ON COLUMN instagram_feeds.gpt_prompt IS 'GPT 프롬프트 (필수, llm_traces.request에서도 조회 가능하지만 빠른 조회를 위해 유지)';
COMMENT ON COLUMN instagram_feeds.instagram_ad_copy IS '생성된 인스타그램 피드 글 (필수)';
COMMENT ON COLUMN instagram_feeds.hashtags IS '생성된 해시태그 (필수, 예: #태그1 #태그2 #태그3)';
COMMENT ON COLUMN instagram_feeds.used_temperature IS '실제 사용된 temperature (llm_models 기본값과 다를 수 있음)';
COMMENT ON COLUMN instagram_feeds.used_max_tokens IS '실제 사용된 최대 토큰 수 (llm_models 기본값과 다를 수 있음)';
COMMENT ON COLUMN instagram_feeds.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN instagram_feeds.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN instagram_feeds.updated_at IS '레코드 수정 시간';

-- 8. 시스템 이벤트 (System Events)
-- worker_events 테이블 컬럼 주석
COMMENT ON COLUMN worker_events.event_id IS '워커 이벤트 고유 식별자 (UUID)';
COMMENT ON COLUMN worker_events.event_type IS '이벤트 타입';
COMMENT ON COLUMN worker_events.status IS '이벤트 상태';
COMMENT ON COLUMN worker_events.start_time IS '이벤트 시작 시간';
COMMENT ON COLUMN worker_events.end_time IS '이벤트 종료 시간';
COMMENT ON COLUMN worker_events.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN worker_events.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN worker_events.updated_at IS '레코드 수정 시간';

-- connected_nodes 테이블 컬럼 주석
COMMENT ON COLUMN connected_nodes.node_id IS '노드 고유 식별자 (UUID)';
COMMENT ON COLUMN connected_nodes.node_type IS '노드 타입';
COMMENT ON COLUMN connected_nodes.status IS '노드 상태';
COMMENT ON COLUMN connected_nodes.pk IS '자동 증가 기본 키 (SERIAL)';
COMMENT ON COLUMN connected_nodes.created_at IS '레코드 생성 시간';
COMMENT ON COLUMN connected_nodes.updated_at IS '레코드 수정 시간';




