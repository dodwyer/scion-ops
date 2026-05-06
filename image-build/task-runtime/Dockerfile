# syntax=docker/dockerfile:1
ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG TASK_VERSION=v3.44.0
ARG UV_VERSION=0.9.16
ARG KIND_VERSION=v0.30.0
ARG KUBECTL_VERSION=v1.33.1

USER root
RUN set -eux; \
  arch="$(dpkg --print-architecture)"; \
  case "${arch}" in \
    amd64|arm64) tool_arch="${arch}" ;; \
    *) echo "unsupported architecture: ${arch}" >&2; exit 1 ;; \
  esac; \
  GOBIN=/usr/local/bin go install github.com/go-task/task/v3/cmd/task@${TASK_VERSION}; \
  curl -fsSL -o /usr/local/bin/kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${tool_arch}"; \
  curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${tool_arch}/kubectl"; \
  chmod 0755 /usr/local/bin/kind /usr/local/bin/kubectl; \
  python3 -m venv /opt/scion-ops-uv; \
  /opt/scion-ops-uv/bin/pip install --no-cache-dir "uv==${UV_VERSION}"; \
  ln -sf /opt/scion-ops-uv/bin/uv /usr/local/bin/uv; \
  task --version; \
  uv --version; \
  kind --version; \
  kubectl version --client=true
