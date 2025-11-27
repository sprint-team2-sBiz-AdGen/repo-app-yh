
"""인스타그램 피드 글 생성 라우터"""
########################################################
# GPT를 활용한 인스타그램 피드 글 생성
# - 조정된 광고문구(eng), tone+style, describe product, 
#   store information, gpt prompt를 입력받음
# - 인스타그램 광고문구와 해시태그를 출력
########################################################
# created_at: 2025-01-XX
# updated_at: 2025-01-XX
# author: LEEYH205
# description: Instagram feed post generation using GPT
# version: 0.1.0
# status: development
# tags: instagram, gpt, feed
# dependencies: fastapi, pydantic, openai
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import logging
import uuid
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from models import InstagramFeedIn, InstagramFeedOut
from services.gpt_service import generate_instagram_feed
from database import get_db, InstagramFeed
from config import GPT_MODEL_NAME, GPT_MAX_TOKENS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/yh/instagram", tags=["instagram"])


@router.post("/feed", response_model=InstagramFeedOut)
def create_instagram_feed(body: InstagramFeedIn, db: Session = Depends(get_db)):
    """
    GPT를 사용하여 인스타그램 피드 글 생성 및 DB 저장
    
    입력:
    - refined_ad_copy_eng: 조정된 광고문구 (영어)
    - tone_style: 톤 & 스타일
    - product_description: 제품 설명
    - store_information: 스토어 정보
    - gpt_prompt: GPT 프롬프트
    
    출력:
    - instagram_feed_id: 생성된 피드 ID (UUID)
    - instagram_ad_copy: 인스타그램 광고문구
    - hashtags: 해시태그
    """
    try:
        logger.info(f"인스타그램 피드 글 생성 요청 - tenant_id: {body.tenant_id}")
        
        # GPT 서비스를 사용하여 인스타그램 피드 글 생성
        result = generate_instagram_feed(
            refined_ad_copy_eng=body.refined_ad_copy_eng,
            tone_style=body.tone_style,
            product_description=body.product_description,
            store_information=body.store_information,
            gpt_prompt=body.gpt_prompt
        )
        
        # DB에 저장
        instagram_feed_id = uuid.uuid4()
        instagram_feed = InstagramFeed(
            instagram_feed_id=instagram_feed_id,
            tenant_id=body.tenant_id,
            refined_ad_copy_eng=body.refined_ad_copy_eng,
            tone_style=body.tone_style,
            product_description=body.product_description,
            store_information=body.store_information,
            gpt_prompt=body.gpt_prompt,
            instagram_ad_copy=result["instagram_ad_copy"],
            hashtags=result["hashtags"],
            gpt_model_name=GPT_MODEL_NAME,
            gpt_max_tokens=GPT_MAX_TOKENS,
            gpt_temperature=0.7,
            gpt_prompt_used=result["prompt_used"],
            gpt_response_raw=result.get("gpt_response_raw"),
            latency_ms=result.get("latency_ms"),
            token_usage=result.get("token_usage")
        )
        
        db.add(instagram_feed)
        db.commit()
        db.refresh(instagram_feed)
        
        logger.info(f"✓ 인스타그램 피드 글 생성 및 DB 저장 완료 - instagram_feed_id: {instagram_feed_id}, tenant_id: {body.tenant_id}")
        
        # 응답 생성
        response = InstagramFeedOut(
            instagram_feed_id=str(instagram_feed_id),
            tenant_id=body.tenant_id,
            instagram_ad_copy=result["instagram_ad_copy"],
            hashtags=result["hashtags"],
            prompt_used=result["prompt_used"],
            generated_at=datetime.utcnow().isoformat() + "Z"
        )
        
        return response
        
    except ValueError as e:
        logger.error(f"❌ 설정 오류: {e}")
        if db:
            db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"❌ 인스타그램 피드 글 생성 중 오류: {e}")
        if db:
            db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"인스타그램 피드 글 생성 중 오류가 발생했습니다: {str(e)}")

