import os
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
ADMIN_ID = 1150548992  # Ваш chat_id
FEEDBACK_CHANNEL = -1001234567890  # Опционально: ID канала для отзывов
