FROM node:22-bookworm-slim AS frontend

WORKDIR /app/new-ui-evaluation

COPY new-ui-evaluation/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY new-ui-evaluation/ ./
RUN npm run build

FROM localhost/scion-ops-mcp:latest

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NEW_UI_EVALUATION_MODE=live

WORKDIR /app

COPY --from=frontend /app/new-ui-evaluation/adapter.py /app/new-ui-evaluation/adapter.py
COPY --from=frontend /app/new-ui-evaluation/dist /app/new-ui-evaluation/dist
COPY --from=frontend /app/new-ui-evaluation/fixtures /app/new-ui-evaluation/fixtures

RUN chown -R 1000:1000 /app/new-ui-evaluation

USER 1000:1000

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s \
  CMD /opt/scion-ops-mcp/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz', timeout=2)"

ENTRYPOINT ["/opt/scion-ops-mcp/venv/bin/python", "/app/new-ui-evaluation/adapter.py"]
CMD ["--host", "0.0.0.0", "--port", "8080"]
