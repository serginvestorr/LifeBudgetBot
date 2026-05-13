import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "expenses.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                emoji TEXT NOT NULL,
                date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()


def save_expenses(user_id: int, expenses: list):
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().isoformat()
    with get_conn() as conn:
        for e in expenses:
            conn.execute(
                "INSERT INTO expenses (user_id, description, amount, category, emoji, date, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, e["description"], e["amount"], e["category"], e["emoji"], today, now)
            )
        conn.commit()


def get_monthly_report(user_id: int, month: str = None) -> str:
    if not month:
        month = datetime.now().strftime("%Y-%m")

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT category, emoji, SUM(amount) as total FROM expenses "
            "WHERE user_id = ? AND date LIKE ? "
            "GROUP BY category ORDER BY total DESC",
            (user_id, f"{month}%")
        ).fetchall()

        total_row = conn.execute(
            "SELECT SUM(amount) as total FROM expenses WHERE user_id = ? AND date LIKE ?",
            (user_id, f"{month}%")
        ).fetchone()

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
        rows = conn.execute(
            "SELECT id, description, amount, emoji, date FROM expenses "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_expense(user_id: int, expense_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM expenses WHERE id = ? AND user_id = ?",
            (expense_id, user_id)
        )
        conn.commit()
    return cursor.rowcount > 0
