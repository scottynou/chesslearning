FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV STOCKFISH_PATH=/usr/games/stockfish
ENV AI_PROVIDER=auto

# Maia (lc0 + poids) - desactive par defaut (MAIA_ENABLED=false).
# Pour activer en prod : --update-env-vars MAIA_ENABLED=true sur Cloud Run.
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
    && rm -rf /var/lib/apt/lists/*

# --- Installation de lc0 (Leela Chess Zero) version CPU avec backend Eigen ---
# Le binaire precompile est petit (~10MB), mais necessite eigen3 pour le backend CPU.
# On utilise une release stable publiee par les mainteneurs lc0.
RUN mkdir -p /opt/lc0 \
    && wget -q https://github.com/LeelaChessZero/lc0/releases/download/v0.31.2/lc0-v0.31.2-linux-cpu-dnnl.tar.gz -O /tmp/lc0.tar.gz \
    && tar -xzf /tmp/lc0.tar.gz -C /opt/lc0 --strip-components=1 \
    && chmod +x /opt/lc0/lc0 \
    && rm /tmp/lc0.tar.gz \
    || (echo "lc0 download failed - Maia desactive" && rm -rf /opt/lc0)

# --- Poids Maia (humanisation reelle) ---
# On telecharge maia-1500 (lambda) et maia-1900 (strong/veryStrong).
# Chaque fichier fait ~150 MB. Si le telechargement echoue, on continue
# sans Maia (le code retombe sur l'humanisation heuristique).
RUN mkdir -p /opt/maia-weights \
    && wget -q https://github.com/CSSLab/maia-chess/raw/master/maia_weights/maia-1500.pb.gz -O /opt/maia-weights/maia-1500.pb.gz \
    || (echo "maia-1500 download failed" && rm -f /opt/maia-weights/maia-1500.pb.gz)
RUN wget -q https://github.com/CSSLab/maia-chess/raw/master/maia_weights/maia-1900.pb.gz -O /opt/maia-weights/maia-1900.pb.gz \
    || (echo "maia-1900 download failed" && rm -f /opt/maia-weights/maia-1900.pb.gz)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
