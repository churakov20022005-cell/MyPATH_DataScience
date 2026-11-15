import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app, models


class WebTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-only-secret", "ADMIN_PASSWORD_HASH": generate_password_hash("test-password-123")})
        self.client = self.app.test_client()
        self.material = {"id": 1, "branch": "sql", "section": "books", "kind": "question", "title": "JOIN <script>alert(1)</script>", "content": "SELECT *\nFROM users;", "answer": "NULL", "updated_at": datetime.now(timezone.utc)}

    def token(self, owner=False):
        with self.client.session_transaction() as session:
            session["csrf_token"] = "test-csrf"
            if owner:
                session["owner"] = True
        return "test-csrf"

    def test_home_and_empty_state(self):
        counts = {key: {"note": 0, "question": 0} for key in models.BRANCHES}
        with patch.object(models, "overview", return_value=(counts, [])):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Здесь начинается ваша коллекция", response.text)
        for branch in models.BRANCHES:
            self.assertIn(f'/branch/{branch}', response.text)

    def test_static_files_available_when_secret_is_missing_or_placeholder(self):
        for secret in (None, "", "replace-with-random-secret"):
            with self.subTest(secret=secret):
                app = create_app({"TESTING": True, "SECRET_KEY": secret})
                client = app.test_client()
                with patch.object(models, "overview") as overview:
                    page = client.get("/")
                    self.assertEqual(page.status_code, 503)
                    self.assertIn("Render: Environment", page.text)
                    overview.assert_not_called()
                for path, content_type in (("/static/style.css", "text/css"), ("/static/app.js", "javascript")):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(content_type, response.content_type)
                    self.assertNotIn("Нужна настройка", response.get_data(as_text=True))
                    response.close()

    def test_branch_filter_and_search(self):
        with patch.object(models, "list_materials", return_value=[self.material]) as listing:
            response = self.client.get("/branch/sql/section/books?kind=question&q=JOIN")
        self.assertEqual(response.status_code, 200)
        listing.assert_called_once_with("sql", "question", "JOIN", "books")
        self.assertIn("&lt;script&gt;", response.text)
        self.assertNotIn("<script>alert", response.text)

    def test_branch_shows_sections_and_preserves_legacy_access(self):
        counts = {"yandex": 2, "books": 1, "tasks": 0, "": 3}
        with patch.object(models, "section_counts", return_value=counts):
            for branch in models.BRANCHES:
                response = self.client.get(f"/branch/{branch}")
                self.assertEqual(response.status_code, 200)
                for section in models.SECTIONS:
                    self.assertIn(f'/branch/{branch}/section/{section}', response.text)
                self.assertIn("Без раздела", response.text)
                self.assertIn("Все материалы", response.text)

    def test_section_validation_and_legacy_search(self):
        self.assertEqual(self.client.get("/branch/sql/section/unknown").status_code, 404)
        with patch.object(models, "list_materials", return_value=[]) as listing:
            self.assertEqual(self.client.get("/branch/sql/section/uncategorized").status_code, 200)
            listing.assert_called_once_with("sql", "", "", "")
        response = self.client.get("/branch/sql?q=JOIN")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/section/all", response.location)

    def test_section_preselected_in_new_form_and_required_on_save(self):
        token = self.token(owner=True)
        response = self.client.get("/materials/new?branch=sql&section=tasks")
        self.assertEqual(response.status_code, 200)
        self.assertIn('value="tasks" selected', response.text)
        data = {"csrf_token": token, "branch": "sql", "section": "invalid", "kind": "note", "title": "test", "content": "test"}
        with patch.object(models, "save_material") as save:
            self.assertEqual(self.client.post("/materials/new", data=data).status_code, 422)
            save.assert_not_called()

    def test_detail_answer_and_escaping(self):
        with patch.object(models, "get_material", return_value=self.material):
            response = self.client.get("/materials/1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Показать ответ", response.text)
        self.assertNotIn("<script>alert", response.text)

    def test_owner_forms_render(self):
        self.token(owner=True)
        self.assertEqual(self.client.get("/materials/new").status_code, 200)
        with patch.object(models, "get_material", return_value=self.material):
            response = self.client.get("/materials/1/edit")
        self.assertEqual(response.status_code, 200)
        self.assertIn("NULL", response.text)

    def test_unauthenticated_mutations_are_blocked(self):
        token = self.token()
        with patch.object(models, "save_material") as save, patch.object(models, "delete_material") as delete:
            self.assertEqual(self.client.post("/materials/new", data={"csrf_token": token}).status_code, 302)
            self.assertEqual(self.client.post("/materials/1/delete", data={"csrf_token": token}).status_code, 302)
            save.assert_not_called()
            delete.assert_not_called()

    def test_csrf_required_even_for_owner(self):
        self.token(owner=True)
        with patch.object(models, "save_material") as save:
            self.assertEqual(self.client.post("/materials/new", data={"title": "test"}).status_code, 400)
            save.assert_not_called()

    def test_login_and_logout(self):
        token = self.token()
        response = self.client.post("/login", data={"csrf_token": token, "password": "wrong"})
        self.assertEqual(response.status_code, 401)
        response = self.client.post("/login", data={"csrf_token": token, "password": "test-password-123"})
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertTrue(session["owner"])
            self.assertNotIn("csrf_token", session)
        token = self.token()
        self.assertEqual(self.client.post("/logout", data={"csrf_token": token}).status_code, 302)
        self.assertEqual(self.client.get("/materials/new").status_code, 302)

    def test_validation_preserves_text(self):
        token = self.token(owner=True)
        with patch.object(models, "save_material") as save:
            response = self.client.post("/materials/new", data={"csrf_token": token, "branch": "bad", "kind": "bad", "title": "", "content": "my draft", "answer": ""})
        self.assertEqual(response.status_code, 422)
        self.assertIn("my draft", response.text)
        save.assert_not_called()

    def test_create_and_edit(self):
        token = self.token(owner=True)
        data = {"csrf_token": token, "branch": "python", "section": "yandex", "kind": "note", "title": " Lists ", "content": "text", "answer": "not for a note"}
        with patch.object(models, "save_material", return_value=9) as save:
            response = self.client.post("/materials/new", data=data)
        self.assertEqual(response.location, "/materials/9")
        self.assertEqual(save.call_args.args[0]["title"], "Lists")
        self.assertEqual(save.call_args.args[0]["answer"], "")
        with patch.object(models, "get_material", return_value=self.material), patch.object(models, "save_material", return_value=1) as save:
            self.assertEqual(self.client.post("/materials/1/edit", data=data).status_code, 302)
            self.assertEqual(save.call_args.args[1], 1)

    def test_delete(self):
        token = self.token(owner=True)
        with patch.object(models, "get_material", return_value=self.material), patch.object(models, "delete_material") as delete:
            response = self.client.post("/materials/1/delete", data={"csrf_token": token})
        self.assertEqual(response.location, "/branch/sql/section/books")
        delete.assert_called_once_with(1)

    def test_errors(self):
        self.assertEqual(self.client.get("/branch/unknown").status_code, 404)
        self.assertEqual(self.client.get("/branch/sql/section/all?kind=wrong").status_code, 400)
        with patch.object(models, "get_material", return_value=None):
            self.assertEqual(self.client.get("/materials/999").status_code, 404)
        with patch.object(models, "overview", side_effect=models.psycopg.OperationalError("internal secret")):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("internal secret", response.text)


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL to run real PostgreSQL integration tests")
class PostgresTests(unittest.TestCase):
    def test_postgres_lifecycle(self):
        import uuid
        from psycopg import sql
        from psycopg.conninfo import make_conninfo

        schema = "test_" + uuid.uuid4().hex
        url = os.environ["TEST_DATABASE_URL"]
        with models.psycopg.connect(url, autocommit=True) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            try:
                app = create_app({"TESTING": True, "SECRET_KEY": "test", "DATABASE_URL": make_conninfo(url, options=f"-csearch_path={schema}")})
                with app.app_context():
                    # Simulate the old schema and an existing record before migration.
                    models.get_db().execute(Path(models.__file__).with_name('schema.sql').read_text(encoding='utf-8'))
                    legacy_id = models.get_db().execute("INSERT INTO materials (branch,kind,title,content) VALUES ('sql','note','Legacy','Keep this text') RETURNING id").fetchone()["id"]
                    models.init_db()
                    models.init_db()
                    legacy = models.get_material(legacy_id)
                    self.assertEqual(legacy["section"], "")
                    self.assertEqual(legacy["content"], "Keep this text")
                    self.assertEqual(legacy["content_format"], "text")
                    self.assertEqual(models.section_counts("sql")[""], 1)
                    self.assertEqual(len(models.list_materials("sql", section="")), 1)
                    legacy["section"] = "books"
                    models.save_material(legacy, legacy_id)
                    self.assertEqual(models.section_counts("sql")["books"], 1)
                    self.assertEqual(len(models.list_materials("sql", section="books")), 1)
                    self.assertEqual(models.list_materials("sql", section="tasks"), [])
                    models.delete_material(legacy_id)
                    # Real image bytes and links persist and can be reused in rich notes.
                    from io import BytesIO
                    from PIL import Image
                    stream = BytesIO()
                    Image.new('RGB', (2, 2), 'white').save(stream, format='PNG')
                    image_id = models.save_image(stream.getvalue(), 'image/png')
                    self.assertEqual(bytes(models.get_image(image_id)['data']), stream.getvalue())
                    rich = {'branch': 'sql', 'section': 'tasks', 'kind': 'note', 'title': 'Rich', 'content': f'<p><strong>Rich</strong></p><img src="/images/{image_id}">', 'answer': '', 'content_format': 'html'}
                    rich_id = models.save_material(rich)
                    self.assertEqual(models.get_material(rich_id)['content_format'], 'html')
                    self.assertEqual(models.get_db().execute('SELECT count(*) AS total FROM material_images WHERE material_id=%s', (rich_id,)).fetchone()['total'], 1)
                    models.delete_material(rich_id)
                    self.assertEqual(models.get_db().execute('SELECT count(*) AS total FROM material_images WHERE material_id=%s', (rich_id,)).fetchone()['total'], 0)
                    counts, recent = models.overview()
                    self.assertEqual(recent, [])
                    item = {"branch": "sql", "section": "tasks", "kind": "question", "title": "Оконные функции", "content": "row_number()\nSELECT '100%';", "answer": "Нумерация"}
                    material_id = models.save_material(item)
                    self.assertEqual(models.get_material(material_id)["content"], item["content"])
                    self.assertEqual(len(models.list_materials("sql", "question", "ОКОННЫЕ")), 1)
                    self.assertEqual(len(models.list_materials("sql", "", "%")), 1)
                    self.assertEqual(models.list_materials("sql", "", "' OR 1=1 --"), [])
                    self.assertEqual(models.list_materials("python"), [])
                    item.update(branch="python", title="Новый заголовок")
                    models.save_material(item, material_id)
                    self.assertEqual(models.get_material(material_id)["branch"], "python")
                    models.delete_material(material_id)
                    self.assertIsNone(models.get_material(material_id))
                    models.seed_demo()
                    models.seed_demo()
                    counts, recent = models.overview()
                    self.assertEqual(sum(sum(c.values()) for c in counts.values()), 3)
                    self.assertEqual(len(recent), 3)
                    # A new app context creates a new connection: records survive reconnects.
                with app.app_context():
                    self.assertEqual(len(models.overview()[1]), 3)
            finally:
                db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
