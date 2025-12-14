FROM python:3.10-slim
WORKDIR /app

RUN apt-get update && \
    apt-get install -y ffmpeg wget unzip git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ===== СКАЧИВАЕМ МОДЕЛЬ В /app (НЕ /tmp!) =====
RUN echo "⏳ Скачиваю Vosk модель..." && \
    wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && \
    echo "✓ Распаковываю..." && \
    unzip -q vosk-model-small-en-us-0.15.zip && \
    mv vosk-model-small-en-us-0.15 vosk_model && \
    rm vosk-model-small-en-us-0.15.zip && \
    echo "✓ Модель готова!" && \
    ls -la /app/vosk_model/

COPY app.py .

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)" || exit 1

CMD ["python", "app.py"]
