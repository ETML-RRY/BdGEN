import os
import shutil
import unittest
from pathlib import Path

from bdgen import secret_store


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(__file__).parent / "_tmp_secret_store"
        if self.tmp.exists():
            shutil.rmtree(self.tmp)
        self.tmp.mkdir()
        self.old_root = os.environ.get("BDGEN_CONFIG_ROOT")
        self.old_openai = os.environ.get("OPENAI_API_KEY")
        os.environ["BDGEN_CONFIG_ROOT"] = str(self.tmp)
        os.environ.pop("OPENAI_API_KEY", None)
        secret_store.lock_vault()

    def tearDown(self):
        secret_store.lock_vault()
        if self.old_root is None:
            os.environ.pop("BDGEN_CONFIG_ROOT", None)
        else:
            os.environ["BDGEN_CONFIG_ROOT"] = self.old_root
        if self.old_openai is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self.old_openai
        if self.tmp.exists():
            shutil.rmtree(self.tmp)

    def test_create_unlock_and_persist_update(self):
        secret_store.create_vault(
            "correct horse battery staple",
            {"OPENAI_API_KEY": "sk-test"},
        )
        self.assertTrue((self.tmp / secret_store.VAULT_FILENAME).exists())
        self.assertEqual(secret_store.get_secret("OPENAI_API_KEY"), "sk-test")

        secret_store.update_secret("OPENAI_API_KEY", "sk-new")
        secret_store.lock_vault()
        self.assertIsNone(secret_store.get_secret("OPENAI_API_KEY"))

        secret_store.unlock_vault("correct horse battery staple")
        self.assertEqual(secret_store.get_secret("OPENAI_API_KEY"), "sk-new")

    def test_wrong_password_fails(self):
        secret_store.create_vault("good-password", {"OPENAI_API_KEY": "sk-test"})
        secret_store.lock_vault()
        with self.assertRaises(secret_store.VaultError):
            secret_store.unlock_vault("bad-password")


if __name__ == "__main__":
    unittest.main()
