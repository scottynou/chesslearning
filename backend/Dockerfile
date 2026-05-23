# ===== Stage 1 : compile lc0 (Leela Chess Zero) depuis les sources =====
# Aucune release Linux-CPU officielle precompilee, on build avec eigen
# (pas de GPU sur Cloud Run). ~5-8 min de build, vit dans une stage
# isolee pour ne pas alourdir l'image finale.
FROM debian:bookworm-slim AS lc0-builder
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        python3 \
        python3-pip \
        ninja-build \
        meson \
        gcc \
        g++ \
        libopenblas-dev \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch v0.30.0 https://github.com/LeelaChessZero/lc0.git /lc0 \
    && cd /lc0 \
    && CXX=g++ meson setup build --buildtype=release \
        -Dgtest=false \
        -Dblas=true \
    && cd build && ninja lc0

# ===== Stage 2 : runtime app =====
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV STOCKFISH_PATH=/usr/games/stockfish
ENV AI_PROVIDER=auto
ENV LC0_PATH=/opt/lc0/lc0
ENV MAIA_WEIGHTS_DIR=/opt/maia-weights
ENV MAIA_ENABLED=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        stockfish \
        wget \
        ca-certificates \
        libgomp1 \
        libstdc++6 \
        libopenblas0 \
        zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /lib/x86_64-linux-gnu/libz.so.1 /usr/lib/x86_64-linux-gnu/libz.so

# Recopie le binaire lc0 compile depuis le stage 1
RUN mkdir -p /opt/lc0
COPY --from=lc0-builder /lc0/build/lc0 /opt/lc0/lc0
RUN chmod +x /opt/lc0/lc0

# Poids Maia (humanisation reelle) - ~150 MB chacun.
# Fallback echec : le code retombe sur l'humanisation heuristique.
RUN mkdir -p /opt/maia-weights \
    && wget -q https://github.com/CSSLab/maia-chess/raw/master/maia_weights/maia-1500.pb.gz -O /opt/maia-weights/maia-1500.pb.gz \
    || (echo "maia-1500 download failed" && rm -f /opt/maia-weights/maia-1500.pb.gz)
RUN wget -q https://github.com/CSSLab/maia-chess/raw/master/maia_weights/maia-1900.pb.gz -O /opt/maia-weights/maia-1900.pb.gz \
    || (echo "maia-1900 download failed" && rm -f /opt/maia-weights/maia-1900.pb.gz)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
