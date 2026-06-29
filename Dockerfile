FROM python:3.12-slim

WORKDIR /app

# Install system deps for psutil
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install ultrawhale
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

# Create output directories
RUN mkdir -p /app/ralph_logs /app/dogfeed_parallel

ENV MISTRALRS_HOST=http://llama-server:8080
ENV ULTRAWHALE_LOG_DIR=/app/ralph_logs
ENV ULTRAWHALE_OUTPUT_DIR=/app/dogfeed_parallel

ENTRYPOINT ["ultrawhale"]
CMD ["status"]
