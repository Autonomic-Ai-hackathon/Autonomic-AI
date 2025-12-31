FROM python:3.11-slim

# 1. Install curl
RUN apt-get update && \
    apt-get install -y curl && \
    rm -rf /var/lib/apt/lists/*

# 2. COPY serverless-init from Datadog's official image (multi-arch compatible)
COPY --from=datadog/serverless-init:1 /datadog-init /app/datadog-init

# 3. Install your dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt ddtrace

# 4. Copy application code
COPY . .

# 5. Use serverless-init as entrypoint
ENTRYPOINT ["/app/datadog-init"]

# 6. Your application command
CMD ["ddtrace-run", "python", "main.py"]
