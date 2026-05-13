import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

from ai_parser import parse_expenses_from_text, parse_expenses_from_photo
from database import init_db, save_expenses, get_monthly_report, get_last_expenses, delete_expense

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=os.getenv("TELEGRAM_TOKEN"))
dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 Привет! Я помогу тебе отслеживать расходы.\n\n"
        "📝 Просто напиши мне о своих тратах:\n"
        "  • Текстом: «кофе 150, хлеб 89, такси 350»\n"
        "  • Или пришли фото чека\n\n"
        "📊 Команды:\n"
        "  /report — итог за текущий месяц\n"
        "  /last — последние 10 записей\n"
        "  /help — помощь"
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📖 Как пользоваться ботом:\n\n"
        "Просто пиши о тратах в любом формате:\n"
        "  • «кофе 150»\n"
        "  • «продукты 1200, бензин 2000»\n"
        "  • «потратил 500 на кино»\n"
        "  • Или присылай фото чека 📸\n\n"
        "Команды:\n"
        "  /report — отчёт за этот месяц\n"
        "  /report 2025-04 — отчёт за апрель 2025\n"
        "  /last — последние 10 записей\n"
        "  /delete [id] — удалить запись по номеру"
    )


@dp.message(Command("report"))
async def cmd_report(message: Message):
    args = message.text.split()
    month = args[1] if len(args) > 1 else None

    await message.answer("📊 Собираю отчёт...")
    report = get_monthly_report(message.from_user.id, month)

    if not report:
        await message.answer("За этот период записей нет.")
        return

    await message.answer(report)


@dp.message(Command("last"))
async def cmd_last(message: Message):
    records = get_last_expenses(message.from_user.id)
    if not records:
        await message.answer("Записей пока нет.")
        return

    text = "📋 Последние записи:\n\n"
    for r in records:
        text += f"#{r['id']} {r['emoji']} {r['description']} — {r['amount']}₽ ({r['date']})\n"

    await message.answer(text)


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

        save_expenses(message.from_user.id, expenses)
        response = format_saved_response(expenses)
        await message.answer(response)

    except Exception as e:
        logger.error(f"Photo error: {e}")
        await message.answer("❌ Ошибка при обработке фото. Попробуй ещё раз.")


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

        save_expenses(message.from_user.id, expenses)
        response = format_saved_response(expenses)
        await message.answer(response)

    except Exception as e:
        logger.error(f"Text error: {e}")
        await message.answer("❌ Ошибка. Попробуй ещё раз.")


def format_saved_response(expenses):
    total = sum(e["amount"] for e in expenses)
    lines = [f"{e['emoji']} {e['description']} — {e['amount']}₽" for e in expenses]
    text = "✅ Записал:\n" + "\n".join(lines)
    if len(expenses) > 1:
        text += f"\n\nИтого: {total}₽"
    return text


async def main():
    init_db()
    logger.info("Bot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
