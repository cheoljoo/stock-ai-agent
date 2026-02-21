# =============================================================================
# Stock AI Agent - Docker Container Image
# ECS Fargate 배포를 위한 컨테이너 이미지 정의
# =============================================================================
FROM python:3.11-slim-bookworm

# 빌드 도구 설치 (일부 Python 패키지 컴파일에 필요)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 의존성 먼저 설치 (Docker 레이어 캐싱 활용)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY app.py stock_agent.py ./

# Streamlit 포트 노출
EXPOSE 8501

# 헬스체크 설정 (ECS 및 ALB 헬스체크용)
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

# Streamlit 실행
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--browser.gatherUsageStats=false"]
