# syntax=docker/dockerfile:1
ARG BASE_IMAGE=localhost/scion-base:latest
FROM ${BASE_IMAGE}

USER root

ENV VIRTUAL_ENV=/opt/scion-ops-mcp/venv

RUN python3 -m venv "${VIRTUAL_ENV}" \
  && "${VIRTUAL_ENV}/bin/pip" install --no-cache-dir "mcp>=1.13,<2" "PyYAML>=6,<7"

ENV PATH="${VIRTUAL_ENV}/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    SCION_OPS_ROOT=/workspace/scion-ops \
    SCION_OPS_MCP_TRANSPORT=streamable-http \
    SCION_OPS_MCP_HOST=0.0.0.0 \
    SCION_OPS_MCP_PORT=8765 \
    SCION_OPS_MCP_PATH=/mcp

WORKDIR /workspace/scion-ops
USER 1000:1000
EXPOSE 8765

ENTRYPOINT ["python", "/workspace/scion-ops/mcp_servers/scion_ops.py"]
