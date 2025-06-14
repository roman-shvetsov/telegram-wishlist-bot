FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    libx11-6 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libxtst6 \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i google-chrome-stable_current_amd64.deb || apt-get update && apt-get install -y -f \
    && rm google-chrome-stable_current_amd64.deb

RUN google-chrome --version

WORKDIR /app
RUN mkdir -p /app/html && chmod -R 777 /app/html
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]