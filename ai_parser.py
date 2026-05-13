import os
import json
import base64
import aiohttp
import logging

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

CATEGORIES = {
    "продукты": "🛒",
    "кафе": "🍔",
    "транспорт": "🚇",
    "аптека": "💊",
    "одежда": "👕",
    "коммуналка": "🏠",
    "развлечения": "🎮",
    "другое": "📦",
}

SYSTEM_PROMPT = """Ты помощник для распознавания расходов. 
Из текста пользователя извлеки все расходы и верни их ТОЛЬКО в формате JSON массива.
Каждый элемент: {"description": "название", "amount": число, "category": "категория"}

Категории (выбери одну): продукты, кафе, транспорт, аптека, одежда, коммуналка, развлечения, другое

Если расходов нет — верни пустой массив [].
Верни ТОЛЬКО JSON, без пояснений и markdown."""


async def call_gemini(parts: list) -> str:
    payload = {
        "contents": [
            {
                "parts": [{"text": SYSTEM_PROMPT}] + parts
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1000,
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(GEMINI_URL, json=payload) as resp:
            data = await resp.json()

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        logger.error(f"Gemini response error: {data}")
        raise ValueError("Не удалось получить ответ от Gemini") from e


async def parse_expenses_from_text(text: str) -> list:
    parts = [{"text": f"Текст пользователя: {text}"}]
    raw = await call_gemini(parts)
    return _parse_json(raw)


async def parse_expenses_from_photo(photo_bytes: bytes) -> list:
    b64 = base64.b64encode(photo_bytes).decode("utf-8")
    parts = [
        {
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": b64
            }
        },
        {"text": "Это фото чека. Извлеки все позиции с ценами."}
    ]
    raw = await call_gemini(parts)
    return _parse_json(raw)


def _parse_json(raw: str) -> list:
    raw = raw.strip().strip("```json").strip("```").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON: {raw}")
        return []

    result = []
    for item in data:
        try:
            category = item.get("category", "другое").lower()
            emoji = CATEGORIES.get(category, "📦")
            result.append({
                "description": str(item["description"]),
                "amount": float(item["amount"]),
                "category": category,
                "emoji": emoji,
            })
        except (KeyError, ValueError):
            continue

    return result
