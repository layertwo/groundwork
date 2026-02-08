FROM node:24-slim AS frontend

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.14-slim AS base

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY alembic/ alembic/
COPY alembic.ini .
COPY --from=frontend /app/frontend/dist frontend/dist
COPY entrypoint.sh .

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
