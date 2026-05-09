# syntax=docker/dockerfile:1
ARG BASE_IMAGE=localhost/scion-base:latest
FROM ${BASE_IMAGE}

USER 1000:1000

ENV SCION_OPS_ROOT=/workspace/scion-ops \
    SCION_OPS_WEB_HOST=0.0.0.0 \
    SCION_OPS_WEB_PORT=8880 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8880

ENTRYPOINT ["python3", "/workspace/scion-ops/web_app/server.py"]
