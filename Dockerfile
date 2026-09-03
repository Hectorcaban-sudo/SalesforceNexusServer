# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React admin console ----------
FROM node:24-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

# ---------- Stage 2: backend runtime ----------
FROM python:3.12-slim AS backend

# Prevent Python from writing .pyc files and enable unbuffered logging output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# Built React admin console goes where main.py expects it: ../frontend/dist
COPY --from=frontend-build /frontend/dist /frontend/dist

# Persistent local storage - mount a volume here in production
RUN mkdir -p /app/data /app/logs
VOLUME ["/app/data", "/app/logs"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["python", "run.py"]
