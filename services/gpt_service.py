
"""GPT 서비스"""
########################################################
# GPT API를 사용한 텍스트 생성 서비스
# - OpenAI API 연동
# - 인스타그램 피드 글 생성
# - 해시태그 생성
########################################################
# created_at: 2025-11-26
# updated_at: 2025-12-01
# author: LEEYH205
# description: GPT service for text generation and translation
# version: 1.1.0
# status: production
# tags: gpt, service, translation
# dependencies: openai, fastapi
# license: MIT
# copyright: 2025 FeedlyAI Team
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
3. MUST include 5-10 relevant hashtags (this is REQUIRED, not optional)
4. Are optimized for Instagram's format
5. Encourage user engagement

IMPORTANT: You MUST always include hashtags in your response. The hashtags field must never be empty.

Format your response as JSON with the following structure:
{
    "instagram_ad_copy": "The main Instagram post text in Korean (without hashtags in the main text)",
    "hashtags": "#hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5 ..."
}

Rules for hashtags:
- MUST include 5-10 hashtags
- Each hashtag must start with # symbol
- Separate hashtags with a single space
- Use Korean hashtags relevant to the product, store, and Korean market
- Include popular Korean food/restaurant hashtags like #맛집 #맛스타그램 #먹스타그램 #푸드스타그램
- Include location-based hashtags if store information is provided
- Hashtags should be in Korean (한글)

Example format:
{
    "instagram_ad_copy": "맛있는 부대찌개를 만나보세요! ...",
    "hashtags": "#부대찌개 #맛집 #서울맛집 #강남맛집 #한국음식 #맛스타그램 #먹스타그램 #푸드스타그램 #맛있는음식 #데일리"
}"""
        
        user_prompt = f"""{gpt_prompt}

**Refined Ad Copy (English):**
{refined_ad_copy_eng}

**Tone & Style:**
{tone_style}

**Product Description:**
{product_description}

**Store Information:**
{store_information}

Please create an engaging Instagram feed post in Korean based on the above information. 

Requirements:
1. Write the main post text in Korean (natural, engaging, and authentic)
2. DO NOT include hashtags in the main post text
3. MUST include 5-10 relevant Korean hashtags in the "hashtags" field
4. Hashtags should be related to: the product name, food category, location (if provided), and popular Korean Instagram food hashtags
5. Make sure the hashtags field is never empty"""

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
        hashtags = result.get("hashtags", "").strip()
        
        # 해시태그가 비어있거나 없을 경우 fallback 처리
        if not hashtags:
            logger.warning("⚠️ GPT 응답에 해시태그가 없습니다. 기본 해시태그 생성 시도...")
            # 기본 해시태그 생성 (제품 설명에서 키워드 추출)
            fallback_hashtags = []
            if product_description:
                # 제품명 추출 시도
                if "부대찌개" in product_description:
                    fallback_hashtags.append("#부대찌개")
                if "맛집" in product_description or "맛" in product_description:
                    fallback_hashtags.append("#맛집")
            # 기본 해시태그 추가
            fallback_hashtags.extend([
                "#맛스타그램", "#먹스타그램", "#푸드스타그램", 
                "#한국음식", "#데일리"
            ])
            if store_information and ("서울" in store_information or "강남" in store_information):
                fallback_hashtags.append("#서울맛집")
                if "강남" in store_information:
                    fallback_hashtags.append("#강남맛집")
            
            hashtags = " ".join(fallback_hashtags[:10])  # 최대 10개
            logger.info(f"✓ Fallback 해시태그 생성: {hashtags}")
        
        # 해시태그 정리 (공백 정리, 중복 제거)
        hashtag_list = [tag.strip() for tag in hashtags.split() if tag.strip().startswith("#")]
        hashtags = " ".join(list(dict.fromkeys(hashtag_list)))  # 중복 제거하면서 순서 유지
        
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


def translate_eng_to_kor(ad_copy_eng: str) -> Dict[str, Any]:
    """
    GPT를 사용하여 영어 광고문구를 한글로 변환
    
    Args:
        ad_copy_eng: 영어 광고문구
    
    Returns:
        Dict[str, Any]: {
            "ad_copy_kor": 한글 광고문구,
            "prompt_used": 사용된 프롬프트,
            "latency_ms": API 호출 소요 시간 (밀리초),
            "token_usage": 토큰 사용량 정보,
            "gpt_response_raw": GPT API 원본 응답 (JSONB 형식)
        }
    """
    try:
        client = get_gpt_client()
        
        # 프롬프트 구성
        system_prompt = """You are an expert translator specializing in translating English ad copy to Korean.
Your task is to translate English advertising copy into natural, engaging Korean that:
1. Maintains the original meaning and intent
2. Sounds natural and authentic in Korean
3. Preserves the marketing tone and style
4. Is appropriate for Korean audiences
5. Keeps the same length and impact as the original

Return only the Korean translation without any additional explanation or formatting."""
        
        user_prompt = f"""Translate the following English ad copy to Korean:

{ad_copy_eng}

Please provide only the Korean translation, maintaining the original tone and style."""

        # GPT API 호출 (latency 측정)
        start_time = time.time()
        response = client.chat.completions.create(
            model=GPT_MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=GPT_MAX_TOKENS,
            temperature=0.3,  # 번역은 일관성을 위해 낮은 temperature 사용
        )
        latency_ms = (time.time() - start_time) * 1000  # 밀리초로 변환
        
        # 응답 파싱
        response_text = response.choices[0].message.content.strip()
        ad_copy_kor = response_text
        
        # 프롬프트 구성 (디버깅용)
        prompt_used = f"System: {system_prompt}\n\nUser: {user_prompt}"
        
        # 토큰 사용량 추출 (feed_gen과 동일한 방식)
        token_usage = None
        try:
            # response.usage 확인
            if hasattr(response, 'usage'):
                usage_obj = response.usage
                if usage_obj is not None:
                    # usage 객체의 속성 확인
                    if hasattr(usage_obj, 'prompt_tokens') and hasattr(usage_obj, 'completion_tokens') and hasattr(usage_obj, 'total_tokens'):
                        token_usage = {
                            "prompt_tokens": usage_obj.prompt_tokens,
                            "completion_tokens": usage_obj.completion_tokens,
                            "total_tokens": usage_obj.total_tokens
                        }
                        logger.info(f"✓ 토큰 사용량 추출 성공: prompt={token_usage['prompt_tokens']}, completion={token_usage['completion_tokens']}, total={token_usage['total_tokens']}")
                    else:
                        logger.warning(f"⚠️ usage 객체에 필요한 속성이 없습니다. usage_obj={usage_obj}, dir={dir(usage_obj)}")
                else:
                    logger.warning(f"⚠️ response.usage가 None입니다.")
            else:
                logger.warning(f"⚠️ response에 usage 속성이 없습니다. response 타입={type(response)}, dir={[x for x in dir(response) if not x.startswith('_')]}")
        except Exception as e:
            logger.error(f"❌ 토큰 사용량 추출 중 오류: {e}", exc_info=True)
            import traceback
            logger.error(f"트레이스백: {traceback.format_exc()}")
        
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
        
        logger.info(f"✓ 영어 → 한글 변환 완료 (latency: {latency_ms:.2f}ms)")
        logger.debug(f"변환된 글 길이: {len(ad_copy_kor)}자")
        
        return {
            "ad_copy_kor": ad_copy_kor,
            "prompt_used": prompt_used,
            "latency_ms": latency_ms,
            "token_usage": token_usage,
            "gpt_response_raw": gpt_response_raw
        }
        
    except Exception as e:
        logger.error(f"❌ GPT API 호출 중 오류: {e}")
        raise

