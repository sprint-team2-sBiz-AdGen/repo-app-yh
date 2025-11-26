FROM python:3.11-slim

WORKDIR /app

# 환경 변수 설정
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 시스템 패키지 설치 (Pillow 및 OpenCV 의존성, 폰트 관련)
RUN apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    fonts-dejavu \
    fonts-nanum \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 폰트 설치 스크립트 복사
COPY scripts/install_fonts.sh /usr/local/bin/install_fonts.sh
RUN chmod +x /usr/local/bin/install_fonts.sh

# 코드 복사
COPY . .

# 포트 노출
EXPOSE 8011

# 실행 명령
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8011", "--reload"]



