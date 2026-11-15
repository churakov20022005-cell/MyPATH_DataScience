from io import BytesIO
import unittest
from unittest.mock import patch
from uuid import uuid4

from PIL import Image

from app import create_app, models
from app.richtext import sanitize_html, validate_image, has_content, image_ids


class RichTextTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-richtext'})
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['owner'] = True
            session['csrf_token'] = 'test-csrf'

    def image_data(self):
        stream = BytesIO()
        Image.new('RGB', (5, 5), 'white').save(stream, format='PNG')
        return stream.getvalue()

    def test_sanitizer_preserves_features_and_rejects_active_content(self):
        image_id = str(uuid4())
        html = f'''<h2>SQL</h2><p style="text-align:center;color:red" onclick="bad()"><strong>Текст</strong><mark>Пометка</mark><a href="javascript:bad()">Ссылка</a></p><pre><code class="language-sql">SELECT &lt; 10;</code></pre><table><tbody><tr><td>Ячейка</td></tr></tbody></table><img src="/images/{image_id}" onerror="bad()"><img src="https://tracker.test/a"><iframe src="https://bad.test"></iframe><script>bad()</script>'''
        result = sanitize_html(html)
        self.assertIn('<strong>Текст</strong>', result)
        self.assertIn('<mark>Пометка</mark>', result)
        self.assertIn('language-sql', result)
        self.assertIn('<table>', result)
        self.assertIn('text-align:center', result)
        for forbidden in ('onclick', 'onerror', 'javascript:', '<script', '<iframe', 'tracker.test', 'color:red'):
            self.assertNotIn(forbidden, result)
        self.assertEqual(image_ids(result), {image_id})

    def test_empty_html_is_not_a_note(self):
        self.assertFalse(has_content('<p><br></p>'))
        self.assertTrue(has_content('<p><strong>Text</strong></p>'))
        self.assertTrue(has_content(f'<img src="/images/{uuid4()}">'))

    def test_image_validation_uses_actual_bytes(self):
        self.assertEqual(validate_image(self.image_data()), 'image/png')
        for bad in (b'<svg onload="bad()"></svg>', b'fake PNG', b'x' * (5 * 1024 * 1024 + 1)):
            with self.assertRaises(ValueError):
                validate_image(bad)

    def test_upload_requires_authentication_and_csrf(self):
        with patch.object(models, 'save_image') as save:
            self.assertEqual(self.client.post('/images/upload', data={'image': (BytesIO(self.image_data()), 'photo.png')}).status_code, 400)
            with self.client.session_transaction() as session:
                session.pop('owner')
            response = self.client.post('/images/upload', data={'csrf_token': 'test-csrf', 'image': (BytesIO(self.image_data()), 'photo.png')})
            self.assertEqual(response.status_code, 401)
            save.assert_not_called()

    def test_upload_and_image_response(self):
        image_id = str(uuid4())
        with patch.object(models, 'save_image', return_value=image_id) as save:
            response = self.client.post('/images/upload', data={'csrf_token': 'test-csrf', 'image': (BytesIO(self.image_data()), 'photo.png')})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json['url'], f'/images/{image_id}')
            self.assertEqual(save.call_args.args[1], 'image/png')
        with patch.object(models, 'get_image', return_value={'data': self.image_data(), 'mime_type': 'image/png'}):
            response = self.client.get(f'/images/{image_id}')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content_type, 'image/png')
            self.assertEqual(response.data, self.image_data())
            self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        with patch.object(models, 'get_image', return_value=None):
            self.assertEqual(self.client.get(f'/images/{image_id}').status_code, 404)

    def test_rich_form_is_sanitized_before_save(self):
        data = {'csrf_token': 'test-csrf', 'branch': 'sql', 'section': 'tasks', 'kind': 'note', 'title': 'Rich note', 'content_format': 'html', 'content': '<p onclick="bad()"><strong>Hello</strong></p>', 'answer': ''}
        with patch.object(models, 'save_material', return_value=3) as save:
            self.assertEqual(self.client.post('/materials/new', data=data).status_code, 302)
            self.assertEqual(save.call_args.args[0]['content'], '<p><strong>Hello</strong></p>')
            self.assertEqual(save.call_args.args[0]['content_format'], 'html')
        data['content'] = '<p><br></p>'
        with patch.object(models, 'save_material') as save:
            self.assertEqual(self.client.post('/materials/new', data=data).status_code, 422)
            save.assert_not_called()
