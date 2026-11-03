from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.db import parse_database_url

NEON_STYLE_URL = (
    "postgresql://appuser:s3cret@ep-cool-123-pooler.us-east-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


class ParseDatabaseUrlTests(SimpleTestCase):
    def test_neon_style_url_is_split_into_its_parts(self):
        settings = parse_database_url(NEON_STYLE_URL)
        self.assertEqual(settings["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(settings["NAME"], "neondb")
        self.assertEqual(settings["USER"], "appuser")
        self.assertEqual(settings["PASSWORD"], "s3cret")
        self.assertEqual(settings["HOST"], "ep-cool-123-pooler.us-east-2.aws.neon.tech")

    def test_default_port_is_5432(self):
        self.assertEqual(parse_database_url(NEON_STYLE_URL)["PORT"], 5432)

    def test_explicit_port_is_used(self):
        url = "postgresql://appuser:s3cret@db.example.com:6543/neondb"
        self.assertEqual(parse_database_url(url)["PORT"], 6543)

    def test_special_characters_in_the_password_are_decoded(self):
        url = "postgresql://appuser:p%40ss%2Fword%23@db.example.com/neondb"
        self.assertEqual(parse_database_url(url)["PASSWORD"], "p@ss/word#")

    def test_postgres_scheme_is_accepted(self):
        url = "postgres://appuser:s3cret@db.example.com/neondb"
        self.assertEqual(parse_database_url(url)["NAME"], "neondb")

    def test_ssl_is_required_and_server_side_cursors_are_disabled(self):
        settings = parse_database_url(NEON_STYLE_URL)
        self.assertEqual(settings["OPTIONS"], {"sslmode": "require"})
        self.assertTrue(settings["DISABLE_SERVER_SIDE_CURSORS"])
        self.assertEqual(settings["CONN_MAX_AGE"], 0)

    def test_other_database_types_are_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_database_url("mysql://appuser:s3cret@db.example.com/neondb")

    def test_missing_database_name_is_rejected(self):
        for url in (
            "postgresql://appuser:s3cret@db.example.com",
            "postgresql://appuser:s3cret@db.example.com/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(ImproperlyConfigured):
                    parse_database_url(url)

    def test_missing_host_is_rejected(self):
        with self.assertRaises(ImproperlyConfigured):
            parse_database_url("postgresql:///neondb")