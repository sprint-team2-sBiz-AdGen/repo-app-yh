
"""GPT 광고 문구 생성 라우터"""
########################################################
# TODO: Implement the actual GPT ad copy generation logic
#       - Connect to GPT API (OpenAI, Anthropic, etc.)
#       - Generate English ad copy from prompts
#       - Translate to Korean
#       - Return Kor Ad Copy
########################################################
# created_at: 2025-11-20
# updated_at: 2025-11-20
# author: LEEYH205
# description: GPT ad copy generation logic
# version: 0.1.0
# status: development
# tags: gpt, ad-copy
# dependencies: fastapi, pydantic, PIL, requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

from fastapi import APIRouter
from models import GPTAdCopyIn

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

