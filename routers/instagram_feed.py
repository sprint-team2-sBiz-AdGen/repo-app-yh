
"""인스타그램 피드 글 생성 라우터"""
########################################################
# GPT를 활용한 인스타그램 피드 글 생성
# - job_id와 tenant_id를 받아서 DB에서 필요한 데이터 조회
# - txt_ad_copy_generations에서 한글 광고문구 조회
# - job_inputs에서 tone_style, product_description 조회
# - stores 테이블에서 스토어 정보 조회
# - 인스타그램 광고문구와 해시태그를 출력
########################################################
# created_at: 2025-11-25
# updated_at: 2025-12-01
# author: LEEYH205
# description: Instagram feed post generation using GPT
# version: 1.0.0
# status: development
# tags: instagram, gpt, feed
# dependencies: fastapi, pydantic, openai
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import logging
import uuid
import json
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from models import InstagramFeedIn, InstagramFeedOut
from services.gpt_service import generate_instagram_feed
from database import get_db, InstagramFeed, LLMModel, Job, JobInput, TxtAdCopyGeneration, LLMTrace
from config import GPT_MODEL_NAME, GPT_MAX_TOKENS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/instagram", tags=["instagram"])


@router.post("/feed", response_model=InstagramFeedOut)
def create_instagram_feed(body: InstagramFeedIn, db: Session = Depends(get_db)):
    """
    GPT를 사용하여 인스타그램 피드 글 생성 및 DB 저장
    
    입력:
    - job_id: Job ID (필수)
    - tenant_id: Tenant ID (필수)
    
    출력:
    - instagram_feed_id: 생성된 피드 ID (UUID)
    - instagram_ad_copy: 인스타그램 광고문구
    - hashtags: 해시태그
    
    처리 과정:
    1. txt_ad_copy_generations에서 한글 광고문구 조회
    2. job_inputs에서 tone_style, product_description 조회
    3. stores 테이블에서 스토어 정보 조회
    4. GPT API 호출하여 인스타그램 피드글 생성
    5. llm_traces 저장
    6. instagram_feeds 저장
    7. jobs 테이블 업데이트
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
        
        logger.info(f"인스타그램 피드 글 생성 요청 - job_id: {body.job_id}, tenant_id: {body.tenant_id}")
        
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
        
        # Step 1: txt_ad_copy_generations에서 한글 광고문구 조회
        ad_copy_kor_row = db.execute(
            text("""
                SELECT ad_copy_kor
                FROM txt_ad_copy_generations
                WHERE job_id = :job_id
                  AND generation_stage = 'eng_to_kor'
                  AND status = 'done'
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"job_id": job_id}
        ).first()
        
        ad_copy_kor = ad_copy_kor_row.ad_copy_kor if ad_copy_kor_row else None
        if not ad_copy_kor:
            logger.warning(f"ad_copy_kor not found in txt_ad_copy_generations: job_id={job_id}")
        
        # Step 2: txt_ad_copy_generations에서 refined_ad_copy_eng 조회
        refined_ad_copy_row = db.execute(
            text("""
                SELECT COALESCE(refined_ad_copy_eng, ad_copy_eng) AS refined_ad_copy_eng
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
        
        refined_ad_copy_eng = refined_ad_copy_row.refined_ad_copy_eng if refined_ad_copy_row else None
        if not refined_ad_copy_eng:
            logger.error(f"refined_ad_copy_eng not found: job_id={job_id}")
            raise HTTPException(
                status_code=400,
                detail=f"English ad copy not found for job_id: {body.job_id}"
            )
        
        # Step 3: job_inputs에서 tone_style, product_description 조회
        job_input = db.query(JobInput).filter(JobInput.job_id == job_id).first()
        if not job_input:
            logger.error(f"JobInput not found: job_id={job_id}")
            raise HTTPException(
                status_code=404,
                detail=f"JobInput not found: {body.job_id}"
            )
        
        product_description = job_input.desc_kor if job_input.desc_kor else ""
        
        # tone_style_id로 tone_styles 테이블에서 톤 & 스타일 정보 조회
        tone_style = ""
        if job_input.tone_style_id:
            tone_style_row = db.execute(
                text("""
                    SELECT kor_name, eng_name
                    FROM tone_styles
                    WHERE tone_style_id = :tone_style_id
                """),
                {"tone_style_id": job_input.tone_style_id}
            ).first()
            
            if tone_style_row:
                tone_style = tone_style_row.kor_name if tone_style_row.kor_name else (tone_style_row.eng_name if tone_style_row.eng_name else "")
        
        # Step 4: jobs.store_id를 통해 stores 테이블에서 스토어 정보 조회
        store_information = ""
        if job.store_id:
            store_row = db.execute(
                text("""
                    SELECT title, body, store_category
                    FROM stores
                    WHERE store_id = :store_id
                """),
                {"store_id": job.store_id}
            ).first()
            
            if store_row:
                # 스토어 정보 조합 (title, body, store_category)
                store_parts = []
                if store_row.title:
                    store_parts.append(store_row.title)
                if store_row.body:
                    store_parts.append(store_row.body)
                if store_row.store_category:
                    store_parts.append(f"카테고리: {store_row.store_category}")
                store_information = ", ".join(store_parts) if store_parts else ""
        
        # Step 5: GPT 프롬프트 구성 (기본값)
        gpt_prompt = "인스타그램에 어울리는 매력적이고 친근한 피드 글을 작성해주세요. 한국어로 작성하고, 자연스럽고 매력적인 톤으로 작성해주세요."
        
        logger.info(f"Data retrieved - refined_ad_copy_eng: {len(refined_ad_copy_eng)} chars, tone_style: {tone_style}, product_description: {len(product_description)} chars, store_information: {len(store_information)} chars")
        
        # Step 6: GPT 서비스를 사용하여 인스타그램 피드 글 생성
        result = generate_instagram_feed(
            refined_ad_copy_eng=refined_ad_copy_eng,
            tone_style=tone_style,
            product_description=product_description,
            store_information=store_information,
            gpt_prompt=gpt_prompt
        )
        
        # Step 7: LLM 모델 조회
        llm_model = db.query(LLMModel).filter(
            LLMModel.model_name == GPT_MODEL_NAME,
            LLMModel.is_active == 'true'
        ).first()
        
        if not llm_model:
            logger.warning(f"⚠️ LLM 모델을 찾을 수 없습니다: {GPT_MODEL_NAME}. 기본 모델 정보로 저장합니다.")
            llm_model_id = None
        else:
            llm_model_id = llm_model.llm_model_id
        
        # Step 8: llm_traces 레코드 생성
        llm_trace_id = uuid.uuid4()
        
        # 요청 데이터 구성
        request_data = {
            "refined_ad_copy_eng": refined_ad_copy_eng,
            "tone_style": tone_style,
            "product_description": product_description,
            "store_information": store_information,
            "gpt_prompt": gpt_prompt,
            "operation": "feed_gen"
        }
        
        # 응답 데이터 구성
        response_data = {
            "instagram_ad_copy": result["instagram_ad_copy"],
            "hashtags": result["hashtags"],
            "token_usage": result.get("token_usage")
        }
        
        # 토큰 사용량 추출 (llm_traces에 저장하기 위해)
        token_usage = result.get("token_usage")
        prompt_tokens = token_usage.get("prompt_tokens") if token_usage else None
        completion_tokens = token_usage.get("completion_tokens") if token_usage else None
        total_tokens = token_usage.get("total_tokens") if token_usage else None
        
        # Step 8: llm_traces에 저장 (토큰 정보 포함)
        db.execute(
            text("""
                INSERT INTO llm_traces (
                    llm_trace_id, job_id, provider, operation_type,
                    request, response, latency_ms,
                    prompt_tokens, completion_tokens, total_tokens, token_usage,
                    created_at, updated_at
                )
                VALUES (
                    :llm_trace_id, :job_id, :provider, :operation_type,
                    CAST(:request AS jsonb), CAST(:response AS jsonb), :latency_ms,
                    :prompt_tokens, :completion_tokens, :total_tokens, CAST(:token_usage AS jsonb),
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
            """),
            {
                "llm_trace_id": llm_trace_id,
                "job_id": job_id,
                "provider": "gpt",
                "operation_type": "feed_gen",
                "request": json.dumps(request_data),
                "response": json.dumps(response_data),
                "latency_ms": result.get("latency_ms"),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "token_usage": json.dumps(token_usage) if token_usage else None
            }
        )
        
        # Step 9: instagram_feeds 테이블에 저장 (최적화된 버전)
        instagram_feed_id = uuid.uuid4()
        
        instagram_feed = InstagramFeed(
            instagram_feed_id=instagram_feed_id,
            job_id=job_id,
            llm_trace_id=llm_trace_id,
            tenant_id=body.tenant_id,
            refined_ad_copy_eng=refined_ad_copy_eng,
            ad_copy_kor=ad_copy_kor,
            tone_style=tone_style,
            product_description=product_description,
            gpt_prompt=gpt_prompt,
            instagram_ad_copy=result["instagram_ad_copy"],
            hashtags=result["hashtags"],
            used_temperature=0.7,  # 실제 사용된 temperature (llm_traces.request에서도 조회 가능)
            used_max_tokens=GPT_MAX_TOKENS,  # 실제 사용된 최대 토큰 수 (llm_traces.request에서도 조회 가능)
            latency_ms=result.get("latency_ms")  # llm_traces.latency_ms와 동일하지만 빠른 조회를 위해 유지
        )
        
        db.add(instagram_feed)
        
        # Step 10: jobs 테이블 업데이트
        db.execute(
            text("""
                UPDATE jobs
                SET current_step = 'instagram_feed_gen',
                    status = 'done',
                    updated_at = CURRENT_TIMESTAMP
                WHERE job_id = :job_id
            """),
            {"job_id": job_id}
        )
        
        # Step 11: 커밋
        try:
            db.commit()
            db.refresh(instagram_feed)
            logger.info(f"✓ 인스타그램 피드 글 생성 및 DB 저장 완료 - instagram_feed_id: {instagram_feed_id}, job_id: {job_id}, llm_trace_id: {llm_trace_id}")
        except Exception as e:
            logger.error(f"Failed to commit to DB: {str(e)}", exc_info=True)
            db.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save instagram feed to database: {str(e)}"
            )
        
        # Step 12: 응답 생성
        response = InstagramFeedOut(
            instagram_feed_id=str(instagram_feed_id),
            tenant_id=body.tenant_id,
            instagram_ad_copy=result["instagram_ad_copy"],
            hashtags=result["hashtags"],
            prompt_used=result["prompt_used"],
            generated_at=datetime.utcnow().isoformat() + "Z"
        )
        
        return response
        
    except HTTPException:
        # HTTPException은 그대로 재발생
        raise
    except ValueError as e:
        logger.error(f"❌ 설정 오류: {e}")
        if db:
            db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 인스타그램 피드 글 생성 중 오류: {e}", exc_info=True)
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
        raise HTTPException(status_code=500, detail=f"인스타그램 피드 글 생성 중 오류가 발생했습니다: {str(e)}")

