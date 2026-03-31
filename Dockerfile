# 펜세오 자동매매 대시보드 — GCP(Compute Engine / Cloud Run) 상시 실행용
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app.py paper_trading.py daily_equity.py ./

# Cloud Run은 PORT를 주입함. VM에서는 기본 8501.
ENV PORT=8501
EXPOSE 8501

HEALTHCHECK --interval=45s --timeout=8s --start-period=60s --retries=3 \
    CMD python -c "import os,urllib.request; p=os.environ.get('PORT','8501'); urllib.request.urlopen(f'http://127.0.0.1:{p}/_stcore/health', timeout=5)"

CMD sh -c "streamlit run app.py \
  --server.port=${PORT} \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false"
