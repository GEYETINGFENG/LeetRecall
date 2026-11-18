# LeetRecall AI backend for Cloud Run. Built remotely by Cloud Build:
#   gcloud run deploy leetrecall-ai --source server ...   (see README "Deploy")
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    FASTEMBED_CACHE_PATH=/app/models \
    PYTHONUNBUFFERED=1

# deps first (cached layer), then the project
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY data/leetrecall-seed-backup.json ./data/leetrecall-seed-backup.json
RUN uv sync --frozen --no-dev

# Bake the embedding model into the image: no download on cold start, no runtime dependency on HuggingFace.
RUN .venv/bin/python -c "from leetrecall_ai.rag.embed import dim; print('embedding dim', dim())"

ENV PORT=8080 \
    LEETRECALL_OTEL_EXPORTER=gcp
EXPOSE 8080
CMD ["sh", "-c", "exec .venv/bin/uvicorn leetrecall_ai.main:app --host 0.0.0.0 --port ${PORT}"]
