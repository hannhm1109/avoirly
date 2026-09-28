FROM python:3.14-slim AS build
RUN pip install --no-cache-dir uv==0.12.19
WORKDIR /app
COPY backend/ /app/backend/
RUN uv sync --project backend --locked --no-dev

FROM python:3.14-slim
RUN useradd --create-home --uid 10001 avoirly
WORKDIR /app
COPY --from=build /app/backend /app/backend
ENV PATH="/app/backend/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    AVOIRLY_MODE=hosted AVOIRLY_STORAGE_ROOT=/tmp/avoirly
USER avoirly
EXPOSE 8000
CMD ["python", "-m", "recovery.api.app"]
