
"""GPT 서비스"""
########################################################
# GPT API를 사용한 텍스트 생성 서비스
# - OpenAI API 연동
# - 인스타그램 피드 글 생성
# - 해시태그 생성
########################################################
# created_at: 2025-01-XX
# updated_at: 2025-01-XX
# author: LEEYH205
# description: GPT service for text generation
# version: 0.1.0
# status: development
# tags: gpt, service
# dependencies: openai, fastapi
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import os
import time
import json
import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from config import GPT_API_KEY, GPT_MODEL_NAME, GPT_MAX_TOKENS

logger = logging.getLogger(__name__)

# OpenAI 클라이언트 초기화
_client: Optional[OpenAI] = None


def get_gpt_client() -> OpenAI:
    """OpenAI 클라이언트 가져오기 (싱글톤 패턴)"""
    global _client
    if _client is None:
        api_key = GPT_API_KEY
        if not api_key:
            raise ValueError("OPENAPI_KEY 또는 GPT_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일에 OPENAPI_KEY를 설정해주세요.")
        _client = OpenAI(api_key=api_key)
    return _client


def generate_instagram_feed(
    refined_ad_copy_eng: str,
    tone_style: str,
    product_description: str,
    store_information: str,
    gpt_prompt: str
) -> Dict[str, Any]:
    """
    GPT를 사용하여 인스타그램 피드 글 생성
    
    Args:
        refined_ad_copy_eng: 조정된 광고문구 (영어)
        tone_style: 톤 & 스타일
        product_description: 제품 설명
        store_information: 스토어 정보
        gpt_prompt: GPT 프롬프트
    
    Returns:
        Dict[str, Any]: {
            "instagram_ad_copy": 인스타그램 광고문구,
            "hashtags": 해시태그 문자열,
            "prompt_used": 사용된 프롬프트,
            "latency_ms": API 호출 소요 시간 (밀리초),
            "token_usage": 토큰 사용량 정보,
            "gpt_response_raw": GPT API 원본 응답 (JSONB 형식)
        }
    """
    try:
        client = get_gpt_client()
        
        # 프롬프트 구성
        system_prompt = """You are an expert Instagram content creator specializing in creating engaging ad copy and relevant hashtags for Korean audiences. 
Your task is to create compelling Instagram feed posts in Korean that:
1. Are engaging and authentic
2. Match the brand's tone and style
3. Include relevant hashtags (5-10 hashtags)
4. Are optimized for Instagram's format
5. Encourage user engagement

Format your response as JSON with the following structure:
{
    "instagram_ad_copy": "The main Instagram post text in Korean",
    "hashtags": "#hashtag1 #hashtag2 #hashtag3 ..."
}

Separate the hashtags with spaces, and make sure they are relevant to the product, store, and Korean market."""
        
        user_prompt = f"""{gpt_prompt}

**Refined Ad Copy (English):**
{refined_ad_copy_eng}

**Tone & Style:**
{tone_style}

**Product Description:**
{product_description}

**Store Information:**
{store_information}

Please create an engaging Instagram feed post in Korean based on the above information. The post should be natural, engaging, and include relevant hashtags for the Korean market."""

        # GPT API 호출 (latency 측정)
        start_time = time.time()
        response = client.chat.completions.create(
            model=GPT_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=GPT_MAX_TOKENS,
            temperature=0.7,
            response_format={"type": "json_object"}  # JSON 형식으로 응답 받기
        )
        latency_ms = (time.time() - start_time) * 1000  # 밀리초로 변환
        
        # 응답 파싱
        response_text = response.choices[0].message.content
        result = json.loads(response_text)
        
        instagram_ad_copy = result.get("instagram_ad_copy", "")
        hashtags = result.get("hashtags", "")
        
        # 프롬프트 구성 (디버깅용)
        prompt_used = f"System: {system_prompt}\n\nUser: {user_prompt}"
        
        # 토큰 사용량 추출
        token_usage = None
        if hasattr(response, 'usage') and response.usage:
            token_usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        
        # GPT API 원본 응답 (JSONB 형식으로 저장 가능하도록 dict로 변환)
        gpt_response_raw = None
        try:
            # OpenAI 응답 객체를 dict로 변환
            gpt_response_raw = {
                "id": response.id,
                "object": response.object,
                "created": response.created,
                "model": response.model,
                "choices": [
                    {
                        "index": choice.index,
                        "message": {
                            "role": choice.message.role,
                            "content": choice.message.content
                        },
                        "finish_reason": choice.finish_reason
                    }
                    for choice in response.choices
                ],
                "usage": token_usage
            }
        except Exception as e:
            logger.warning(f"GPT 응답 원본 저장 중 오류: {e}")
        
        logger.info(f"✓ 인스타그램 피드 글 생성 완료 (latency: {latency_ms:.2f}ms)")
        logger.debug(f"생성된 글 길이: {len(instagram_ad_copy)}자, 해시태그: {hashtags}")
        
        return {
            "instagram_ad_copy": instagram_ad_copy,
            "hashtags": hashtags,
            "prompt_used": prompt_used,
            "latency_ms": latency_ms,
            "token_usage": token_usage,
            "gpt_response_raw": gpt_response_raw
        }
        
    except Exception as e:
        logger.error(f"❌ GPT API 호출 중 오류: {e}")
        raise

