# Базовый образ
FROM python:3.12-slim

# Установка зависимостей для Chrome и ChromeDriver
RUN apt-get update && apt-get install -y \
    wget \
    unzip \
    gnupg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

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