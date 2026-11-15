"""Create local configuration once, without putting credentials in Git."""
from pathlib import Path
import secrets
from werkzeug.security import generate_password_hash

root = Path(__file__).resolve().parent
env = root / ".env"
if env.exists():
    raise SystemExit(".env already exists; no settings were changed.")
db_password = secrets.token_hex(24)
owner_password = secrets.token_urlsafe(18)
env.write_text(
    f"POSTGRES_DB=mypath\nPOSTGRES_USER=mypath\nPOSTGRES_PASSWORD={db_password}\n"
    f"DATABASE_URL=postgresql://mypath:{db_password}@localhost:5432/mypath\n"
    f"SECRET_KEY={secrets.token_hex(32)}\n"
    f"ADMIN_PASSWORD_HASH='{generate_password_hash(owner_password)}'\n"
    "COOKIE_SECURE=false\n",
    encoding="utf-8",
)
(root / ".owner-password.txt").write_text(owner_password + "\n", encoding="utf-8")
print("Created .env and .owner-password.txt (both ignored by Git).")
