FROM node:22-slim AS liff-builder

WORKDIR /build/liff-app
COPY liff-app/package*.json ./
RUN npm ci
COPY liff-app/ ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=liff-builder /build/liff-app/dist ./liff-app/dist

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
