"""두 가지 광고 문구 비교 테스트"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from PIL import Image
from services.llava_service import validate_image_and_text

def compare_ad_copies():
    """두 가지 광고 문구를 비교 테스트"""
    
    image_path = "/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    
    ad_copy_good = "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
    ad_copy_bad = "The ultimate choice for people who hate spicy food: our extra-.pasta"
    #ad_copy_bad = "Cool down this summer with our refreshing Pork Kimchi Stew ice cream!"
    
    print("=" * 80)
    print("광고 문구 비교 테스트")
    print("=" * 80)
    print(f"이미지: {image_path}")
    print("\n테스트할 광고 문구:")
    print(f"1. 좋은 예: {ad_copy_good}")
    print(f"2. 나쁜 예: {ad_copy_bad}")
    print("=" * 80)
    
    # 이미지 로드
    image = Image.open(image_path)
    print(f"\n이미지 로드 완료: {image.size[0]}x{image.size[1]}")
    
    # 좋은 광고 문구 테스트
    print("\n" + "=" * 80)
    print("테스트 1: 좋은 광고 문구")
    print("=" * 80)
    result_good = validate_image_and_text(
        image=image,
        ad_copy_text=ad_copy_good,
        validation_prompt=None
    )
    print("\n분석 결과:")
    print(f"- 적합성: {result_good['is_valid']}")
    print(f"- 관련성 점수: {result_good['relevance_score']}")
    print(f"\nLLaVa 분석:")
    print(result_good['analysis'])
    
    # 나쁜 광고 문구 테스트
    print("\n" + "=" * 80)
    print("테스트 2: 나쁜 광고 문구 (이미지와 맞지 않음)")
    print("=" * 80)
    result_bad = validate_image_and_text(
        image=image,
        ad_copy_text=ad_copy_bad,
        validation_prompt=None
    )
    print("\n분석 결과:")
    print(f"- 적합성: {result_bad['is_valid']}")
    print(f"- 관련성 점수: {result_bad['relevance_score']}")
    print(f"\nLLaVa 분석:")
    print(result_bad['analysis'])
    
    # 비교 요약
    print("\n" + "=" * 80)
    print("비교 요약")
    print("=" * 80)
    print(f"좋은 광고 문구 - 적합성: {result_good['is_valid']}, 점수: {result_good['relevance_score']}")
    print(f"나쁜 광고 문구 - 적합성: {result_bad['is_valid']}, 점수: {result_bad['relevance_score']}")
    
    if result_good['relevance_score'] > result_bad['relevance_score']:
        print("\n✓ LLaVa가 두 광고 문구를 올바르게 구분했습니다!")
    else:
        print("\n✗ LLaVa가 두 광고 문구를 제대로 구분하지 못했습니다.")
        print("  프롬프트 개선이 필요합니다.")

if __name__ == "__main__":
    compare_ad_copies()

