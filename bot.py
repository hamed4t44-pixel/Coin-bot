import json
import random
import re
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

TOKEN = "8871423117:AAGQazGUveICtDgu9S1ouN27REvC8glaZ4w"
OWNER_ID = 6515459294

START_COINS = 100
GAME_TIMEOUT = 60
GAME_FEE = 5
TRANSFER_FEE = 8

COINS_FILE = "coins.json"

active_games = {}


def load_coins():
    try:
        with open(COINS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


coins = load_coins()


def save_coins():
    with open(COINS_FILE, "w", encoding="utf-8") as f:
        json.dump(coins, f, ensure_ascii=False, indent=2)


def is_owner(user_id):
    return int(user_id) == OWNER_ID


def get_balance(user_id):
    if is_owner(user_id):
        return 10**18

    uid = str(user_id)

    if uid not in coins:
        coins[uid] = START_COINS
        save_coins()

    return int(coins[uid])


def add_coins(user_id, amount):
    if is_owner(user_id):
        return

    uid = str(user_id)
    coins[uid] = get_balance(user_id) + int(amount)
    save_coins()


def remove_coins(user_id, amount):
    if is_owner(user_id):
        return

    uid = str(user_id)
    coins[uid] = max(0, get_balance(user_id) - int(amount))
    save_coins()


def normalize(text):
    table = str.maketrans(
        "۰۱۲۳۴۵۶۷۸۹",
        "0123456789"
    )
    return text.translate(table)
async def show_balance(update, context):
    user = update.effective_user
    balance = get_balance(user.id)

    if is_owner(user.id):
        text = (
            "👑 پروفایل مالک\n"
            "━━━━━━━━━━━━━━\n"
            f"👤 نام: {user.first_name or 'کاربر'}\n"
            f"🆔 آیدی: {user.id}\n"
            "🪙 موجودی: ♾️ نامحدود"
        )
    else:
        text = (
            "👤 پروفایل کاربر\n"
            "━━━━━━━━━━━━━━\n"
            f"👤 نام: {user.first_name or 'کاربر'}\n"
            f"🆔 آیدی: {user.id}\n"
            f"🪙 موجودی: {balance:,} COIN"
        )

    await update.message.chat.send_message(text)


async def transfer_coins(update, amount):
    sender = update.effective_user
    reply = update.message.reply_to_message

    if reply is None:
        await update.message.chat.send_message(
            "⛔ برای انتقال، روی پیام شخص موردنظر Reply کنید."
        )
        return

    receiver = reply.from_user

    if receiver.id == sender.id:
        await update.message.chat.send_message(
            "⛔ نمی‌توانید به خودتان انتقال دهید."
        )
        return

    if amount <= 0:
        return

    sender_balance = get_balance(sender.id)

    if not is_owner(sender.id):
        if sender_balance < amount:
            await update.message.chat.send_message(
                f"⛔ موجودی کافی نیست.\n"
                f"💰 موجودی: {sender_balance:,} COIN\n"
                f"🎟 مبلغ: {amount:,} COIN"
            )
            return

        remove_coins(sender.id, amount)

    fee = (amount * TRANSFER_FEE) // 100
    received = amount - fee

    add_coins(receiver.id, received)

    await update.message.chat.send_message(
        "✅ انتقال انجام شد\n"
        "━━━━━━━━━━━━━━\n"
        f"👤 فرستنده: {sender.first_name or 'کاربر'}\n"
        f"👤 گیرنده: {receiver.first_name or 'کاربر'}\n"
        f"🪙 مبلغ: {amount:,} COIN\n"
        f"➖ کارمزد 8%: {fee:,} COIN\n"
        f"✅ دریافتی: {received:,} COIN"
    )


async def create_game(update, amount):
    chat_id = update.effective_chat.id
    user = update.effective_user

    if amount < 10:
        await update.message.chat.send_message(
            "⛔ حداقل بازی 10 COIN است."
        )
        return

    if chat_id in active_games:
        await update.message.chat.send_message(
            "⚠️ یک بازی در این گروه فعال است."
        )
        return

    balance = get_balance(user.id)

    if not is_owner(user.id) and balance < amount:
        await update.message.chat.send_message(
            f"⛔ موجودی کافی نیست.\n"
            f"💰 موجودی: {balance:,} COIN"
        )
        return

    if not is_owner(user.id):
        remove_coins(user.id, amount)

    keyboard = [[
        InlineKeyboardButton(
            "✅ پیوستن",
            callback_data=f"join:{chat_id}"
        ),
        InlineKeyboardButton(
            "❌ لغو",
            callback_data=f"cancel:{chat_id}"
        )
    ]]

    message = await update.message.chat.send_message(
        "🎮 بازی سکه‌ای ساخته شد\n"
        "━━━━━━━━━━━━━━\n"
        f"👤 سازنده: {user.first_name or 'کاربر'}\n"
        f"🎟 ورودی: {amount:,} COIN\n"
        "👥 بازیکنان: 1/2\n\n"
        "برای پیوستن روی دکمه ✅ بزنید.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    active_games[chat_id] = {
        "creator": user.id,
        "amount": amount,
        "players": [user.id],
        "message_id": message.message_id
    }

    asyncio.create_task(
        game_timeout(chat_id, message.message_id)
    )
async def join_game(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    user = query.from_user
    game = active_games.get(chat_id)

    if not game:
        await query.answer(
            "⛔ این بازی تمام شده است.",
            show_alert=True
        )
        return

    if user.id in game["players"]:
        await query.answer(
            "⚠️ شما قبلاً وارد شده‌اید.",
            show_alert=True
        )
        return

    amount = game["amount"]
    balance = get_balance(user.id)

    if not is_owner(user.id) and balance < amount:
        await query.answer(
            f"❌ موجودی شما {balance:,} COIN است.",
            show_alert=True
        )
        return

    if not is_owner(user.id):
        remove_coins(user.id, amount)

    game["players"].append(user.id)

    player1 = game["players"][0]
    player2 = game["players"][1]

    winner = random.choice([player1, player2])

    if winner == player1:
        loser = player2
    else:
        loser = player1

    total = amount * 2
    fee = (total * GAME_FEE) // 100
    prize = total - fee

    add_coins(winner, prize)

    try:
        winner_member = await context.bot.get_chat_member(
            chat_id,
            winner
        )
        winner_name = (
            winner_member.user.first_name
            or "برنده"
        )
    except:
        winner_name = "برنده"

    try:
        loser_member = await context.bot.get_chat_member(
            chat_id,
            loser
        )
        loser_name = (
            loser_member.user.first_name
            or "بازنده"
        )
    except:
        loser_name = "بازنده"

    await query.edit_message_text(
        "🎲 نتیجه بازی\n"
        "━━━━━━━━━━━━━━\n"
        f"🏆 برنده: {winner_name}\n"
        f"💔 بازنده: {loser_name}\n"
        "━━━━━━━━━━━━━━\n"
        f"🎟 ورودی هر نفر: {amount:,} COIN\n"
        f"💰 مجموع: {total:,} COIN\n"
        f"➖ کارمزد 5%: {fee:,} COIN\n"
        f"🏆 جایزه برنده: {prize:,} COIN\n\n"
        "🎉 تبریک به برنده! 🍀"
    )

    del active_games[chat_id]


async def cancel_game(update, context):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat.id
    user = query.from_user
    game = active_games.get(chat_id)

    if not game:
        return

    if user.id != game["creator"]:
        await query.answer(
            "⛔ فقط سازنده می‌تواند لغو کند.",
            show_alert=True
        )
        return

    amount = game["amount"]

    if not is_owner(user.id):
        add_coins(user.id, amount)

    await query.edit_message_text(
        "❌ بازی لغو شد.\n"
        f"✅ مبلغ {amount:,} COIN برگشت داده شد."
    )

    del active_games[chat_id]


async def game_timeout(chat_id, message_id):
    await asyncio.sleep(GAME_TIMEOUT)

    game = active_games.get(chat_id)

    if not game:
        return

    if len(game["players"]) != 1:
        return

    amount = game["amount"]
    creator = game["creator"]

    if not is_owner(creator):
        add_coins(creator, amount)

    try:
        await application.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "⏰ زمان بازی تمام شد.\n\n"
                "❌ بازیکن دوم وارد نشد.\n"
                f"✅ مبلغ {amount:,} COIN برگشت داده شد."
            )
        )
    except:
        pass

    del active_games[chat_id]
async def start(update, context):
    await update.message.chat.send_message(
        "🤖 ربات Coin فعال است!\n\n"
        "💰 موجودی: موجودی\n"
        "🎮 بازی: بازی 100\n"
        "🔄 انتقال: روی پیام Reply کنید و بنویسید انتقال 100"
    )


async def message_handler(update, context):
    if not update.message:
        return

    text = update.message.text or ""
    text = normalize(text.strip())

    if text == "موجودی":
        await show_balance(update, context)
        return

    match = re.fullmatch(r"انتقال\s+(\d+)", text)

    if match:
        await transfer_coins(
            update,
            int(match.group(1))
        )
        return

    match = re.fullmatch(r"بازی\s+(\d+)", text)

    if match:
        await create_game(
            update,
            int(match.group(1))
        )


application = (
    Application
    .builder()
    .token(TOKEN)
    .build()
)

application.add_handler(
    CommandHandler("start", start)
)

application.add_handler(
    CallbackQueryHandler(
        join_game,
        pattern=r"^join:"
    )
)

application.add_handler(
    CallbackQueryHandler(
        cancel_game,
        pattern=r"^cancel:"
    )
)

application.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        message_handler
    )
)

print("🤖 ربات Coin در حال اجراست...")

application.run_polling()
