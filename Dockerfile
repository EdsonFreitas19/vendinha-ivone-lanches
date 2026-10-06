FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Banco de dados e fotos ficam aqui: monte um volume/disco persistente neste caminho
ENV DATA_DIR=/data \
    COOKIE_SECURE=1 \
    PORT=8000
VOLUME /data
EXPOSE 8000

# 1 worker + threads: SQLite funciona bem assim para uma loja pequena
CMD ["sh", "-c", "gunicorn -w 1 --threads 4 -b 0.0.0.0:${PORT} app:app"]
