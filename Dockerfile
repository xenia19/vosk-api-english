FROM python:3.10-slim

WORKDIR /app

# Устанавливаем зависимости системы
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем приложение
COPY app.py .

# Expose порт
EXPOSE 5000

# Здоровьечек проверка (чтобы Render не подумал, что контейнер упал)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health', timeout=5)" || exit 1

# Запускаем приложение
CMD ["python", "app.py"]
