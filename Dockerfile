# ---- RailMate production image ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RAILMATE_ENV=production

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Build the timetable database and train the model at image build time,
# then delete the ~100 MB raw download to keep the image small.
RUN python -m scripts.build_dataset \
 && python -m ml.train_delay_model \
 && rm -rf data/raw \
 && useradd --create-home --uid 10001 appuser \
 && mkdir -p /app/var \
 && chown -R appuser:appuser /app/var

USER appuser
EXPOSE 8000
VOLUME ["/app/var"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
