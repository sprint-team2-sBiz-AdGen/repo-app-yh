"""YOLOv8 모델 다운로드 스크립트"""
import os
import sys

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from ultralytics import YOLO
from config import MODEL_DIR

def download_yolo_model():
    """YOLOv8x-seg 모델 다운로드"""
    model_name = "yolov8x-seg.pt"
    model_path = os.path.join(MODEL_DIR, model_name)
    
    print("=" * 60)
    print("YOLOv8x-seg 모델 다운로드 시작")
    print("=" * 60)
    print(f"모델명: {model_name}")
    print(f"저장 위치: {model_path}")
    print("=" * 60)
    
    # 모델 디렉토리 생성
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    try:
        # 모델 다운로드 및 로드
        # Ultralytics는 모델명만 지정하면 자동으로 다운로드합니다
        print("\n[1/2] YOLOv8x-seg 모델 다운로드 중... (시간이 걸릴 수 있습니다)")
        print("      모델 크기: 약 136MB")
        
        # 모델 로드 (자동 다운로드)
        model = YOLO(model_name)
        print("✓ 모델 다운로드 완료")
        
        # 모델을 지정된 경로에 저장
        print(f"\n[2/2] 모델을 {model_path}에 저장 중...")
        model.save(model_path)
        print(f"✓ 모델 저장 완료: {model_path}")
        
        # 파일 크기 확인
        if os.path.exists(model_path):
            file_size = os.path.getsize(model_path) / (1024**2)  # MB
            print(f"\n저장된 모델 크기: {file_size:.2f} MB")
        
        print("\n" + "=" * 60)
        print("모든 다운로드가 완료되었습니다!")
        print(f"모델 위치: {model_path}")
        print("=" * 60)
        
        # 모델 정보 출력
        print("\n모델 정보:")
        print(f"  - 모델 타입: YOLOv8x-seg (Segmentation)")
        print(f"  - 입력 크기: 640x640 (기본값)")
        print(f"  - 클래스 수: 80 (COCO 데이터셋)")
        
    except ImportError:
        print("\n❌ 오류: ultralytics 패키지가 설치되지 않았습니다.")
        print("\n설치 방법:")
        print("  pip install ultralytics")
        print("  또는")
        print("  uv pip install ultralytics")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        print("\n문제 해결 방법:")
        print("1. 인터넷 연결 확인")
        print("2. 디스크 공간 확인 (최소 200MB 필요)")
        print("3. ultralytics 패키지 설치 확인")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    download_yolo_model()

