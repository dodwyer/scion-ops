# Build context: repo root new-ui-evaluation/ (adapter/ + frontend/dist/ from a prior Vite build).
# The Vite build must be run before building this image:
#   cd new-ui-evaluation && npm run build
FROM python:3.12-slim
WORKDIR /app

COPY adapter/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY frontend/dist ./static
COPY adapter/ ./adapter/

EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/healthz', timeout=2)"

CMD ["python", "-m", "adapter.main"]
