# Single image used for both Cloud Run targets:
#   - Service (dashboard):  default CMD runs Streamlit on $PORT
#   - Job (digest):         override CMD to run `python -m bot.telegram ...`
#
# Build:  docker build -t bottibot .
# Run dashboard locally:
#   docker run --rm -p 8080:8080 -e PORT=8080 bottibot
# Run digest locally:
#   docker run --rm --env-file .env bottibot \
#     uv run python -m bot.telegram --universe US_LARGE --top 5

FROM python:3.12-slim

# uv for dependency management (matches local dev workflow)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# Cache deps separately from source for fast rebuilds
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra gcs

# Application code
COPY . .

# Streamlit defaults; Cloud Run injects PORT
ENV PORT=8080 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8080

# Default = dashboard service. Cloud Run Jobs override this CMD.
CMD ["sh", "-c", "uv run streamlit run dashboard/app.py --server.port=${PORT} --server.address=0.0.0.0"]
