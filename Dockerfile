FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TERM=xterm-256color

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper/ ./scraper/
COPY app/ ./app/

RUN mkdir -p /app/output /app/data
VOLUME ["/app/output", "/app/data"]

EXPOSE 8000

# Default: la CLI dello scraper. La dashboard è il servizio "dashboard" del compose.
ENTRYPOINT ["python", "-m", "scraper.main"]
CMD ["--help"]
