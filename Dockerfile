# Базовый образ
FROM python:3.11-slim

# Установка рабочей директории
WORKDIR /app

# Создание директории для HTML и установка прав
RUN mkdir -p /app/html && chmod -R 777 /app/html

# Копирование requirements.txt
COPY requirements.txt .

# Обновление pip и установка зависимостей
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование остального кода
COPY . .

# Команда для запуска приложения
CMD ["python", "main.py"]