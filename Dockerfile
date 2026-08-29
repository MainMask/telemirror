FROM python:3.13-slim-bookworm AS build

ENV PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY ./requirements.txt /app/requirements.txt
# torch/simple-lama pins chosen without a live build check — verify on first deploy.
RUN pip install --target=/app/dependencies "simple-lama-inpainting==0.1.2" --no-deps && \
    pip install --target=/app/dependencies "torch==2.5.1" --index-url https://download.pytorch.org/whl/cpu && \
    pip install --target=/app/dependencies -r requirements.txt


FROM python:3.13-slim-bookworm AS release

# ffmpeg is needed at runtime by the watermark filter; its deps also cover
# the shared libs opencv-python-headless needs.
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m apprunner

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/dependencies

WORKDIR /app
COPY --from=build /app/dependencies /app/dependencies
COPY --chown=apprunner:apprunner . /app

USER apprunner

ARG PORT=8000
EXPOSE ${PORT}

CMD ["python", "main.py"]
