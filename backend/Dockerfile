FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements-runtime-lock.txt ./
RUN pip install --no-cache-dir -r requirements-runtime-lock.txt && pip check
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN useradd --create-home --uid 10001 benchmark && mkdir -p /app/storage/uploads && chown -R benchmark:benchmark /app
USER benchmark
EXPOSE 8000
# Application lifespan upgrades Alembic and seeds only missing records.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
