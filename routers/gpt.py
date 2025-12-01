
"""GPT 광고 문구 생성 라우터"""
########################################################
# GPT API를 사용한 텍스트 생성 및 변환
# - 영어 광고문구 → 한글 변환
# - 광고 문구 생성
########################################################
# created_at: 2025-11-20
# updated_at: 2025-12-01
# author: LEEYH205
# description: GPT ad copy generation and translation logic
# version: 1.0.0
# status: development
# tags: gpt, ad-copy
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import uuid
import json
import time
import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from models import GPTAdCopyIn, EngToKorIn, EngToKorOut
from services.gpt_service import translate_eng_to_kor
from database import get_db, Job, TxtAdCopyGeneration, LLMTrace, InstagramFeed, LLMModel
from config import GPT_MODEL_NAME

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/gpt", tags=["gpt"])


@router.post("/ad-copy")
def generate_ad_copy(body: GPTAdCopyIn):
    """GPT를 사용한 광고 문구 생성 (Eng -> Kor)"""
    # TODO: 실제 GPT API 연동 구현
    # - Tone + Style, Product Description, Store Information을 prompt로 구성
    # - GPT API 호출하여 영어 광고 문구 생성
    # - 한국어로 번역 (또는 직접 한국어 생성)
    
    # Mock 응답
    prompt = f"""
    Tone and Style: {body.tone_style}
    Product Description: {body.product_description}
    Store Information: {body.store_information}
    """
    
    # Mock 광고 문구
    mock_ad_copy = f"[{body.tone_style}] {body.product_description} - {body.store_information}"
    
    return {
        "ad_copy_text": mock_ad_copy,
        "language": body.language,
        "prompt_used": prompt.strip(),
        "generated_at": "2025-11-20T00:00:00Z"
    }


@router.post("/eng-to-kor", response_model=EngToKorOut)
def eng_to_kor(body: EngToKorIn, db: Session = Depends(get_db)):
    """
    영어 광고문구를 한글로 변환
    
    Args:
        body: EngToKorIn 모델
            - job_id: Job ID
            - tenant_id: Tenant ID
    
    Returns:
        EngToKorOut:
            - job_id: Job ID
            - llm_trace_id: LLM Trace ID
            - ad_copy_gen_id: Ad Copy Generation ID
            - ad_copy_kor: 한글 광고문구
            - status: 상태 ('done' 또는 'failed')
    
    Raises:
        HTTPException 404: job을 찾을 수 없는 경우
        HTTPException 400: 영어 광고문구를 찾을 수 없는 경우
        HTTPException 500: GPT API 호출 또는 DB 저장 중 오류 발생
    """
    try:
        # Step 0: job_id 검증
        try:
            job_id = uuid.UUID(body.job_id)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid UUID format: {str(e)}"
            )
        
        # job 조회 및 검증
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job:
            logger.error(f"Job not found: job_id={body.job_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Job not found: {body.job_id}"
            )
        
        # job의 tenant_id 확인
        if job.tenant_id != body.tenant_id:
            logger.error(f"Job tenant_id mismatch: job.tenant_id={job.tenant_id}, request.tenant_id={body.tenant_id}")
            raise HTTPException(
                status_code=400,
                detail=f"Job tenant_id mismatch"
            )
        
        # Step 1: txt_ad_copy_generations에서 영어 광고문구 조회
        # refined_ad_copy_eng 우선, 없으면 ad_copy_eng 사용
        ad_copy_gen = db.execute(
            text("""
                SELECT 
                    ad_copy_gen_id,
                    COALESCE(refined_ad_copy_eng, ad_copy_eng) AS ad_copy_eng
                FROM txt_ad_copy_generations
                WHERE job_id = :job_id
                  AND (
                      (generation_stage = 'refined_ad_copy' AND refined_ad_copy_eng IS NOT NULL)
                      OR (generation_stage = 'ad_copy_eng' AND ad_copy_eng IS NOT NULL)
                  )
                  AND status = 'done'
                ORDER BY 
                    CASE generation_stage
                        WHEN 'refined_ad_copy' THEN 1
                        WHEN 'ad_copy_eng' THEN 2
                    END,
                    created_at DESC
                LIMIT 1
            """),
            {"job_id": job_id}
        ).first()
        
        if not ad_copy_gen or not ad_copy_gen.ad_copy_eng:
            logger.error(f"English ad copy not found: job_id={job_id}")
            raise HTTPException(
                status_code=400,
                detail=f"English ad copy not found for job_id: {body.job_id}. Please ensure ad_copy_eng or refined_ad_copy_eng exists in txt_ad_copy_generations."
            )
        
        ad_copy_eng = ad_copy_gen.ad_copy_eng
        logger.info(f"Found English ad copy: job_id={job_id}, length={len(ad_copy_eng)}")
        
        # Step 2: LLM 모델 조회
        llm_model = db.query(LLMModel).filter(
            LLMModel.model_name == GPT_MODEL_NAME,
            LLMModel.is_active == 'true'
        ).first()
        
        if not llm_model:
            logger.warning(f"⚠️ LLM 모델을 찾을 수 없습니다: {GPT_MODEL_NAME}. 기본 모델 정보로 저장합니다.")
            llm_model_id = None
        else:
            llm_model_id = llm_model.llm_model_id
        
        # Step 3: GPT API 호출: 영어 → 한글 변환
        try:
            result = translate_eng_to_kor(ad_copy_eng)
            ad_copy_kor = result["ad_copy_kor"]
            latency_ms = result["latency_ms"]
            token_usage = result.get("token_usage")
            gpt_response_raw = result.get("gpt_response_raw")
            prompt_used = result.get("prompt_used")
        except Exception as e:
            logger.error(f"GPT translation failed: {str(e)}", exc_info=True)
            # jobs 테이블 상태를 'failed'로 업데이트
            db.execute(
                text("""
                    UPDATE jobs
                    SET status = 'failed',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE job_id = :job_id
                """),
                {"job_id": job_id}
            )
            db.commit()
            raise HTTPException(
                status_code=500,
                detail=f"GPT translation failed: {str(e)}"
            )
        
        # Step 4: 토큰 사용량 추출 (llm_traces에 저장하기 위해)
        prompt_tokens = token_usage.get("prompt_tokens") if token_usage else None
        completion_tokens = token_usage.get("completion_tokens") if token_usage else None
        total_tokens = token_usage.get("total_tokens") if token_usage else None
        
        # Step 5: llm_traces 레코드 생성
        llm_trace_id = uuid.uuid4()
        
        # 요청 데이터 구성
        request_data = {
            "ad_copy_eng": ad_copy_eng,
            "operation": "eng_to_kor"
        }
        
        # 응답 데이터 구성
        response_data = {
            "ad_copy_kor": ad_copy_kor,
            "token_usage": token_usage
        }
        
        # llm_traces에 저장 (토큰 정보 포함)
        db.execute(
            text("""
                INSERT INTO llm_traces (
                    llm_trace_id, job_id, provider, llm_model_id, operation_type,
                    request, response, latency_ms,
                    prompt_tokens, completion_tokens, total_tokens, token_usage,
                    created_at, updated_at
                )
                VALUES (
                    :llm_trace_id, :job_id, :provider, :llm_model_id, :operation_type,
                    CAST(:request AS jsonb), CAST(:response AS jsonb), :latency_ms,
                    :prompt_tokens, :completion_tokens, :total_tokens, CAST(:token_usage AS jsonb),
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "llm_trace_id": llm_trace_id,
                "job_id": job_id,
                "provider": "gpt",
                "llm_model_id": llm_model_id,
                "operation_type": "eng_to_kor",
                "request": json.dumps(request_data),
                "response": json.dumps(response_data),
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "token_usage": json.dumps(token_usage) if token_usage else None
            }
        )
        
        # Step 6: txt_ad_copy_generations 레코드 생성/업데이트
        ad_copy_gen_id = uuid.uuid4()
        
        # 기존 레코드 확인
        existing_gen = db.execute(
            text("""
                SELECT ad_copy_gen_id
                FROM txt_ad_copy_generations
                WHERE job_id = :job_id
                  AND generation_stage = 'eng_to_kor'
                LIMIT 1
            """),
            {"job_id": job_id}
        ).first()
        
        if existing_gen:
            # 기존 레코드 업데이트
            db.execute(
                text("""
                    UPDATE txt_ad_copy_generations
                    SET llm_trace_id = :llm_trace_id,
                        ad_copy_kor = :ad_copy_kor,
                        status = 'done',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ad_copy_gen_id = :ad_copy_gen_id
                """),
                {
                    "ad_copy_gen_id": existing_gen.ad_copy_gen_id,
                    "llm_trace_id": llm_trace_id,
                    "ad_copy_kor": ad_copy_kor
                }
            )
            ad_copy_gen_id = existing_gen.ad_copy_gen_id
            logger.info(f"Updated existing txt_ad_copy_generations record: ad_copy_gen_id={ad_copy_gen_id}")
        else:
            # 새 레코드 생성
            db.execute(
                text("""
                    INSERT INTO txt_ad_copy_generations (
                        ad_copy_gen_id, job_id, llm_trace_id, generation_stage,
                        ad_copy_kor, status, created_at, updated_at
                    )
                    VALUES (
                        :ad_copy_gen_id, :job_id, :llm_trace_id, :generation_stage,
                        :ad_copy_kor, :status, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "ad_copy_gen_id": ad_copy_gen_id,
                    "job_id": job_id,
                    "llm_trace_id": llm_trace_id,
                    "generation_stage": "eng_to_kor",
                    "ad_copy_kor": ad_copy_kor,
                    "status": "done"
                }
            )
            logger.info(f"Created new txt_ad_copy_generations record: ad_copy_gen_id={ad_copy_gen_id}")
        
        # Step 7: instagram_feeds.ad_copy_kor 업데이트 (기존 레코드가 있으면)
        db.execute(
            text("""
                UPDATE instagram_feeds
                SET ad_copy_kor = :ad_copy_kor,
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id
            """),
            {
                "job_id": job_id,
                "ad_copy_kor": ad_copy_kor
            }
        )
        
        # Step 8: jobs 테이블 업데이트
        db.execute(
            text("""
                UPDATE jobs
                SET current_step = 'ad_copy_gen_kor',
                    status = 'done',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id
            """),
            {"job_id": job_id}
        )
        
        # Step 9: 커밋
        try:
            db.commit()
            logger.info(f"Saved to DB: job_id={job_id}, llm_trace_id={llm_trace_id}, ad_copy_gen_id={ad_copy_gen_id}, latency_ms={latency_ms:.2f}")
        except Exception as e:
            logger.error(f"Failed to commit to DB: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save translation result to database: {str(e)}"
            )
        
        # Step 10: 응답 반환
        return EngToKorOut(
            job_id=body.job_id,
            llm_trace_id=str(llm_trace_id),
            ad_copy_gen_id=str(ad_copy_gen_id),
            ad_copy_kor=ad_copy_kor,
            status="done"
        )
    
    except HTTPException:
        # HTTPException은 그대로 재발생
        raise
    except Exception as e:
        # 예상치 못한 오류
        logger.error(f"Unexpected error in eng_to_kor: {str(e)}", exc_info=True)
        if db:
            try:
                db.execute(
                    text("""
                        UPDATE jobs
                        SET status = 'failed',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE job_id = :job_id
                    """),
                    {"job_id": job_id}
                )
                db.commit()
            except Exception as update_error:
                logger.error(f"Failed to update job status to failed: {update_error}")
            db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )

