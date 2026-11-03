from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured


def parse_database_url(url):
    """Turn a DATABASE_URL such as postgresql://user:pass@host/dbname into Django settings."""
    parsed = urlparse(url)

    if parsed.scheme not in ("postgres", "postgresql"):
        raise ImproperlyConfigured(
            "DATABASE_URL must start with postgresql:// or postgres://"
        )

    name = parsed.path.lstrip("/")
    if not parsed.hostname or not name:
        raise ImproperlyConfigured(
            "DATABASE_URL must include a host name and a database name."
        )

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname,
        "PORT": parsed.port or 5432,
        # Hosted databases require an encrypted connection.
        "OPTIONS": {"sslmode": "require"},
        # Needed when the database sits behind a connection pooler (as Neon does).
        "DISABLE_SERVER_SIDE_CURSORS": True,
        # Serverless functions should not keep connections open between requests.
        "CONN_MAX_AGE": 0,
    }