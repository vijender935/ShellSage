FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENT_WORKSPACE=/app/workspace \
    COMMAND_CPU_SECONDS=60 \
    COMMAND_MAX_FILE_BYTES=16777216 \
    COMMAND_MAX_OPEN_FILES=256

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin agent \
    && mkdir -p /app/workspace \
    && chown -R agent:agent /app

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R agent:agent /app

USER agent
EXPOSE 8000
CMD ["python", "run_mcp_server.py", "--http", "--host", "0.0.0.0", "--port", "8000"]
