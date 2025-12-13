FROM python:3.10-slim

WORKDIR /app

# Устанавливаем системные зависимости (включая wget и unzip!)
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    wget \
    unzip && \
    rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# ===== СКАЧИВАЕМ И РАСПАКОВЫВАЕМ VOSK МОДЕЛЬ =====
RUN echo "⏳ Скачиваю Vosk модель..." && \
    mkdir -p /tmp && \
    cd /tmp && \
    wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && \
    echo "✓ Распаковываю..." && \
    unzip -q vosk-model-small-en-us-0.15.zip && \
    mv vosk-model-small-en-us-0.15 vosk_model && \
    rm vosk-model-small-en-us-0.15.zip && \
    echo "✓ Модель готова!" && \
    ls -la /tmp/vosk_model/

# Копируем приложение
COPY app.py .

# Expose порт
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)" || exit 1

# Запускаем приложение
CMD ["python", "app.py"]
