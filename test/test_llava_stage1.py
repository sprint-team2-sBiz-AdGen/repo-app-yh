"""LLaVa Stage 1 검증 테스트 스크립트"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from PIL import Image
from services.llava_service import validate_image_and_text

# ASSETS_DIR 설정 (config와 동일하게)
ASSETS_DIR = os.getenv("ASSETS_DIR", "/var/www/assets")

def test_stage1_validation():
    """LLaVa Stage 1 검증 테스트"""
    
    # 테스트 데이터
    # 실제 경로: /opt/feedlyai/assets/yh/image_to_use/...
    # API에서는 /assets/yh/image_to_use/... 형식으로 사용
    image_path = "/opt/feedlyai/assets/yh/image_to_use/20251119-111402-976662c1_pbg_customer_review_ugc_engagement.png"
    ad_copy_text_good = "Spicy Pork Kimchi Stew – one spoon and you'll forget everything else."
    ad_copy_text_bad = "For a quiet, odor-free office lunch, bring this sizzling Pork Kimchi Stew."
    
    ad_copy_text = ad_copy_text_bad
    
    print("=" * 60)
    print("LLaVa Stage 1 Validation 테스트")
    print("=" * 60)
    print(f"이미지 경로: {image_path}")
    print(f"광고 문구: {ad_copy_text}")
    print("=" * 60)
    
    try:
        # 이미지 로드
        print("\n[1/3] 이미지 로드 중...")
        image = Image.open(image_path)
        print(f"✓ 이미지 로드 완료: {image.size[0]}x{image.size[1]}")
        
        # LLaVa 검증 실행
        # validation_prompt를 None으로 전달하면 함수 내부에서 ad_copy_text를 포함한 프롬프트가 자동 생성됨
        print("\n[2/3] LLaVa 모델 로드 및 검증 중... (시간이 걸릴 수 있습니다)")
        result = validate_image_and_text(
            image=image,
            ad_copy_text=ad_copy_text,
            validation_prompt=None  # None으로 전달하면 ad_copy_text가 프롬프트에 자동 포함됨
        )
        
        # 결과 출력
        print("\n[3/3] 검증 완료!")
        print("\n" + "=" * 60)
        print("검증 결과")
        print("=" * 60)
        print(f"✓ 적합성: {result['is_valid']}")
        print(f"✓ 이미지 품질: {result['image_quality_ok']}")
        print(f"✓ 관련성 점수: {result['relevance_score']}")
        print(f"✓ 이슈: {result['issues']}")
        print(f"✓ 추천사항: {result['recommendations']}")
        print("\n" + "-" * 60)
        print("LLaVa 분석 결과:")
        print("-" * 60)
        print(result['analysis'])
        print("=" * 60)
        
        return result
        
    except FileNotFoundError:
        print(f"\n❌ 오류: 이미지를 찾을 수 없습니다: {image_path}")
        print("이미지 경로를 확인해주세요.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_stage1_validation()

