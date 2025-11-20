"""LLaVa 모델 다운로드 스크립트"""
import os
import sys
from transformers import LlavaProcessor, LlavaForConditionalGeneration
import torch
from config import LLAVA_MODEL_NAME, MODEL_DIR, DEVICE_TYPE

def download_model():
    """LLaVa 모델 다운로드"""
    print("=" * 60)
    print("LLaVa 모델 다운로드 시작")
    print("=" * 60)
    print(f"모델명: {LLAVA_MODEL_NAME}")
    print(f"저장 위치: {MODEL_DIR}")
    print(f"디바이스: {DEVICE_TYPE}")
    print("=" * 60)
    
    # 모델 디렉토리 생성
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    try:
        # 프로세서 다운로드
        print("\n[1/2] 프로세서 다운로드 중...")
        processor = LlavaProcessor.from_pretrained(
            LLAVA_MODEL_NAME,
            cache_dir=MODEL_DIR
        )
        print("✓ 프로세서 다운로드 완료")
        
        # 모델 다운로드
        print("\n[2/2] 모델 다운로드 중... (시간이 걸릴 수 있습니다)")
        model = LlavaForConditionalGeneration.from_pretrained(
            LLAVA_MODEL_NAME,
            torch_dtype=torch.float16 if DEVICE_TYPE == "cuda" and torch.cuda.is_available() else torch.float32,
            cache_dir=MODEL_DIR,
            low_cpu_mem_usage=True
        )
        print("✓ 모델 다운로드 완료")
        
        print("\n" + "=" * 60)
        print("모든 다운로드가 완료되었습니다!")
        print(f"모델 위치: {MODEL_DIR}")
        print("=" * 60)
        
        # 모델 크기 확인
        model_size = sum(p.numel() * p.element_size() for p in model.parameters())
        print(f"\n모델 크기: {model_size / (1024**3):.2f} GB")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        print("\n문제 해결 방법:")
        print("1. 인터넷 연결 확인")
        print("2. 디스크 공간 확인")
        print("3. Hugging Face 토큰이 필요한 경우 설정")
        sys.exit(1)

if __name__ == "__main__":
    download_model()

