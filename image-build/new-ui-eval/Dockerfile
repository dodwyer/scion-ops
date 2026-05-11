FROM node:22-bookworm-slim AS frontend

WORKDIR /app/new-ui-evaluation

COPY new-ui-evaluation/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY new-ui-evaluation/ ./
RUN npm run build

FROM python:3.12-slim

ENV HOST=0.0.0.0 \
    PORT=8080 \
    SCION_NEW_UI_EVAL_HOST=0.0.0.0 \
    SCION_NEW_UI_EVAL_PORT=8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=frontend /app/new-ui-evaluation/adapter.py /app/new-ui-evaluation/adapter.py
COPY --from=frontend /app/new-ui-evaluation/dist /app/new-ui-evaluation/dist
COPY --from=frontend /app/new-ui-evaluation/fixtures /app/new-ui-evaluation/fixtures

EXPOSE 8080

CMD ["python", "/app/new-ui-evaluation/adapter.py", "--host", "0.0.0.0", "--port", "8080"]
