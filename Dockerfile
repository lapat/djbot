FROM python:3.11-slim

# System deps: ffmpeg (audio), rubberband (time-stretch), libsndfile (soundfile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    librubberband-dev \
    rubberband-cli \
    libsndfile1 \
    libsndfile1-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch first (much smaller than CUDA — beat_this only needs CPU)
RUN pip install --no-cache-dir \
    torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Remaining Python deps (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download beat_this model into the image layer so Railway doesn't re-fetch on each run
RUN python -c "from beat_this.inference import File2Beats; File2Beats(checkpoint='final0', device='cpu', dbn=False); print('beat_this model cached')"

# App code
COPY . .

CMD ["python", "-m", "pipeline.worker"]
