from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from flask import current_app, g

BRANCHES = {
    "sql": {"title": "SQL", "symbol": "{ }", "description": "Запросы, связи и закономерности в данных.", "topics": "JOIN · GROUP BY · Оконные функции", "label": "Работа с данными"},
    "python": {"title": "Python", "symbol": "py", "description": "От первых строк кода до анализа данных.", "topics": "Синтаксис · pandas · NumPy", "label": "Программирование"},
    "ml": {"title": "Machine Learning", "symbol": "✳", "description": "Модели, которые учатся находить ответы.", "topics": "Признаки · Обучение · Метрики", "label": "Машинное обучение"},
}

SECTIONS = {
    "yandex": {"title": "Конспект ЯндексПрактикум", "description": "Теория, заметки и важные выводы из курса.", "symbol": "01"},
    "books": {"title": "Конспект по книгам", "description": "Идеи и примеры из прочитанных книг.", "symbol": "02"},
    "tasks": {"title": "Решение задач", "description": "Условия, ход решения и разбор ошибок.", "symbol": "03"},
}


def get_db():
    if "db" not in g:
        url = current_app.config["DATABASE_URL"]
        if not url:
            raise psycopg.OperationalError("DATABASE_URL is required")
        g.db = psycopg.connect(url, row_factory=dict_row, connect_timeout=5, autocommit=True)
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with db.transaction():
        db.execute(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        for migration in sorted(Path(__file__).with_name("migrations").glob("*.sql")):
            db.execute(migration.read_text(encoding="utf-8"))


def overview():
    db = get_db()
    counts = {key: {"note": 0, "question": 0} for key in BRANCHES}
    for row in db.execute("SELECT branch, kind, count(*) AS total FROM materials GROUP BY branch, kind"):
        counts[row["branch"]][row["kind"]] = row["total"]
    recent = db.execute("SELECT * FROM materials ORDER BY updated_at DESC, id DESC LIMIT 5").fetchall()
    return counts, recent


def section_counts(branch):
    counts = {key: 0 for key in (*SECTIONS, "")}
    rows = get_db().execute("SELECT section, count(*) AS total FROM materials WHERE branch=%s GROUP BY section", (branch,))
    for row in rows:
        counts[row["section"]] = row["total"]
    return counts


def list_materials(branch, kind="", query="", section=None):
    conditions, params = ["branch = %s"], [branch]
    if section is not None:
        conditions.append("section = %s")
        params.append(section)
    if kind:
        conditions.append("kind = %s")
        params.append(kind)
    if query:
        conditions.append("(strpos(lower(title), lower(%s)) > 0 OR strpos(lower(content), lower(%s)) > 0 OR strpos(lower(answer), lower(%s)) > 0)")
        params.extend([query] * 3)
    # Only fixed SQL fragments are concatenated. User input stays in bound parameters.
    return get_db().execute("SELECT * FROM materials WHERE " + " AND ".join(conditions) + " ORDER BY updated_at DESC, id DESC LIMIT 200", params).fetchall()


def get_material(material_id):
    return get_db().execute("SELECT * FROM materials WHERE id = %s", (material_id,)).fetchone()


def save_material(data, material_id=None):
    db = get_db()
    params = (data["branch"], data["kind"], data["title"], data["content"], data["answer"], data.get("section", ""))
    with db.transaction():
        if material_id is None:
            row = db.execute("INSERT INTO materials (branch, kind, title, content, answer, section) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", params).fetchone()
        else:
            row = db.execute("UPDATE materials SET branch=%s, kind=%s, title=%s, content=%s, answer=%s, section=%s, updated_at=now() WHERE id=%s RETURNING id", params + (material_id,)).fetchone()
        return row["id"] if row else None


def delete_material(material_id):
    db = get_db()
    with db.transaction():
        db.execute("DELETE FROM materials WHERE id=%s", (material_id,))


def seed_demo():
    db = get_db()
    examples = [
        ("sql-join", "sql", "note", "Как работает LEFT JOIN", "LEFT JOIN сохраняет все строки левой таблицы. Если совпадения справа нет, её столбцы будут NULL.\n\nSELECT users.name, orders.id\nFROM users\nLEFT JOIN orders ON orders.user_id = users.id;", ""),
        ("python-list", "python", "question", "Чем список отличается от кортежа?", "В каких случаях стоит выбрать list, а в каких — tuple?", "Список изменяемый: элементы можно добавлять, удалять и заменять. Кортеж неизменяемый. Кортеж можно использовать как ключ словаря, если все его элементы хешируемы."),
        ("ml-split", "ml", "note", "Зачем разделять данные на train и test", "Обучающая выборка нужна для настройки параметров модели. Тестовая — для финальной оценки на данных, которые модель не видела.\n\nПодбирайте гиперпараметры на валидационной выборке или с помощью кросс-валидации. Не используйте test для выбора модели.", ""),
    ]
    with db.transaction():
        for example in examples:
            db.execute("INSERT INTO materials (seed_key, branch, kind, title, content, answer) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (seed_key) DO NOTHING", example)
