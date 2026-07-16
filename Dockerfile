# Stage 1: Build PyInstaller bundle
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libzmq3-dev libomp-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt pyinstaller

COPY . .
RUN pyinstaller --clean --noconfirm bci-runtime.spec && \
    ls dist/

# Stage 2: Minimal runtime
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libzmq5 libgomp1 libstdc++6 ca-certificates procps && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/daemon_config.json /app/
COPY --from=builder /build/dist/bci-runtime /app/

EXPOSE 5555
EXPOSE 5556
EXPOSE 5557

HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=3 \
    CMD pgrep -f bci-runtime > /dev/null || exit 1

ENV BCI_BIND_HOST=0.0.0.0
ENV BCI_DAEMON_CONFIG=/app/daemon_config.json
ENV PYTHONUNBUFFERED=1

WORKDIR /app
ENTRYPOINT ["/app/bci-runtime"]
