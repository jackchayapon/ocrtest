FROM python:3.12-slim
WORKDIR /service
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENTHAI_MODEL_DIR=/models/openthai2
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home ocr
COPY app ./app
COPY model-manifest.json ./
USER 10001
EXPOSE 8091
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('OPENTHAI_PORT', '8091')+'/health', timeout=2)"
CMD ["python", "-m", "app"]
