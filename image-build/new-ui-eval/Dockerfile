FROM node:22-bookworm-slim AS frontend

WORKDIR /app/new-ui-evaluation

COPY new-ui-evaluation/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY new-ui-evaluation/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=frontend /app/new-ui-evaluation/adapter.py /app/new-ui-evaluation/adapter.py
COPY --from=frontend /app/new-ui-evaluation/dist /app/new-ui-evaluation/dist
COPY --from=frontend /app/new-ui-evaluation/fixtures /app/new-ui-evaluation/fixtures

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz', timeout=2)"

CMD ["python", "/app/new-ui-evaluation/adapter.py", "--host", "0.0.0.0", "--port", "8080"]
