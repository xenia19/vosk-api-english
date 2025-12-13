FROM python:3.10-slim

WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && \
    apt-get install -y ffmpeg git wget unzip && \
    rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# ===== СКАЧИВАЕМ VOSK МОДЕЛЬ ПРИ BUILD'Е =====
RUN echo "⏳ Скачиваю Vosk модель..." && \
    mkdir -p /tmp && \
    cd /tmp && \
    wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip && \
    echo "✓ Распаковываю..." && \
    unzip -q vosk-model-small-en-us-0.15.zip && \
    mv vosk-model-small-en-us-0.15 vosk_model && \
    rm vosk-model-small-en-us-0.15.zip && \
    echo "✓ Модель готова!"

# Копируем приложение
COPY app.py .

# Expose порт
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)" || exit 1

# Запускаем приложение
CMD ["python", "app.py"]
