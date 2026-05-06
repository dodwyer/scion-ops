# syntax=docker/dockerfile:1
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG TASK_VERSION=v3.44.0
ARG UV_VERSION=0.9.16

USER root
RUN GOBIN=/usr/local/bin go install github.com/go-task/task/v3/cmd/task@${TASK_VERSION} \
  && python3 -m venv /opt/scion-ops-uv \
  && /opt/scion-ops-uv/bin/pip install --no-cache-dir "uv==${UV_VERSION}" \
  && ln -sf /opt/scion-ops-uv/bin/uv /usr/local/bin/uv \
  && task --version \
  && uv --version
