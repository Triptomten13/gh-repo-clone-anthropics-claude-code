FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# LOCAL_AI=1 installs llama.cpp (llama-cpp-python, prebuilt CPU wheel) so DAEMON CORE can run local models.
ARG LOCAL_AI=1
COPY requirements.txt requirements-local-ai.txt ./
RUN pip install --no-cache-dir -r requirements.txt "psycopg[binary]>=3.2" \
 && if [ "$LOCAL_AI" = "1" ]; then pip install --no-cache-dir -r requirements-local-ai.txt; fi
COPY . .
ENV MODELS_DIR=/app/data/models ARCHIVE_DIR=/app/data/archive
RUN useradd -r rocky && mkdir -p /app/data/models /app/data/archive && chown -R rocky /app
USER rocky
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
