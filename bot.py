import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from dotenv import load_dotenv
 
from ai_parser import parse_expenses_from_text, parse_expenses_from_photo
from database import init_db, save_expenses, get_monthly_report, get_last_expenses, delete_expense
 
load_dotenv()
 
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
 
bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()
 
# --- Главная Reply-клавиатура ---
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Отчёт за месяц"), KeyboardButton(text="📋 Последние записи")],
        [KeyboardButton(text="❓ Помощь")],
    ],
    resize_keyboard=True,
    persistent=True,
)
 
 
def delete_kb(ids: list) -> InlineKeyboardMarkup:
    """Inline-кнопки «🗑 Удалить #id» для каждой сохранённой записи."""
    buttons = [
        [InlineKeyboardButton(text=f"🗑 Удалить #{expense_id}", callback_data=f"del:{expense_id}")]
        for expense_id in ids
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
 
 
def delete_kb_last(records: list) -> InlineKeyboardMarkup:
    """Inline-кнопки удаления для списка /last."""
    buttons = [
        [InlineKeyboardButton(
            text=f"🗑 #{r['id']} {r['emoji']} {r['description'][:20]}",
            callback_data=f"del:{r['id']}"
        )]
        for r in records
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
 
 
# --- Callback: удаление по inline-кнопке ---
@dp.callback_query(F.data.startswith("del:"))
async def cb_delete(callback: CallbackQuery):
    expense_id = int(callback.data.split(":")[1])
    success = delete_expense(callback.from_user.id, expense_id)
 
    if success:
        await callback.answer(f"Запись #{expense_id} удалена ✅")
        # Убираем только эту кнопку из клавиатуры
        old_rows = callback.message.reply_markup.inline_keyboard
        new_rows = [row for row in old_rows if row[0].callback_data != f"del:{expense_id}"]
        new_kb = InlineKeyboardMarkup(inline_keyboard=new_rows) if new_rows else None
        await callback.message.edit_reply_markup(reply_markup=new_kb)
    else:
        await callback.answer(f"Запись #{expense_id} не найдена ❌")
 
 
# --- /start ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я помогу тебе отслеживать расходы.\n\n"
        "📝 Просто напиши мне о своих тратах:\n"
        "  • Текстом: «кофе 150, хлеб 89, такси 350»\n"
        "  • Или пришли фото чека 📸\n\n"
        "Используй кнопки внизу для быстрого доступа к командам.",
        reply_markup=main_kb,
    )
 
 
# --- /help и кнопка ---
@dp.message(Command("help"))
@dp.message(F.text == "❓ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "📖 Как пользоваться ботом:\n\n"
        "Просто пиши о тратах в любом формате:\n"
        "  • «кофе 150»\n"
        "  • «продукты 1200, бензин 2000»\n"
        "  • «потратил 500 на кино»\n"
        "  • Или присылай фото чека 📸\n\n"
        "После записи появятся кнопки удаления — нажми нужную.\n"
        "Или: /report 2025-04 — отчёт за конкретный месяц",
        reply_markup=main_kb,
    )
 
 
# --- /report и кнопка ---
@dp.message(Command("report"))
@dp.message(F.text == "📊 Отчёт за месяц")
async def cmd_report(message: Message):
    args = message.text.split() if message.text else []
    month = args[1] if len(args) > 1 else None
 
    await message.answer("📊 Собираю отчёт...")
    report = get_monthly_report(message.from_user.id, month)
    if not report:
        await message.answer("За этот период записей нет.")
        return
    await message.answer(report)
 
 
# --- /last и кнопка ---
@dp.message(Command("last"))
@dp.message(F.text == "📋 Последние записи")
async def cmd_last(message: Message):
    records = get_last_expenses(message.from_user.id)
    if not records:
        await message.answer("Записей пока нет.")
        return
 
    text = "📋 Последние записи:\n\n"
    for r in records:
        text += f"#{r['id']} {r['emoji']} {r['description']} — {r['amount']}₽ ({r['date']})\n"
    text += "\nНажми кнопку ниже, чтобы удалить запись:"
 
    await message.answer(text, reply_markup=delete_kb_last(records))
 
 
# --- /delete (текстовая команда, для совместимости) ---
@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Укажи ID записи: /delete 5")
        return
 
    expense_id = int(args[1])
    success = delete_expense(message.from_user.id, expense_id)
    if success:
        await message.answer(f"✅ Запись #{expense_id} удалена.")
    else:
        await message.answer(f"❌ Запись #{expense_id} не найдена.")
 
 
# --- Фото чека ---
@dp.message(F.photo)
async def handle_photo(message: Message):
    await message.answer("📸 Обрабатываю фото чека...")
 
    try:
        photo = message.photo[-1]
        file = await bot.get_file(photo.file_id)
        file_url = f"https://api.telegram.org/file/bot{os.getenv('TELEGRAM_TOKEN')}/{file.file_path}"
 
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                photo_bytes = await resp.read()
 
        expenses = await parse_expenses_from_photo(photo_bytes)
 
        if not expenses:
            await message.answer("😕 Не смог распознать чек. Попробуй написать расходы текстом.")
            return
 
        ids = save_expenses(message.from_user.id, expenses)
        text, kb = format_saved_response(expenses, ids)
        await message.answer(text, reply_markup=kb)
 
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await message.answer("❌ Ошибка при обработке фото. Попробуй ещё раз.")
 
 
# --- Текстовое сообщение ---
@dp.message(F.text)
async def handle_text(message: Message):
    if message.text.startswith("/"):
        return
 
    await message.answer("⏳ Обрабатываю...")
 
    try:
        expenses = await parse_expenses_from_text(message.text)
 
        if not expenses:
            await message.answer(
                "😕 Не смог найти расходы в сообщении.\n"
                "Попробуй написать например: «кофе 150, хлеб 89»"
            )
            return
 
        ids = save_expenses(message.from_user.id, expenses)
        text, kb = format_saved_response(expenses, ids)
        await message.answer(text, reply_markup=kb)
 
    except Exception as e:
        logger.error(f"Text error: {e}")
        await message.answer("❌ Ошибка. Попробуй ещё раз.")
 
 
def format_saved_response(expenses: list, ids: list) -> tuple:
    total = sum(e["amount"] for e in expenses)
    lines = [f"{e['emoji']} {e['description']} — {e['amount']}₽" for e in expenses]
    text = "✅ Записал:\n" + "\n".join(lines)
    if len(expenses) > 1:
        text += f"\n\nИтого: {total}₽"
    return text, delete_kb(ids)
 
 
async def main():
    init_db()
    logger.info("Bot started!")
    await dp.start_polling(bot)
 
 
if __name__ == "__main__":
    asyncio.run(main())
