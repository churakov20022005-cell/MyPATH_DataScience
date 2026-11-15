"""One HTML allowlist for storage and display; plain legacy text stays escaped."""
import re
from html.parser import HTMLParser
from io import BytesIO
import warnings

import bleach
from bleach.css_sanitizer import CSSSanitizer
from markupsafe import Markup
from PIL import Image, UnidentifiedImageError

IMAGE_PATH = re.compile(r"^/images/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$")
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
TAGS = frozenset('p br strong b em i u s del h1 h2 h3 h4 ul ol li blockquote pre code a img hr mark table thead tbody tr th td input label div span'.split())


def allow_attribute(tag, name, value):
    if name == 'style':
        return tag in ('p', 'h1', 'h2', 'h3', 'h4', 'th', 'td')
    if tag == 'a':
        return name in ('href', 'title')
    if tag == 'img':
        return (name == 'src' and IMAGE_PATH.fullmatch(value) is not None) or name in ('alt', 'title')
    if tag == 'code' and name == 'class':
        return value in ('language-sql', 'language-python', 'language-javascript', 'language-bash', 'language-json', 'language-plaintext')
    if tag in ('ul', 'li') and name == 'data-type':
        return value in ('taskList', 'taskItem')
    if tag == 'li' and name == 'data-checked':
        return value in ('true', 'false')
    if tag == 'input':
        return (name == 'type' and value == 'checkbox') or name in ('checked', 'disabled')
    if tag in ('td', 'th') and name in ('colspan', 'rowspan'):
        return value.isdigit() and 1 <= int(value) <= 30
    if tag == 'ol' and name == 'start':
        return value.isdigit() and len(value) <= 5
    return False


def sanitize_html(value):
    return bleach.clean(value, tags=TAGS, attributes=allow_attribute,
                        protocols={'http', 'https', 'mailto'}, strip=True,
                        css_sanitizer=CSSSanitizer(allowed_css_properties=['text-align']))


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = TextExtractor()
    parser.feed(value)
    return ' '.join(parser.parts).strip()


def has_content(value):
    return bool(plain_text(value) or re.search(r'<img\b[^>]*\bsrc="/images/', value))


def image_ids(value):
    return set(re.findall(r'<img\b[^>]*\bsrc="/images/([0-9a-f-]{36})"', value))


def render_content(value, content_format='text'):
    # Sanitizing again protects rendering even if database contents bypassed a form.
    return Markup(sanitize_html(value)) if content_format == 'html' else value


def validate_image(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Изображение должно быть не больше 5 МБ.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp', 'GIF': 'image/gif'}.get(image.format)
                if not mime:
                    raise ValueError('Поддерживаются PNG, JPEG, WebP и GIF.')
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ValueError('Изображение слишком большое: максимум 20 мегапикселей.')
                image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError('Не удалось прочитать изображение. Выберите другой файл.') from None
    return mime
