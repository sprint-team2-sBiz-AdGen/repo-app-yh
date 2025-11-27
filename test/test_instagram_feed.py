
"""인스타그램 피드 글 생성 테스트"""
########################################################
# GPT를 활용한 인스타그램 피드 글 생성 API 테스트
########################################################
# created_at: 2025-11-27
# updated_at: 2025-11-27
# author: LEEYH205
# description: Instagram feed post generation test
# version: 0.1.0
# status: development
# tags: test, instagram, gpt
# dependencies: requests
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import sys
import os
import json
import requests
from typing import Dict, Any

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from database import SessionLocal, InstagramFeed, LLMModel

# API 기본 URL
API_BASE_URL = "http://localhost:8011"


def test_instagram_feed(
    tenant_id: str = "test_instagram_tenant",
    refined_ad_copy_eng: str = "Delicious Korean Army Stew - A perfect blend of spicy, savory, and comforting flavors that will warm your heart.",
    tone_style: str = "친근하고 따뜻한, 맛있는 음식을 즐기는 사람들을 위한",
    product_description: str = "부대찌개 - 다양한 재료가 어우러진 한국의 대표적인 퓨전 요리",
    store_information: str = "서울 강남구 테헤란로, 맛있는 부대찌개 전문점",
    gpt_prompt: str = "인스타그램에 어울리는 매력적이고 친근한 피드 글을 작성해주세요. 한국어로 작성하고, 자연스럽고 매력적인 톤으로 작성해주세요.",
    api_url: str = API_BASE_URL
) -> Dict[str, Any]:
    """
    인스타그램 피드 글 생성 API 테스트
    
    Args:
        tenant_id: 테넌트 ID
        refined_ad_copy_eng: 조정된 광고문구 (영어)
        tone_style: 톤 & 스타일
        product_description: 제품 설명
        store_information: 스토어 정보
        gpt_prompt: GPT 프롬프트
        api_url: API 서버 URL
    
    Returns:
        Dict[str, Any]: API 응답
    """
    url = f"{api_url}/api/yh/instagram/feed"
    
    payload = {
        "tenant_id": tenant_id,
        "refined_ad_copy_eng": refined_ad_copy_eng,
        "tone_style": tone_style,
        "product_description": product_description,
        "store_information": store_information,
        "gpt_prompt": gpt_prompt
    }
    
    print("\n" + "=" * 60)
    print("인스타그램 피드 글 생성 테스트")
    print("=" * 60)
    print(f"\nAPI URL: {url}")
    print(f"\n요청 데이터:")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    
    try:
        response = requests.post(url, json=payload, timeout=120)  # GPT API 호출 시간을 고려하여 120초로 증가
        response.raise_for_status()
        
        result = response.json()
        
        print("\n" + "=" * 60)
        print("✓ API 호출 성공!")
        print("=" * 60)
        print(f"\n응답 데이터:")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        print("\n" + "-" * 60)
        print("생성된 인스타그램 피드 글:")
        print("-" * 60)
        print(result.get("instagram_ad_copy", ""))
        
        print("\n" + "-" * 60)
        print("해시태그:")
        print("-" * 60)
        print(result.get("hashtags", ""))
        
        print("\n" + "-" * 60)
        print("메타데이터:")
        print("-" * 60)
        print(f"Instagram Feed ID: {result.get('instagram_feed_id', 'N/A')}")
        print(f"생성 시간: {result.get('generated_at', 'N/A')}")
        
        # DB 확인
        instagram_feed_id = result.get('instagram_feed_id')
        if instagram_feed_id:
            verify_db_record(instagram_feed_id)
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ API 호출 실패: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"응답 상태 코드: {e.response.status_code}")
            try:
                print(f"응답 내용: {e.response.text}")
            except:
                pass
        raise
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        raise


def verify_db_record(instagram_feed_id: str):
    """DB에 저장된 레코드 확인"""
    print("\n" + "=" * 60)
    print("DB 레코드 확인")
    print("=" * 60)
    
    try:
        db = SessionLocal()
        import uuid
        feed_id_uuid = uuid.UUID(instagram_feed_id)
        feed = db.query(InstagramFeed).filter(InstagramFeed.instagram_feed_id == feed_id_uuid).first()
        
        if feed:
            print(f"\n✓ DB 레코드 발견:")
            print(f"  - Instagram Feed ID: {feed.instagram_feed_id}")
            print(f"  - Tenant ID: {feed.tenant_id}")
            print(f"  - Job ID: {feed.job_id if feed.job_id else 'N/A'}")
            print(f"  - Overlay ID: {feed.overlay_id if feed.overlay_id else 'N/A'}")
            
            # LLM 모델 정보 조회
            if feed.llm_model_id:
                llm_model = db.query(LLMModel).filter(LLMModel.llm_model_id == feed.llm_model_id).first()
                if llm_model:
                    print(f"  - LLM Model: {llm_model.model_name} ({llm_model.provider})")
                else:
                    print(f"  - LLM Model ID: {feed.llm_model_id} (모델 정보 없음)")
            else:
                print(f"  - LLM Model ID: N/A")
            
            print(f"  - Used Temperature: {feed.used_temperature}" if feed.used_temperature is not None else "  - Used Temperature: N/A")
            print(f"  - Used Max Tokens: {feed.used_max_tokens}" if feed.used_max_tokens is not None else "  - Used Max Tokens: N/A")
            print(f"  - Latency: {feed.latency_ms:.2f}ms" if feed.latency_ms else "  - Latency: N/A")
            print(f"  - Prompt Tokens: {feed.prompt_tokens}" if feed.prompt_tokens is not None else "  - Prompt Tokens: N/A")
            print(f"  - Completion Tokens: {feed.completion_tokens}" if feed.completion_tokens is not None else "  - Completion Tokens: N/A")
            print(f"  - Total Tokens: {feed.total_tokens}" if feed.total_tokens is not None else "  - Total Tokens: N/A")
            print(f"  - Token Usage (JSON): {feed.token_usage}" if feed.token_usage else "  - Token Usage (JSON): N/A")
            print(f"  - Created At: {feed.created_at}")
            print(f"\n  생성된 글 (일부):")
            print(f"  {feed.instagram_ad_copy[:100]}...")
            print(f"\n  해시태그: {feed.hashtags}")
        else:
            print(f"\n❌ DB 레코드를 찾을 수 없습니다: {instagram_feed_id}")
        
        db.close()
        
    except Exception as e:
        print(f"\n❌ DB 확인 중 오류: {e}")
        import traceback
        traceback.print_exc()


def main():
    """메인 테스트 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="인스타그램 피드 글 생성 API 테스트")
    parser.add_argument("--tenant-id", default="test_instagram_tenant",
                       help="테스트용 tenant_id")
    parser.add_argument("--refined-ad-copy-eng", type=str,
                       default="Delicious Korean Army Stew - A perfect blend of spicy, savory, and comforting flavors that will warm your heart.",
                       help="조정된 광고문구 (영어)")
    parser.add_argument("--tone-style", type=str,
                       default="친근하고 따뜻한, 맛있는 음식을 즐기는 사람들을 위한",
                       help="톤 & 스타일")
    parser.add_argument("--product-description", type=str,
                       default="부대찌개 - 다양한 재료가 어우러진 한국의 대표적인 퓨전 요리",
                       help="제품 설명")
    parser.add_argument("--store-information", type=str,
                       default="서울 강남구 테헤란로, 맛있는 부대찌개 전문점",
                       help="스토어 정보")
    parser.add_argument("--gpt-prompt", type=str,
                       default="인스타그램에 어울리는 매력적이고 친근한 피드 글을 작성해주세요. 한국어로 작성하고, 자연스럽고 매력적인 톤으로 작성해주세요.",
                       help="GPT 프롬프트")
    parser.add_argument("--api-url", default=API_BASE_URL,
                       help="API 서버 URL")
    
    args = parser.parse_args()
    
    try:
        result = test_instagram_feed(
            tenant_id=args.tenant_id,
            refined_ad_copy_eng=args.refined_ad_copy_eng,
            tone_style=args.tone_style,
            product_description=args.product_description,
            store_information=args.store_information,
            gpt_prompt=args.gpt_prompt,
            api_url=args.api_url
        )
        
        print("\n" + "=" * 60)
        print("✓ 테스트 완료!")
        print("=" * 60)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

