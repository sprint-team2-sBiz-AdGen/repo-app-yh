"""LLaVA 폰트 추천 다양성 테스트"""
########################################################
# Font Recommendation Diversity Test
# - LLaVA가 다양한 폰트를 추천하는지 테스트
# - temperature와 do_sample 파라미터 조정으로 다양성 확보
########################################################
# created_at: 2025-11-25
# updated_at: 2025-11-25
# author: LEEYH205
# description: Test LLaVA font recommendation diversity
# version: 1.0.0
# status: production
# tags: test, llava, font, diversity
# dependencies: subprocess, sqlalchemy
# license: MIT
# copyright: 2025 FeedlyAI
########################################################

import sys
import os
import subprocess
import time
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from database import SessionLocal, VLMTrace
import json


def test_font_diversity(
    image_path: str,
    text_path: str,
    num_tests: int = 10,
    api_url: str = "http://localhost:8011"
):
    """
    LLaVA 폰트 추천 다양성 테스트
    
    Args:
        image_path: 테스트할 이미지 경로
        text_path: 테스트할 텍스트 경로
        num_tests: 테스트 실행 횟수
        api_url: API URL
    """
    print('='*60)
    print(f'LLaVA 폰트 추천 다양성 테스트 ({num_tests}회 실행)')
    print('='*60)
    print(f'이미지: {image_path}')
    print(f'텍스트: {text_path}')
    print('개선 사항:')
    print('  - temperature: 0.1 → 0.7')
    print('  - do_sample: False → True')
    print('  - 프롬프트에 다양성 지시 추가')
    print()
    
    font_recommendations = []
    
    for i in range(1, num_tests + 1):
        print(f'[{i}/{num_tests}]', end=' ', flush=True)
        
        try:
            # test_pipeline_full.py 실행
            result = subprocess.run(
                ['python3', os.path.join(project_root, 'test', 'test_pipeline_full.py'),
                 '--image-path', image_path,
                 '--text-path', text_path],
                capture_output=True,
                text=True,
                timeout=300  # 5분 타임아웃
            )
            
            if result.returncode != 0:
                print('✗', end=' ')
                if result.stderr:
                    print(f'오류: {result.stderr[:100]}')
                continue
            
            # 최신 vlm_trace 조회
            db = SessionLocal()
            vlm_trace = db.query(VLMTrace).order_by(VLMTrace.created_at.desc()).first()
            
            if vlm_trace and vlm_trace.response:
                font_rec = vlm_trace.response.get('font_recommendation', {})
                font_name = font_rec.get('font_name', 'N/A')
                font_style = font_rec.get('font_style', 'N/A')
                font_size = font_rec.get('font_size_category', 'N/A')
                font_color = font_rec.get('font_color_hex', 'N/A')
                
                font_recommendations.append({
                    'test_num': i,
                    'font_name': font_name,
                    'font_style': font_style,
                    'font_size': font_size,
                    'font_color': font_color,
                    'timestamp': vlm_trace.created_at.isoformat() if hasattr(vlm_trace.created_at, 'isoformat') else str(vlm_trace.created_at)
                })
                
                print(f'{font_name}', flush=True)
            else:
                print('N/A', end=' ')
            
            db.close()
            
            # 다음 테스트 전 잠시 대기
            time.sleep(2)
            
        except subprocess.TimeoutExpired:
            print('✗ 타임아웃', end=' ')
            continue
        except Exception as e:
            print(f'✗ 오류: {str(e)[:50]}', end=' ')
            continue
    
    print('\n' + '='*60)
    print('테스트 결과 요약')
    print('='*60)
    
    if font_recommendations:
        # 폰트 이름별 통계
        font_name_counts = {}
        for rec in font_recommendations:
            font_name = rec['font_name']
            font_name_counts[font_name] = font_name_counts.get(font_name, 0) + 1
        
        print(f'\n[폰트 이름 추천 통계] (총 {len(font_recommendations)}회)')
        for font_name, count in sorted(font_name_counts.items(), key=lambda x: -x[1]):
            percentage = (count / len(font_recommendations)) * 100
            bar = '█' * int(percentage / 5)
            print(f'  {font_name:30s}: {count:2d}회 ({percentage:5.1f}%) {bar}')
        
        # 폰트 스타일별 통계
        font_style_counts = {}
        for rec in font_recommendations:
            font_style = rec['font_style']
            font_style_counts[font_style] = font_style_counts.get(font_style, 0) + 1
        
        print(f'\n[폰트 스타일 추천 통계]')
        for font_style, count in sorted(font_style_counts.items(), key=lambda x: -x[1]):
            percentage = (count / len(font_recommendations)) * 100
            print(f'  {font_style:20s}: {count:2d}회 ({percentage:5.1f}%)')
        
        # 다양성 평가
        unique_fonts = len(font_name_counts)
        total_tests = len(font_recommendations)
        diversity_ratio = unique_fonts / total_tests if total_tests > 0 else 0
        
        print(f'\n[다양성 평가]')
        print(f'  고유 폰트 개수: {unique_fonts}개')
        print(f'  총 테스트 횟수: {total_tests}회')
        print(f'  다양성 비율: {diversity_ratio:.2%}')
        
        if diversity_ratio >= 0.5:
            print(f'  ✓ 다양성이 높습니다 (50% 이상)')
        elif diversity_ratio >= 0.3:
            print(f'  ⚠ 다양성이 보통입니다 (30-50%)')
        else:
            print(f'  ✗ 다양성이 낮습니다 (30% 미만)')
        
        # 상세 결과
        print(f'\n[상세 결과]')
        for rec in font_recommendations:
            print(f"  테스트 {rec['test_num']:2d}: {rec['font_name']:25s} ({rec['font_style']}, {rec['font_size']}, {rec['font_color']})")
        
        # JSON 결과 저장
        result_file = os.path.join(project_root, 'test', 'output', 'font_diversity_test_result.json')
        os.makedirs(os.path.dirname(result_file), exist_ok=True)
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                'test_date': datetime.now().isoformat(),
                'image_path': image_path,
                'text_path': text_path,
                'num_tests': num_tests,
                'results': font_recommendations,
                'statistics': {
                    'font_name_counts': font_name_counts,
                    'font_style_counts': font_style_counts,
                    'unique_fonts': unique_fonts,
                    'diversity_ratio': diversity_ratio
                }
            }, f, indent=2, ensure_ascii=False)
        print(f'\n[결과 저장] JSON 파일: {result_file}')
    else:
        print('  ⚠ 수집된 폰트 추천이 없습니다')
    
    print('='*60)
    return font_recommendations


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='LLaVA 폰트 추천 다양성 테스트')
    parser.add_argument('--image-path', type=str, required=True, help='테스트할 이미지 경로')
    parser.add_argument('--text-path', type=str, required=True, help='테스트할 텍스트 경로')
    parser.add_argument('--num-tests', type=int, default=10, help='테스트 실행 횟수 (기본값: 10)')
    parser.add_argument('--api-url', type=str, default='http://localhost:8011', help='API URL (기본값: http://localhost:8011)')
    
    args = parser.parse_args()
    
    test_font_diversity(
        image_path=args.image_path,
        text_path=args.text_path,
        num_tests=args.num_tests,
        api_url=args.api_url
    )



