FROM python:3.10-slim

WORKDIR /app

# Устанавливаем FFmpeg (нужен для pydub конвертации)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем приложение
COPY app.py .

# Expose порт
EXPOSE 5000

# Запускаем приложение
CMD ["python", "app.py"]
