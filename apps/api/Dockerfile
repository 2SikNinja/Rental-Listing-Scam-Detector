# =====================================================================
# Dockerfile for the Rental Scam Detector API
#
# Build:  docker build -t rental-scam-api .
# Run:    docker run --rm -p 8080:8080 --env-file .env rental-scam-api
# Then open http://localhost:8080/docs
#
# Two stages: the "builder" stage installs dependencies, and the final
# stage copies only what is needed to run. The final image has no build
# tools and no uv, which makes it smaller and gives attackers less to use.
# =====================================================================

# ---------- Stage 1: install dependencies ----------
FROM python:3.13-slim AS builder

# Copy the uv binary from its official image (pinned version for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

WORKDIR /app

# Compile .py files to bytecode for faster startup, and copy packages
# instead of symlinking so the .venv can move to the next stage.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy only the dependency files first. Docker caches each step, so as
# long as these two files don't change, the slow install step is reused
# on every rebuild, even when the app code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ---------- Stage 2: runtime ----------
FROM python:3.13-slim AS runtime

# Run as a regular user, not root. If someone ever exploited the app,
# they would not have admin rights inside the container.
RUN useradd --create-home --uid 1000 appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

USER appuser

EXPOSE 8080

# Cloud Run tells the container which port to use through $PORT.
# "exec" makes uvicorn the main process so it shuts down cleanly when
# Cloud Run stops the container.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
