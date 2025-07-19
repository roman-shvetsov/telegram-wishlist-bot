from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUser
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.constants import ParseMode
from telegram.error import TimedOut, Forbidden, Conflict
from telegram.request import HTTPXRequest
from db import (
    init_db,
    register_user,
    get_user_wishlist,
    add_link_to_wishlist,
    create_friend_request,
    update_friend_request,
    get_pool,
    check_friendship,
    get_pending_requests,
    delete_gift_by_id,
    get_friends,
    remove_friend,
    get_user_by_id,
    add_feedback,
    reserve_gift,
    cancel_reservation,
    get_reservation_info,
    check_old_reservations
)
from config import TELEGRAM_TOKEN, ADMIN_ID
import asyncio
import logging
import asyncpg
import sys
import os

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Счетчик попыток перезапуска
RESTART_ATTEMPTS = 0
MAX_RESTART_ATTEMPTS = 3

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await register_user(user)

    await update.message.reply_text(
        """Надоело ломать голову над подарками? 🎁

Наш бот - твой личный помощник в мире подарков:
✨ Создавай вишлист своей мечты
✨ Узнавай желания друзей
✨ Дари то, что действительно нужно

Это проще простого:
1. Отправь боту ссылку на желаемый товар
2. Пригласи друзей одним кликом 👥
3. Обменивайтесь списками и радуйте друг друга идеальными подарками!️""",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

    await update.message.reply_text(
        "🔍 Подробнее о работе бота: /terms",
        disable_web_page_preview=True
    )

async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    terms_text = """
📜 *Условия использования бота*

1. *Как это работает*:
   - Вы добавляете ссылки на желаемые подарки
   - Ваши друзья видят ваш список и выбирают подарки
   - Вы видите списки своих друзей

2. *Конфиденциальность*:
   - Ваши списки видны только добавленным друзьям
   - Мы не передаем ваши данные третьим лицам
   - Вы можете удалить свои данные в любой момент

3. *Правила*:
   - Запрещено добавлять незаконные или опасные товары
   - Не злоупотребляйте добавлением друзей
   - Будьте вежливы с другими пользователями

Спасибо, что используете нашего бота! ❤️
"""
    await update.message.reply_text(
        terms_text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["🎁 Мой виш-лист"],
        ["👫 Добавить друга", "📋 Друзья"],
        ["🗑 Удалить подарок", "📝 Отзыв"]
    ], resize_keyboard=True)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    logger.info(f"Received button press: {message} from user {update.effective_user.id}")

    if message == '🎁 Мой виш-лист':
        await show_user_wishlist(update, context)
    elif message == '🗑 Удалить подарок':
        await show_gifts_to_delete(update, context)
    elif message == '👫 Добавить друга':
        await add_friend_handler(update, context)
    elif message == '📋 Друзья':
        await show_friends_list(update, context)
    elif message == '📝 Отзыв':
        await request_feedback(update, context)

async def check_gift_limit(user_id: int) -> bool:
    pool = get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval('SELECT COUNT(*) FROM wishlist WHERE user_id = $1', user_id)
        return count >= 15

async def show_user_wishlist(update: Update, context: ContextTypes.DEFAULT_TYPE, is_own_list=True):
    user_id = update.effective_user.id
    wishlist = await get_user_wishlist(user_id)

    if not wishlist:
        await update.message.reply_text("Твой список подарков пока пуст 😊 Давай добавим что-нибудь!")
        return

    for gift in wishlist:
        gift_link = gift['link']
        message_text = f"🎁 [Ссылка на товар]({gift_link})"

        if is_own_list:
            reservation = await get_reservation_info(gift['id'])
            if reservation:
                message_text += "\n\n🛑 *ЗАБРОНИРОВАНО*"

            await update.message.reply_text(
                message_text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False
            )
        else:
            reservation = await get_reservation_info(gift['id'])
            if reservation:
                if reservation['reserved_by'] == user_id:
                    message_text += "\n\n✅ *Вы забронировали этот подарок*"
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Отменить бронь", callback_data=f"cancel_reserve:{gift['id']}")]
                    ])
                else:
                    message_text += "\n\n🛑 *Уже забронировано*"
                    keyboard = None
            else:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔒 Забронировать", callback_data=f"reserve:{gift['id']}")]
                ])

            await update.message.reply_text(
                message_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=False
            )

async def show_gifts_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wishlist = await get_user_wishlist(update.effective_user.id)
    if not wishlist:
        await update.message.reply_text("Пока нечего удалять - список пуст 😉")
        return

    for gift in wishlist:
        link = gift["link"]
        gift_id = gift["id"]
        short_text = (link[:50] + '...') if len(link) > 50 else link

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Удалить", callback_data=f"delete:{gift_id}")]
        ])

        await update.message.reply_text(
            f"[{short_text}]({link})",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

async def add_friend_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("👤 Выбрать друга", request_user=KeyboardButtonRequestUser(
            request_id=1,
            user_is_bot=False,
            user_is_premium=None
        ))],
        ["🏠 Главное меню"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        "Нажмите кнопку ниже, чтобы выбрать друга из списка контактов:",
        reply_markup=keyboard
    )

async def handle_user_shared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received user_shared from user {update.effective_user.id}")
    user_shared = update.message.user_shared
    selected_user_id = user_shared.user_id

    if update.effective_user.id == selected_user_id:
        await update.message.reply_text(
            "Нельзя добавить самого себя в друзья 😊",
            reply_markup=main_keyboard()
        )
        return

    pool = get_pool()
    async with pool.acquire() as conn:
        friend = await conn.fetchrow('SELECT * FROM users WHERE id = $1', selected_user_id)

    if not friend:
        invite_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📩 Пригласить друга",
                url=f"https://t.me/share/url?url=https://t.me/{(await context.bot.get_me()).username}&text=Привет!%20Давай%20обмениваться%20списками%20желаний%20через%20этого%20бота!"
            )]
        ])

        await update.message.reply_text(
            "Этот пользователь ещё не использует нашего бота 😢\nПригласите его по ссылке ниже:",
            reply_markup=invite_keyboard
        )
        return

    if await check_friendship(update.effective_user.id, selected_user_id):
        await update.message.reply_text(
            "Вы уже друзья с этим пользователем!",
            reply_markup=main_keyboard()
        )
        return

    # Проверяем, есть ли существующий запрос
    pool = get_pool()
    async with pool.acquire() as conn:
        existing_request = await conn.fetchrow(
            'SELECT * FROM friend_requests WHERE from_user_id = $1 AND to_user_id = $2 AND status = $3',
            update.effective_user.id, selected_user_id, 'pending'
        )
        if existing_request:
            await update.message.reply_text(
                "Вы уже отправили запрос этому пользователю 😊",
                reply_markup=main_keyboard()
            )
            return

    # Создаем запрос в друзья
    success = await create_friend_request(update.effective_user.id, selected_user_id)
    if not success:
        await update.message.reply_text(
            "Не удалось создать запрос в друзья. Возможно, запрос уже существует.",
            reply_markup=main_keyboard()
        )
        return

    request_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"friend_request:accept:{update.effective_user.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"friend_request:reject:{update.effective_user.id}")
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=selected_user_id,
            text=f"👋 Пользователь {update.effective_user.first_name} хочет добавить вас в друзья!",
            reply_markup=request_keyboard
        )
        await update.message.reply_text(
            "Запрос в друзья успешно отправлен!",
            reply_markup=main_keyboard()
        )
    except Forbidden as e:
        logger.error(f"Ошибка: пользователь {selected_user_id} заблокировал бота: {e}")
        # Удаляем запрос из базы, если не удалось отправить сообщение
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM friend_requests WHERE from_user_id = $1 AND to_user_id = $2 AND status = $3',
                update.effective_user.id, selected_user_id, 'pending'
            )
        await update.message.reply_text(
            "Не удалось отправить запрос. Пользователь, возможно, заблокировал бота.",
            reply_markup=main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке запроса в друзья пользователю {selected_user_id}: {e}")
        # Удаляем запрос из базы при любой другой ошибке
        async with pool.acquire() as conn:
            await conn.execute(
                'DELETE FROM friend_requests WHERE from_user_id = $1 AND to_user_id = $2 AND status = $3',
                update.effective_user.id, selected_user_id, 'pending'
            )
        await update.message.reply_text(
            "Произошла ошибка при отправке запроса. Попробуйте позже.",
            reply_markup=main_keyboard()
        )

async def show_friends_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    friends = await get_friends(update.effective_user.id)
    if not friends:
        await update.message.reply_text(
            "У тебя пока нет друзей 😉 Добавь кого-нибудь, чтобы видеть их списки!",
            reply_markup=main_keyboard()
        )
        return

    for friend in friends:
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎁 Показать вишлист", callback_data=f"show_wishlist:{friend['id']}"),
                InlineKeyboardButton("❌ Удалить", callback_data=f"remove_friend:{friend['id']}")
            ]
        ])

        await update.message.reply_text(
            f"👤 {friend['first_name']} (@{friend['username']})",
            reply_markup=keyboard
        )

    pending_requests = await get_pending_requests(update.effective_user.id)
    if pending_requests:
        await update.message.reply_text("📥 Входящие запросы в друзья:")
        for request in pending_requests:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Принять", callback_data=f"friend_request:accept:{request['from_user_id']}"),
                    InlineKeyboardButton("❌ Отклонить",
                                        callback_data=f"friend_request:reject:{request['from_user_id']}")
                ]
            ])

            await update.message.reply_text(
                f"👤 {request['first_name']} (@{request['username']}) хочет добавить вас в друзья",
                reply_markup=keyboard
            )

async def handle_friend_request_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"Received friend request response: {query.data} from user {query.from_user.id}")

    action, from_user_id = query.data.split(":")[1:]
    from_user_id = int(from_user_id)
    to_user_id = query.from_user.id

    success = await update_friend_request(from_user_id, to_user_id, action)
    if not success:
        await query.edit_message_text("Не удалось найти активный запрос в друзья.")
        return

    from_user = await get_user_by_id(from_user_id)
    to_user = await get_user_by_id(to_user_id)

    if action == 'accept':
        await query.edit_message_text(
            f"✅ Вы приняли запрос в друзья от {from_user['first_name']} (@{from_user['username']})!"
        )
        try:
            await context.bot.send_message(
                chat_id=from_user_id,
                text=f"🎉 Пользователь {to_user['first_name']} (@{to_user['username']}) принял ваш запрос в друзья!"
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления о принятии дружбы пользователю {from_user_id}: {e}")
    else:
        await query.edit_message_text(
            f"❌ Вы отклонили запрос в друзья от {from_user['first_name']} (@{from_user['username']})"
        )
        try:
            await context.bot.send_message(
                chat_id=from_user_id,
                text=f"😢 Пользователь {to_user['first_name']} (@{to_user['username']}) отклонил ваш запрос в друзья."
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления об отклонении дружбы пользователю {from_user_id}: {e}")

async def check_reservations_periodically(context: ContextTypes.DEFAULT_TYPE):
    try:
        count = await check_old_reservations()
        if count > 0:
            logger.info(f"Автоматически отменено {count} старых бронирований")
    except Exception as e:
        logger.error(f"Ошибка при проверке бронирований: {e}")

async def handle_friend_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"Received callback: {query.data} from user {query.from_user.id}")

    try:
        if query.data.startswith("show_wishlist:"):
            friend_id = int(query.data.split(":")[1])
            friend = await get_user_by_id(friend_id)
            wishlist = await get_user_wishlist(friend_id)

            if not wishlist:
                await query.edit_message_text(f"🎁 У {friend['first_name']} пока нет подарков в списке 😢")
                return

            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"🎁 Список подарков {friend['first_name']}:"
            )

            current_user_id = query.from_user.id
            for gift in wishlist:
                gift_link = gift['link']
                message_text = f"🎁 [Ссылка на товар]({gift_link})"

                reservation = await get_reservation_info(gift['id'])
                if reservation:
                    if reservation['reserved_by'] == current_user_id:
                        message_text += "\n\n✅ *Вы забронировали этот подарок*"
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ Отменить бронь", callback_data=f"cancel_reserve:{gift['id']}")]
                        ])
                    else:
                        message_text += "\n\n🛑 *Уже забронировано*"
                        keyboard = None
                else:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔒 Забронировать", callback_data=f"reserve:{gift['id']}")]
                    ])

                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=message_text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=False
                )

        elif query.data.startswith("reserve:"):
            gift_id = int(query.data.split(":")[1])
            user_id = query.from_user.id

            pool = get_pool()
            async with pool.acquire() as conn:
                gift_info = await conn.fetchrow(
                    'SELECT w.link, w.user_id as owner_id, u.first_name '
                    'FROM wishlist w '
                    'JOIN users u ON w.user_id = u.id '
                    'WHERE w.id = $1',
                    gift_id
                )

            if not gift_info:
                await query.edit_message_text("Подарок не найден.")
                return

            gift_link = gift_info['link']

            if gift_info['owner_id'] == user_id:
                await query.edit_message_text("Нельзя забронировать свой собственный подарок 😊")
                return

            if await reserve_gift(gift_id, user_id):
                try:
                    message_text = f"🎉 <b>Кто-то хочет подарить вам этот подарок!</b>\n\n"
                    message_text += f"🔗 <a href=\"{gift_link}\">Ссылка на товар</a>\n\n"
                    message_text += "Теперь другие не смогут его забронировать!"

                    await context.bot.send_message(
                        chat_id=gift_info['owner_id'],
                        text=message_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False
                    )
                except Exception as e:
                    logger.error(f"Ошибка при уведомлении владельца: {e}")

                message_text = f"✅ <b>Вы забронировали этот подарок!</b>\n\n"
                message_text += f"🔗 <a href=\"{gift_link}\">Ссылка на товар</a>\n\n"
                message_text += "Теперь другие не смогут его выбрать. Не забудьте подарить его в течение 10 дней!"

                await query.edit_message_text(
                    text=message_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Отменить бронь", callback_data=f"cancel_reserve:{gift_id}")]
                    ])
                )
            else:
                await query.edit_message_text(
                    "Не удалось забронировать подарок. Возможно, он уже забронирован.",
                    parse_mode=ParseMode.HTML
                )

        elif query.data.startswith("cancel_reserve:"):
            gift_id = int(query.data.split(":")[1])
            user_id = query.from_user.id

            pool = get_pool()
            async with pool.acquire() as conn:
                gift_info = await conn.fetchrow(
                    'SELECT w.link, w.user_id as owner_id, u.first_name '
                    'FROM wishlist w '
                    'JOIN users u ON w.user_id = u.id '
                    'WHERE w.id = $1',
                    gift_id
                )

            if not gift_info:
                await query.edit_message_text("Подарок не найден.")
                return

            gift_link = gift_info['link']

            if await cancel_reservation(gift_id, user_id):
                try:
                    message_text = f"😢 <b>Кто-то передумал дарить вам этот подарок</b>\n\n"
                    message_text += f"🔗 <a href=\"{gift_link}\">Ссылка на товар</a>\n\n"
                    message_text += "Теперь его снова можно забронировать!"

                    await context.bot.send_message(
                        chat_id=gift_info['owner_id'],
                        text=message_text,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=False
                    )
                except Exception as e:
                    logger.error(f"Ошибка при уведомлении владельца: {e}")

                message_text = f"❌ <b>Вы отменили бронирование подарка</b>\n\n"
                message_text += f"🔗 <a href=\"{gift_link}\">Ссылка на товар</a>"

                await query.edit_message_text(
                    text=message_text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=False,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔒 Забронировать снова", callback_data=f"reserve:{gift_id}")]
                    ])
                )
            else:
                await query.edit_message_text(
                    "Не удалось отменить бронь. Возможно, она уже была отменена.",
                    parse_mode=ParseMode.HTML
                )

        elif query.data.startswith("remove_friend:"):
            friend_id = int(query.data.split(":")[1])
            user_id = query.from_user.id
            await remove_friend(user_id, friend_id)

            pool = get_pool()
            async with pool.acquire() as conn:
                # Очищаем все связанные запросы в друзья
                await conn.execute(
                    'DELETE FROM friend_requests WHERE (from_user_id = $1 AND to_user_id = $2) OR (from_user_id = $2 AND to_user_id = $1)',
                    user_id, friend_id
                )
                # Очищаем бронирования
                gifts = await conn.fetch(
                    'SELECT w.id FROM wishlist w '
                    'JOIN reservations r ON w.id = r.gift_id '
                    'WHERE w.user_id = $1 AND r.reserved_by = $2',
                    user_id, friend_id
                )
                friend_gifts = await conn.fetch(
                    'SELECT w.id FROM wishlist w '
                    'JOIN reservations r ON w.id = r.gift_id '
                    'WHERE w.user_id = $1 AND r.reserved_by = $2',
                    friend_id, user_id
                )

                for gift in gifts + friend_gifts:
                    await cancel_reservation(gift['id'], friend_id if gift in gifts else user_id)

            await query.edit_message_text("Друг удалён из списка 💔")

    except Exception as e:
        logger.error(f"Ошибка в handle_friend_callback: {e}")
        await query.edit_message_text("Произошла ошибка 😢 Попробуйте позже.")

async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    logger.info(f"Received delete callback: {query.data} from user {query.from_user.id}")

    if query.data.startswith("delete:"):
        gift_id = int(query.data.split("delete:")[1])
        await delete_gift_by_id(gift_id)
        await query.edit_message_text("Подарок удалён ✅")

async def request_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Received feedback request from user {update.effective_user.id}")
    await update.message.reply_text(
        "Напиши свой отзыв или предложение по улучшению бота. "
        "Мы ценим каждое мнение! 😊\n\n"
        "Можешь отправить текст, фото с подписью или просто фото.",
        reply_markup=ReplyKeyboardMarkup([["🏠 Главное меню"]], resize_keyboard=True)
    )
    context.user_data['awaiting_feedback'] = True

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_feedback'):
        return
    logger.info(f"Received media feedback from user {update.effective_user.id}")

    user = update.effective_user
    caption = update.message.caption or "Без описания"

    await add_feedback(user.id, user.username, caption)
    await update.message.reply_text(
        "Спасибо за ваш отзыв с медиа! 💖 Мы обязательно его рассмотрим.",
        reply_markup=main_keyboard()
    )

    try:
        if update.message.photo:
            photo = update.message.photo[-1].file_id
            await context.bot.send_photo(
                chat_id=ADMIN_ID,
                photo=photo,
                caption=f"📷 Отзыв от @{user.username} (id: {user.id}):\n\n{caption}"
            )
        elif update.message.document:
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=update.message.document.file_id,
                caption=f"📄 Отзыв от @{user.username} (id: {user.id}):\n\n{caption}"
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📦 Отзыв от @{user.username} (id: {user.id}):\n\n{caption}"
            )
    except Exception as e:
        logger.error(f"Ошибка при отправке медиа-отзыва админу: {e}")

    del context.user_data['awaiting_feedback']

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    logger.info(f"Received text message: {message} from user {update.effective_user.id}")

    if message == '🏠 Главное меню':
        if 'awaiting_feedback' in context.user_data:
            del context.user_data['awaiting_feedback']

        await update.message.reply_text("Главное меню:", reply_markup=main_keyboard())
        return

    if context.user_data.get('awaiting_feedback'):
        user = update.effective_user
        if "http" in message.lower():
            await update.message.reply_text("Ссылки в отзывах запрещены.", reply_markup=main_keyboard())
            return
        await add_feedback(user.id, user.username, message)

        await update.message.reply_text(
            "Спасибо за ваш отзыв! 💖 Мы обязательно его рассмотрим.",
            reply_markup=main_keyboard()
        )

        feedback_text = (
            f"📝 Новый отзыв от @{user.username} (id: {user.id}):\n\n"
            f"{message}"
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=feedback_text
            )
        except Exception as e:
            logger.error(f"Ошибка при отправке отзыва админу: {e}")

        del context.user_data['awaiting_feedback']
        return

    if message.startswith("http"):
        try:
            if await check_gift_limit(update.effective_user.id):
                await update.message.reply_text(
                    "🚫 Вы достигли лимита в 15 подарков в вашем списке!",
                    reply_markup=main_keyboard()
                )
                return
            gift_id = await add_link_to_wishlist(update.effective_user.id, message)
            logger.info(f"Successfully added gift with id {gift_id} for user {update.effective_user.id}")
            await update.message.reply_text("Подарок добавлен в твой список! 👍")
        except asyncpg.UniqueViolationError as e:
            logger.error(f"UniqueViolationError while adding link to wishlist: {e}")
            pool = get_pool()
            async with pool.acquire() as conn:
                await conn.execute("SELECT setval('wishlist_id_seq', (SELECT MAX(id) FROM wishlist))")
                logger.info("Synchronized wishlist_id_seq")
                try:
                    gift_id = await add_link_to_wishlist(update.effective_user.id, message)
                    logger.info(f"Successfully added gift with id {gift_id} for user {update.effective_user.id} after sequence sync")
                    await update.message.reply_text("Подарок добавлен в твой список! 👍")
                except Exception as e:
                    logger.error(f"Failed to add link to wishlist after sequence sync: {e}")
                    await update.message.reply_text(
                        "Произошла ошибка при добавлении подарка. Попробуйте позже.",
                        reply_markup=main_keyboard()
                    )
        except Exception as e:
            logger.error(f"Error while adding link to wishlist: {e}")
            await update.message.reply_text(
                "Произошла ошибка при добавлении подарка. Попробуйте позже.",
                reply_markup=main_keyboard()
            )
        return

    await handle_buttons(update, context)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Доступ запрещен.")
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT id FROM users")
    for user in users:
        try:
            await context.bot.send_message(chat_id=user['id'], text=" ".join(context.args))
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {user['id']}: {e}")
    await update.message.reply_text("Сообщение отправлено всем пользователям!")

async def post_init(application):
    await init_db()
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT setval('wishlist_id_seq', (SELECT MAX(id) FROM wishlist))")
            logger.info("Synchronized wishlist_id_seq at startup")
    except Exception as e:
        logger.error(f"Error synchronizing wishlist_id_seq at startup: {e}")

async def notify_admin(context: ContextTypes.DEFAULT_TYPE, message: str):
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"[Только для админа] {message}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок приложения"""
    global RESTART_ATTEMPTS
    logger.error(f"Update {update} caused error {context.error}")

    if isinstance(context.error, Conflict):
        logger.warning("Conflict detected: another bot instance is running. Attempting to recover...")
        if RESTART_ATTEMPTS >= MAX_RESTART_ATTEMPTS:
            logger.error("Max restart attempts reached. Stopping bot.")
            await notify_admin(context, f"⚠️ Максимальное количество попыток перезапуска ({MAX_RESTART_ATTEMPTS}) достигнуто. Бот остановлен.")
            sys.exit(1)

        RESTART_ATTEMPTS += 1
        try:
            await context.bot.delete_webhook()
            logger.info("Webhook deleted successfully")
            await context.application.stop()
            logger.info("Application stopped")
            await asyncio.sleep(5)
            RESTART_ATTEMPTS = 0  # Сбрасываем счетчик после успешного перезапуска
            logger.info("Attempting to restart polling...")
            await context.application.run_polling(
                drop_pending_updates=True,
                poll_interval=1.0,
                timeout=30
            )
        except Exception as e:
            logger.error(f"Failed to recover from Conflict: {e}")
            await notify_admin(context, f"⚠️ Ошибка: конфликт getUpdates. Не удалось перезапустить: {e}")
    elif isinstance(context.error, TimedOut):
        logger.warning("TimedOut detected. Retrying in 10 seconds...")
        try:
            await asyncio.sleep(10)
            await context.application.run_polling(
                drop_pending_updates=True,
                poll_interval=1.0,
                timeout=30
            )
        except Exception as e:
            logger.error(f"Failed to recover from TimedOut: {e}")
            await notify_admin(context, f"⚠️ Ошибка: TimedOut при запросе к Telegram API. Попытка переподключения не удалась: {e}")

def main():
    try:
        http_request = HTTPXRequest(
            connection_pool_size=50,  # Уменьшено для меньшей нагрузки
            read_timeout=30.0,
            write_timeout=10.0,
            connect_timeout=10.0,
            pool_timeout=30.0
        )

        app = ApplicationBuilder() \
            .token(TELEGRAM_TOKEN) \
            .post_init(post_init) \
            .concurrent_updates(True) \
            .get_updates_request(http_request) \
            .build()

        # Регистрация обработчиков
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("terms", terms))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
        app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, handle_media))
        app.add_handler(CallbackQueryHandler(handle_delete_callback, pattern="^delete:"))
        app.add_handler(CallbackQueryHandler(handle_friend_callback, pattern="^(show_wishlist|remove_friend|reserve|cancel_reserve):"))
        app.add_handler(CallbackQueryHandler(handle_friend_request_response, pattern="^friend_request:"))
        app.add_handler(MessageHandler(filters.StatusUpdate.USER_SHARED, handle_user_shared))
        app.add_handler(CommandHandler("broadcast", broadcast))
        app.add_error_handler(error_handler)

        app.job_queue.run_repeating(
            callback=check_reservations_periodically,
            interval=86400,
            first=10
        )

        logger.info("Запуск бота с Polling...")
        app.run_polling(
            drop_pending_updates=True,
            poll_interval=1.0,  # Увеличен интервал для стабильности
            timeout=30
        )

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        asyncio.run(notify_admin(None, f"⚠️ Критическая ошибка при запуске бота: {e}"))
        asyncio.run(asyncio.sleep(10))
        sys.exit(1)

if __name__ == "__main__":
    main()