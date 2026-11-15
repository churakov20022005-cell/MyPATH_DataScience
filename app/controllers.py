from functools import wraps

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from . import models

bp = Blueprint("main", __name__)


def owner_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("owner"):
            return redirect(url_for("main.login"))
        return view(*args, **kwargs)
    return wrapped


def find_material(material_id):
    material = models.get_material(material_id)
    if not material:
        abort(404)
    return material


@bp.get("/")
def home():
    counts, recent = models.overview()
    return render_template("home.html", counts=counts, recent=recent, total=sum(sum(c.values()) for c in counts.values()))


@bp.get("/branch/<branch>")
def branch(branch):
    if branch not in models.BRANCHES:
        abort(404)
    if request.args.get("kind") or request.args.get("q"):
        return redirect(url_for("main.section", branch=branch, section="all", kind=request.args.get("kind", ""), q=request.args.get("q", "")))
    return render_template("branch.html", branch=branch, info=models.BRANCHES[branch], counts=models.section_counts(branch))


@bp.get("/branch/<branch>/section/<section>")
def section(branch, section):
    if branch not in models.BRANCHES or section not in (*models.SECTIONS, "all", "uncategorized"):
        abort(404)
    selected = None if section == "all" else "" if section == "uncategorized" else section
    title = "Все материалы" if section == "all" else "Без раздела" if section == "uncategorized" else models.SECTIONS[section]["title"]
    kind, query = request.args.get("kind", ""), request.args.get("q", "").strip()
    if kind not in ("", "note", "question") or len(query) > 200:
        abort(400)
    return render_template("section.html", branch=branch, info=models.BRANCHES[branch], section=section, section_title=title, kind=kind, query=query, materials=models.list_materials(branch, kind, query, selected))


@bp.get("/materials/<int:material_id>")
def detail(material_id):
    return render_template("detail.html", material=find_material(material_id))


@bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        stored = current_app.config["ADMIN_PASSWORD_HASH"]
        if stored and not stored.startswith("replace-") and check_password_hash(stored, request.form.get("password", "")):
            session.clear()
            session["owner"] = True
            session.permanent = True
            flash("Вы вошли как владелец. Можно добавлять и редактировать материалы.")
            return redirect(url_for("main.home"))
        error = "Неверный пароль или вход владельца ещё не настроен."
    return render_template("login.html", error=error), 401 if error else 200


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.home"))


@bp.route("/materials/new", methods=["GET", "POST"])
@bp.route("/materials/<int:material_id>/edit", methods=["GET", "POST"])
@owner_required
def editor(material_id=None):
    existing = find_material(material_id) if material_id else None
    data = dict(existing) if existing else {"branch": request.args.get("branch", "sql"), "section": request.args.get("section", "yandex"), "kind": "note", "title": "", "content": "", "answer": ""}
    errors = []
    if request.method == "POST":
        data = {key: request.form.get(key, "").strip() for key in ("branch", "section", "kind", "title", "content", "answer")}
        if data["branch"] not in models.BRANCHES:
            errors.append("Выберите направление SQL, Python или ML.")
        if data["kind"] not in ("note", "question"):
            errors.append("Выберите тип материала.")
        if data["section"] not in models.SECTIONS and not (existing and data["section"] == ""):
            errors.append("Выберите подраздел: ЯндексПрактикум, книги или решение задач.")
        if not 1 <= len(data["title"]) <= 180:
            errors.append("Заголовок должен содержать от 1 до 180 символов.")
        if not 1 <= len(data["content"]) <= 100000:
            errors.append("Основной текст должен содержать от 1 до 100 000 символов.")
        if len(data["answer"]) > 100000:
            errors.append("Ответ должен быть не длиннее 100 000 символов.")
        if data["kind"] == "note":
            data["answer"] = ""
        if not errors:
            saved_id = models.save_material(data, material_id)
            if saved_id is None:
                abort(404)
            flash("Материал сохранён.")
            return redirect(url_for("main.detail", material_id=saved_id))
    return render_template("editor.html", data=data, errors=errors, editing=existing is not None), 422 if errors else 200


@bp.post("/materials/<int:material_id>/delete")
@owner_required
def delete(material_id):
    material = find_material(material_id)
    models.delete_material(material_id)
    flash("Материал удалён.")
    return redirect(url_for("main.section", branch=material["branch"], section=material.get("section") or "uncategorized"))
