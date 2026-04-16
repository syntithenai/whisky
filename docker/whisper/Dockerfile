FROM ghcr.io/ggml-org/whisper.cpp:main-vulkan

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages fastapi uvicorn python-multipart

COPY app.py /app/app.py

ENV MODEL_PATH=/models/ggml-large-v3.bin
ENV WHISPER_CPP_PATH=/app/build/bin/whisper-cli
ENV WHISPER_BACKEND_PREFERENCE=auto
ENV WHISPER_CPU_FALLBACK=true

EXPOSE 10000

ENTRYPOINT []
CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "10000"]