import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from deploy import mac


class MacSetupTests(unittest.TestCase):
    def test_only_matching_local_https_tunnel_is_selected(self):
        tunnels = [
            {"url": "https://other.example", "upstream": {"url": "http://localhost:3000"}},
            {"url": "https://console.example", "upstream": {"url": "http://127.0.0.1:8088"}},
        ]
        self.assertEqual(mac.tunnel_url(tunnels, 8088), "https://console.example")
        with self.assertRaises(ValueError):
            mac.tunnel_url(tunnels, 8090)
        with self.assertRaises(ValueError):
            mac.tunnel_url(tunnels + [tunnels[-1]], 8088)

    def test_http_and_credential_bearing_urls_are_rejected(self):
        for url in ("http://console.example", "https://secret@console.example", "https://console.example/api", "https://console.example/?token=x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                mac.public_url(url)

    def test_prepare_preserves_existing_secrets_and_writes_private_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            with patch.object(mac, "postgres_info", return_value=("test-admin", "test-network")):
                first = mac.prepare(path, url="https://console.example")
                values = mac.read_env(path)
                values["DEEPSEEK_API_KEY"] = "test-$-#-'literal"
                values["ADMIN_OPEN_IDS"] = "ou_one, ou_two "
                mac.write_env(path, values)
                second = mac.prepare(path, url="https://changed.example")
            self.assertEqual(first["DATABASE_URL"], second["DATABASE_URL"])
            self.assertEqual(first["AGENT_INTERNAL_TOKEN"], second["AGENT_INTERNAL_TOKEN"])
            self.assertEqual(first["CREDENTIAL_ENCRYPTION_KEY"], second["CREDENTIAL_ENCRYPTION_KEY"])
            self.assertEqual(second["DEEPSEEK_API_KEY"], values["DEEPSEEK_API_KEY"])
            self.assertEqual(second["ADMIN_OPEN_IDS"], "ou_one,ou_two")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_missing_external_credentials_never_initialize_database_or_start_services(self):
        with patch("sys.argv", ["mac.py", "up"]), patch.object(mac, "prepare", return_value={}), \
                patch.object(mac, "ensure_database") as database, patch.object(mac, "compose") as compose:
            with self.assertRaises(ValueError):
                mac.main()
            database.assert_not_called()
            compose.assert_not_called()

    def test_existing_foreign_database_is_not_adopted_or_modified(self):
        values = {"DATABASE_URL": "postgresql+psycopg://rpa_console:test@postgresql:5432/rpa_console", "POSTGRES_CONTAINER": "postgresql"}
        with patch.object(mac, "psql", return_value="another-application") as sql:
            with self.assertRaisesRegex(ValueError, "属于其他角色"):
                mac.ensure_database(values)
            self.assertEqual(sql.call_count, 1)
            self.assertTrue(sql.call_args.args[1].startswith("SELECT "))

    def test_other_database_url_is_not_initialized(self):
        values = {"DATABASE_URL": "postgresql+psycopg://admin:test@postgresql:5432/existing_business", "POSTGRES_CONTAINER": "postgresql"}
        with patch.object(mac, "psql") as sql:
            with self.assertRaises(ValueError):
                mac.ensure_database(values)
            sql.assert_not_called()


if __name__ == "__main__":
    unittest.main()
