#!/usr/bin/env python3
"""
JS 파트 테스트 스크립트
ad_copy_gen_kor 실패한 job들에 대해 임의의 ad_copy_eng를 생성하여 테스트
"""
import sys
import uuid
import json
import time
from database import SessionLocal
from sqlalchemy import text
from services.gpt_service import translate_eng_to_kor
from config import GPT_MODEL_NAME
from database import LLMModel
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_test_ad_copy_eng(job_id: str, tenant_id: str, db: Session):
    """테스트용 영어 광고문구 생성"""
    # 1. Job Inputs에서 정보 조회
    job_input = db.execute(text("""
        SELECT desc_kor, tone_style_id
        FROM job_inputs
        WHERE job_id = :job_id
    """), {"job_id": uuid.UUID(job_id)}).first()
    
    if not job_input:
        logger.error(f"JobInput not found: job_id={job_id}")
        return None
    
    desc_kor = job_input.desc_kor or "맛있는 음식"
    tone_style_id = job_input.tone_style_id
    
    # 2. Tone Style 조회
    tone_style = None
    if tone_style_id:
        tone_style = db.execute(text("""
            SELECT tone_style_name
            FROM tone_styles
            WHERE tone_style_id = :tone_style_id
        """), {"tone_style_id": tone_style_id}).first()
    
    tone_style_name = tone_style.tone_style_name if tone_style else "친근한"
    
    # 3. 임의의 영어 광고문구 생성 (간단한 버전)
    # 실제로는 GPT API를 호출해야 하지만, 테스트용으로 간단한 텍스트 사용
    ad_copy_eng = f"Delicious {desc_kor} - Experience the best {tone_style_name} taste!"
    
    # 4. LLM 모델 조회
    llm_model = db.query(LLMModel).filter(
        LLMModel.model_name == GPT_MODEL_NAME,
        LLMModel.is_active == 'true'
    ).first()
    llm_model_id = llm_model.llm_model_id if llm_model else None
    
    # 5. LLM Trace 생성 (모의)
    llm_trace_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO llm_traces (
            llm_trace_id, job_id, llm_model_id,
            provider, operation_type,
            request, response,
            prompt_tokens, completion_tokens, total_tokens,
            token_usage, latency_ms,
            created_at, updated_at
        ) VALUES (
            :llm_trace_id, :job_id, :llm_model_id,
            'gpt', 'ad_copy_eng',
            CAST(:request AS jsonb), CAST(:response AS jsonb),
            :prompt_tokens, :completion_tokens, :total_tokens,
            CAST(:token_usage AS jsonb), :latency_ms,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """), {
        "llm_trace_id": llm_trace_id,
        "job_id": uuid.UUID(job_id),
        "llm_model_id": llm_model_id,
        "request": json.dumps({"desc_kor": desc_kor, "tone_style": tone_style_name}),
        "response": json.dumps({"ad_copy_eng": ad_copy_eng}),
        "prompt_tokens": 50,
        "completion_tokens": 20,
        "total_tokens": 70,
        "token_usage": json.dumps({"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70}),
        "latency_ms": 1000.0
    })
    
    # 6. txt_ad_copy_generations 레코드 생성
    ad_copy_gen_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO txt_ad_copy_generations (
            ad_copy_gen_id, job_id, llm_trace_id,
            generation_stage, ad_copy_eng, status,
            created_at, updated_at
        ) VALUES (
            :ad_copy_gen_id, :job_id, :llm_trace_id,
            'ad_copy_eng', :ad_copy_eng, 'done',
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """), {
        "ad_copy_gen_id": ad_copy_gen_id,
        "job_id": uuid.UUID(job_id),
        "llm_trace_id": llm_trace_id,
        "ad_copy_eng": ad_copy_eng
    })
    
    db.commit()
    logger.info(f"✅ 테스트용 ad_copy_eng 생성 완료: job_id={job_id}, ad_copy_gen_id={ad_copy_gen_id}")
    return ad_copy_gen_id


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 test_js_part_for_job.py <job_id> [tenant_id]")
        sys.exit(1)
    
    job_id = sys.argv[1]
    tenant_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    db = SessionLocal()
    try:
        # Job 확인
        job = db.execute(text("""
            SELECT job_id, tenant_id, status, current_step
            FROM jobs
            WHERE job_id = :job_id
        """), {"job_id": uuid.UUID(job_id)}).first()
        
        if not job:
            logger.error(f"Job not found: {job_id}")
            sys.exit(1)
        
        if tenant_id and job.tenant_id != tenant_id:
            logger.error(f"Tenant ID mismatch: job.tenant_id={job.tenant_id}, provided={tenant_id}")
            sys.exit(1)
        
        logger.info(f"Job 확인: {job.job_id}, Status: {job.status}, Step: {job.current_step}")
        
        # 이미 ad_copy_eng가 있는지 확인
        existing = db.execute(text("""
            SELECT ad_copy_gen_id, generation_stage, ad_copy_eng
            FROM txt_ad_copy_generations
            WHERE job_id = :job_id
              AND generation_stage = 'ad_copy_eng'
              AND status = 'done'
            ORDER BY created_at DESC
            LIMIT 1
        """), {"job_id": uuid.UUID(job_id)}).first()
        
        if existing and existing.ad_copy_eng:
            logger.warning(f"⚠️ 이미 ad_copy_eng가 존재합니다: {existing.ad_copy_gen_id}")
            response = input("기존 레코드를 삭제하고 새로 생성하시겠습니까? (y/n): ")
            if response.lower() == 'y':
                db.execute(text("""
                    DELETE FROM txt_ad_copy_generations
                    WHERE ad_copy_gen_id = :ad_copy_gen_id
                """), {"ad_copy_gen_id": existing.ad_copy_gen_id})
                db.commit()
                logger.info("기존 레코드 삭제 완료")
            else:
                logger.info("작업 취소")
                return
        
        # 테스트용 ad_copy_eng 생성
        ad_copy_gen_id = generate_test_ad_copy_eng(job_id, job.tenant_id, db)
        
        if ad_copy_gen_id:
            logger.info(f"✅ 성공! ad_copy_gen_id: {ad_copy_gen_id}")
            logger.info("이제 ad_copy_gen_kor 단계가 자동으로 진행될 것입니다.")
        else:
            logger.error("❌ 실패")
            
    except Exception as e:
        logger.error(f"오류 발생: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()




