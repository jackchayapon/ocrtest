FROM python:3.12-slim
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HF_HOME=/tmp/huggingface HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /service
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 service
COPY requirements.txt ./
RUN pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 --index-url ${TORCH_INDEX} \
    && pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY model-manifest.json ./
USER 10001
EXPOSE 8092
HEALTHCHECK --interval=30s --timeout=5s --start-period=10m CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8092/health',timeout=3)"
CMD ["python", "-m", "app.main"]
