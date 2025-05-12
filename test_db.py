import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_connection():
    # Получаем DATABASE_URL из переменной окружения
    conn = await asyncpg.connect(os.getenv("NEW_DATABASE_URL"))
    print("Подключение успешно!")
    await conn.close()

import asyncio
asyncio.run(test_connection())
