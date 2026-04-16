# Whisper Service

This directory contains a local GPU-capable Whisper transcription service for the crawler.

It follows the same architecture as the OpenClaw example: the crawler calls a local HTTP service, and the service runs `whisper.cpp` in a Vulkan-enabled Docker image.

## Model Reuse

The launcher script prefers reusing an existing GGML model file instead of downloading another copy.

Default source model path:

- `/home/stever/projects/whisper models/ggml-large-v3.bin`

On first start, the launcher copies the model into `docker/whisper/models/` using `cp --reflink=auto` when possible.

## Service

- Default port: `10010`
- Health: `GET /health`
- Transcribe: `POST /transcribe`

`/transcribe` accepts either multipart form uploads or raw `application/octet-stream` audio.