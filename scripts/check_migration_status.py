#!/usr/bin/env python3
"""마이그레이션 상태 확인 스크립트"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal
from sqlalchemy import text, inspect
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_table_columns(table_name: str, expected_columns: list, removed_columns: list = None):
    """테이블 컬럼 확인"""
    db = SessionLocal()
    try:
        inspector = inspect(db.bind)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        
        print(f"\n{'=' * 60}")
        print(f"📋 {table_name} 테이블 컬럼 확인")
        print(f"{'=' * 60}")
        
        # 예상 컬럼 확인
        missing_columns = []
        for col in expected_columns:
            if col not in columns:
                missing_columns.append(col)
                print(f"❌ 누락된 컬럼: {col}")
            else:
                print(f"✅ 존재하는 컬럼: {col}")
        
        # 제거된 컬럼 확인
        if removed_columns:
            for col in removed_columns:
                if col in columns:
                    print(f"⚠️  제거되지 않은 컬럼: {col}")
                else:
                    print(f"✅ 제거된 컬럼: {col}")
        
        if not missing_columns and (not removed_columns or all(col not in columns for col in removed_columns)):
            print(f"\n✅ {table_name} 테이블 마이그레이션 완료")
            return True
        else:
            print(f"\n❌ {table_name} 테이블 마이그레이션 미완료")
            return False
            
    except Exception as e:
        logger.error(f"테이블 확인 중 오류: {e}", exc_info=True)
        return False
    finally:
        db.close()

def main():
    """메인 함수"""
    print("=" * 60)
    print("마이그레이션 상태 확인")
    print("=" * 60)
    
    # 1. llm_traces 테이블 확인
    llm_traces_expected = [
        'llm_trace_id', 'job_id', 'provider', 'operation_type',
        'request', 'response', 'latency_ms',
        'prompt_tokens', 'completion_tokens', 'total_tokens', 'token_usage',
        'created_at', 'updated_at'
    ]
    llm_traces_ok = check_table_columns('llm_traces', llm_traces_expected)
    
    # 2. instagram_feeds 테이블 확인
    instagram_feeds_expected = [
        'instagram_feed_id', 'job_id', 'llm_trace_id', 'overlay_id',
        'tenant_id', 'refined_ad_copy_eng', 'ad_copy_kor',
        'tone_style', 'product_description', 'gpt_prompt',
        'instagram_ad_copy', 'hashtags',
        'used_temperature', 'used_max_tokens', 'latency_ms',
        'created_at', 'updated_at'
    ]
    instagram_feeds_removed = [
        'llm_model_id', 'store_information',
        'gpt_prompt_used', 'gpt_response_raw',
        'prompt_tokens', 'completion_tokens', 'total_tokens', 'token_usage'
    ]
    instagram_feeds_ok = check_table_columns('instagram_feeds', instagram_feeds_expected, instagram_feeds_removed)
    
    # 3. 최종 결과
    print("\n" + "=" * 60)
    print("최종 결과")
    print("=" * 60)
    if llm_traces_ok and instagram_feeds_ok:
        print("✅ 모든 마이그레이션이 완료되었습니다!")
        return 0
    else:
        print("❌ 일부 마이그레이션이 완료되지 않았습니다.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

