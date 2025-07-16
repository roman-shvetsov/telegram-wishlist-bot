import asyncpg
import os
from dotenv import load_dotenv
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

pool = None

async def init_db():
    global pool
    for attempt in range(3):
        try:
            logger.info(f"Попытка подключения к базе данных (попытка {attempt + 1}): {DATABASE_URL}")
            pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
            logger.info("Подключение к базе данных успешно!")
            async with pool.acquire() as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id BIGINT PRIMARY KEY,
                        username TEXT,
                        first_name TEXT
                    );

                    CREATE TABLE IF NOT EXISTS wishlist (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                        link TEXT
                    );

                    CREATE TABLE IF NOT EXISTS friends (
                        user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                        friend_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                        PRIMARY KEY (user_id, friend_id)
                    );

                    CREATE TABLE IF NOT EXISTS feedback (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                        username TEXT,
                        text TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS friend_requests (
                        id SERIAL PRIMARY KEY,
                        from_user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                        to_user_id BIGINT REFERENCES users(id) ON DELETE CASCADE,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(from_user_id, to_user_id)
                    );

                    CREATE TABLE IF NOT EXISTS reservations (
                        id SERIAL PRIMARY KEY,
                        gift_id INTEGER REFERENCES wishlist(id) ON DELETE CASCADE,
                        reserved_by BIGINT REFERENCES users(id) ON DELETE CASCADE,
                        reserved_at TIMESTAMP DEFAULT NOW(),
                        UNIQUE(gift_id, reserved_by)
                    );
                ''')
            return
        except Exception as e:
            logger.error(f"Ошибка подключения к базе данных: {e}")
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)

def get_pool():
    if pool is None:
        raise RuntimeError("Database pool has not been initialized")
    return pool

async def register_user(user):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (id) DO NOTHING;
        ''', user.id, user.username, user.first_name)

async def add_link_to_wishlist(user_id, link):
    pool = get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow('''
            INSERT INTO wishlist (user_id, link)
            VALUES ($1, $2)
            RETURNING id;
        ''', user_id, link)
        return record['id']

async def get_user_wishlist(user_id):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch('''
            SELECT id, link 
            FROM wishlist 
            WHERE user_id = $1
            ORDER BY id
        ''', user_id)

async def delete_gift_by_id(gift_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM wishlist WHERE id = $1", gift_id)

async def get_user_by_id(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM users WHERE id = $1', user_id)

async def get_friends(user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch('''
            SELECT u.id, u.username, u.first_name 
            FROM friends f 
            JOIN users u ON f.friend_id = u.id 
            WHERE f.user_id = $1
        ''', user_id)

async def remove_friend(user_id: int, friend_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('''
                DELETE FROM friends 
                WHERE (user_id = $1 AND friend_id = $2) 
                OR (user_id = $2 AND friend_id = $1)
            ''', user_id, friend_id)
            await conn.execute('''
                DELETE FROM friend_requests 
                WHERE (from_user_id = $1 AND to_user_id = $2) 
                OR (from_user_id = $2 AND to_user_id = $1)
            ''', user_id, friend_id)

async def add_feedback(user_id: int, username: str, text: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO feedback (user_id, username, text)
            VALUES ($1, $2, $3);
        ''', user_id, username, text)

async def create_friend_request(from_user_id: int, to_user_id: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval('''
            SELECT EXISTS(
                SELECT 1 FROM friend_requests 
                WHERE (from_user_id = $1 AND to_user_id = $2)
                   OR (from_user_id = $2 AND to_user_id = $1)
            ) OR EXISTS(
                SELECT 1 FROM friends 
                WHERE (user_id = $1 AND friend_id = $2)
                   OR (user_id = $2 AND friend_id = $1)
            )
        ''', from_user_id, to_user_id)

        if exists:
            return False

        await conn.execute('''
            INSERT INTO friend_requests (from_user_id, to_user_id)
            VALUES ($1, $2)
        ''', from_user_id, to_user_id)
        return True

async def update_friend_request(from_user_id: int, to_user_id: int, status: str) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            request = await conn.fetchrow('''
                SELECT * FROM friend_requests 
                WHERE from_user_id = $1 AND to_user_id = $2 AND status = 'pending'
                LIMIT 1
                FOR UPDATE
            ''', from_user_id, to_user_id)

            if not request:
                return False

            if status == 'accept':
                await conn.execute('''
                    INSERT INTO friends (user_id, friend_id) 
                    VALUES ($1, $2), ($2, $1)
                    ON CONFLICT DO NOTHING
                ''', from_user_id, to_user_id)

            await conn.execute('''
                DELETE FROM friend_requests 
                WHERE id = $1
            ''', request['id'])

            return True

async def get_pending_requests(to_user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch('''
            SELECT fr.from_user_id, u.username, u.first_name
            FROM friend_requests fr
            JOIN users u ON fr.from_user_id = u.id
            WHERE fr.to_user_id = $1 AND fr.status = 'pending'
        ''', to_user_id)

async def check_friendship(user_id1: int, user_id2: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval('''
            SELECT EXISTS(
                SELECT 1 FROM friends 
                WHERE (user_id = $1 AND friend_id = $2)
                   OR (user_id = $2 AND friend_id = $1)
            )
        ''', user_id1, user_id2)

async def reserve_gift(gift_id: int, user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        gift = await conn.fetchrow('SELECT user_id FROM wishlist WHERE id = $1', gift_id)
        if not gift:
            return False

        if gift['user_id'] == user_id:
            return False

        existing = await conn.fetchrow(
            'SELECT 1 FROM reservations WHERE gift_id = $1',
            gift_id
        )
        if existing:
            return False

        await conn.execute(
            'INSERT INTO reservations (gift_id, reserved_by) VALUES ($1, $2)',
            gift_id, user_id
        )
        return True

async def cancel_reservation(gift_id: int, user_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            'DELETE FROM reservations WHERE gift_id = $1 AND reserved_by = $2',
            gift_id, user_id
        )
        return result != 'DELETE 0'

async def get_reservation_info(gift_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            'SELECT r.*, u.first_name, u.username FROM reservations r '
            'JOIN users u ON r.reserved_by = u.id '
            'WHERE r.gift_id = $1',
            gift_id
        )

async def check_old_reservations():
    pool = get_pool()
    async with pool.acquire() as conn:
        old_reservations = await conn.fetch(
            'SELECT r.id FROM reservations r '
            'WHERE r.reserved_at < NOW() - INTERVAL \'10 days\''
        )

        for reservation in old_reservations:
            await conn.execute(
                'DELETE FROM reservations WHERE id = $1',
                reservation['id']
            )

        return len(old_reservations)