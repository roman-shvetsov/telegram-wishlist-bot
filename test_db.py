import asyncio
from db import connect


async def test_connection():
    try:
        pool = await connect()
        async with pool.acquire() as conn:
            result = await conn.fetch("SELECT 1;")
            print("✅ Соединение с базой данных установлено!")
            print("Результат запроса:", result)
    except Exception as e:
        print("❌ Ошибка при подключении к базе:", e)

if __name__ == "__main__":
    asyncio.run(test_connection())
