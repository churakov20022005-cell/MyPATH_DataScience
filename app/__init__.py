import os
import secrets
from datetime import timedelta

import click
from dotenv import load_dotenv
from flask import Flask, abort, render_template, request, session
from werkzeug.security import generate_password_hash


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        DATABASE_URL=os.getenv("DATABASE_URL"),
        ADMIN_PASSWORD_HASH=os.getenv("ADMIN_PASSWORD_HASH", ""),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    from . import models
    from .controllers import bp

    app.register_blueprint(bp)
    app.teardown_appcontext(models.close_db)

    from .richtext import render_content
    app.jinja_env.filters["render_content"] = render_content

    @app.before_request
    def verify_csrf():
        # Styles and scripts must remain available on configuration error pages.
        if request.endpoint == "static":
            return None
        if not app.secret_key or app.secret_key.startswith("replace-"):
            return render_template("error.html", title="Нужна настройка", message="Задайте SECRET_KEY в переменных окружения сервера (на Render: Environment) или в локальном .env, затем перезапустите приложение."), 503
        if request.method == "POST":
            expected = session.get("csrf_token", "")
            provided = request.form.get("csrf_token", "")
            if not expected or not secrets.compare_digest(expected, provided):
                abort(400, description="Форма устарела. Обновите страницу и повторите действие.")

    @app.context_processor
    def template_context():
        if app.secret_key and "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(32)
        return {"csrf_token": session.get("csrf_token", ""), "branches": models.BRANCHES, "sections": models.SECTIONS}

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def page_error(error):
        messages = {404: "Такой страницы нет. Вернитесь к направлениям обучения.", 413: "Материал слишком большой. Сократите текст."}
        return render_template("error.html", title=f"Ошибка {error.code}", message=messages.get(error.code, error.description)), error.code

    @app.errorhandler(models.psycopg.Error)
    def database_error(error):
        app.logger.error("Database request failed: %s", type(error).__name__)
        return render_template("error.html", title="База пока недоступна", message="Проверьте подключение к PostgreSQL и выполните команду init-db из инструкции."), 503

    @app.cli.command("init-db")
    def init_db():
        """Create tables without dropping existing materials."""
        models.init_db()
        click.echo("Таблицы PostgreSQL готовы. Существующие материалы сохранены.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add optional example materials once."""
        models.seed_demo()
        click.echo("Примеры добавлены. Повторный запуск не создаёт дубликаты.")

    @app.cli.command("password-hash")
    @click.password_option(confirmation_prompt=True)
    def password_hash(password):
        """Generate ADMIN_PASSWORD_HASH without needing a database."""
        if len(password) < 12:
            raise click.ClickException("Используйте пароль длиной от 12 символов.")
        click.echo(generate_password_hash(password))

    return app
