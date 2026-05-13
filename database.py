import os
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
 
logger = logging.getLogger(__name__)
 
DATABASE_URL = os.getenv("DATABASE_URL")
 
 
def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
 
 
def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    description TEXT NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    emoji TEXT NOT NULL,
                    date TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        conn.commit()
 
 
def save_expenses(user_id: int, expenses: list) -> list[int]:
    """Сохраняет расходы и возвращает список присвоенных ID."""
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().isoformat()
    ids = []
    with get_conn() as conn:
        with conn.cursor() as cur:
            for e in expenses:
                cur.execute(
                    "INSERT INTO expenses (user_id, description, amount, category, emoji, date, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (user_id, e["description"], e["amount"], e["category"], e["emoji"], today, now)
                )
                row = cur.fetchone()
                ids.append(row["id"])
        conn.commit()
    return ids
 
 
def get_monthly_report(user_id: int, month: str = None) -> str:
    if not month:
        month = datetime.now().strftime("%Y-%m")
 
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT category, emoji, SUM(amount) as total FROM expenses "
                "WHERE user_id = %s AND date LIKE %s "
                "GROUP BY category, emoji ORDER BY total DESC",
                (user_id, f"{month}%")
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT SUM(amount) as total FROM expenses WHERE user_id = %s AND date LIKE %s",
                (user_id, f"{month}%")
            )
            total_row = cur.fetchone()
 
    if not rows:
        return None
 
    lines = [f"📊 Отчёт за {month}:\n"]
    for row in rows:
        lines.append(f"{row['emoji']} {row['category'].capitalize()} — {row['total']:.0f}₽")
 
    total = total_row["total"] or 0
    lines.append(f"\n💰 Итого: {total:.0f}₽")
    return "\n".join(lines)
 
 
def get_last_expenses(user_id: int, limit: int = 10) -> list:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, description, amount, emoji, date FROM expenses "
                "WHERE user_id = %s ORDER BY id DESC LIMIT %s",
                (user_id, limit)
            )
            rows = cur.fetchall()
    return [dict(r) for r in rows]
 
 
def delete_expense(user_id: int, expense_id: int) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM expenses WHERE id = %s AND user_id = %s",
                (expense_id, user_id)
            )
            deleted = cur.rowcount
        conn.commit()
    return deleted > 0
