FROM python:3.11-slim-bookworm

WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[ib]"

COPY config/gateway.yaml /config/gateway.yaml
COPY scripts/run_ib_gateway.py ./scripts/run_ib_gateway.py

ENV IB_GATEWAY_CONFIG=/config/gateway.yaml
ENV PYTHONUNBUFFERED=1

CMD ["python", "scripts/run_ib_gateway.py"]
