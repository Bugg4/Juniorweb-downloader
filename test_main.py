import json
import os
import tempfile
import unittest
from unittest.mock import patch


for variable in ("COMPANY", "USERNAME", "PASSWORD", "NTFY_TOPIC"):
    os.environ[variable] = "test-value"

import main


class FakeTitle:
    def __init__(self, text):
        self.text = text


class FakeHtml:
    def __init__(self, text="", anchors=None, title=""):
        self.text = text
        self.anchors = anchors or []
        self.title = title

    def find(self, selector, first=False):
        if selector == "a":
            return self.anchors
        if selector == "title" and first:
            return FakeTitle(self.title) if self.title else None
        return []


class FakeResponse:
    def __init__(self, url, text="", anchors=None, title=""):
        self.url = url
        self.status_code = 200
        self.text = text
        self.content = text.encode()
        self.html = FakeHtml(text, anchors, title)

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.cookies = {"csrfp_token": "test-token"}

    def get(self, url):
        return FakeResponse(url)

    def post(self, url, **kwargs):
        return self.response


class FakeAnchor:
    def __init__(self, text, href, **attrs):
        self.text = text
        self.attrs = {"href": href, **attrs}


class MainTests(unittest.TestCase):
    def test_login_rejects_mandatory_password_change_page(self):
        response = FakeResponse(
            "https://juniorweb.example.it/juniorweb/cambiapsw.php",
            text="Utente test-user Cambio password obbligatorio (360 Giorni)",
            title="JuniorWEB © - Login",
        )

        with patch.object(main, "USERNAME", "test-user"):
            session, logged_in_response = main.login(
                FakeSession(response),
                "https://juniorweb.example.it/juniorweb/index.php",
                {},
                {},
            )

        self.assertIsNone(session)
        self.assertIsNone(logged_in_response)

    def test_extract_live_files_accepts_pdf_filename_in_href(self):
        response = FakeResponse(
            "https://juniorweb.example.it/juniorweb/index.php",
            anchors=[
                FakeAnchor("Download", "files/payroll.pdf"),
                FakeAnchor("Download", "files/payroll.pdf"),
                FakeAnchor("Not a PDF", "files/readme.txt"),
            ],
        )

        files = main.extract_live_files(response)

        self.assertEqual(
            files,
            [
                {
                    "file_name": "payroll.pdf",
                    "file_url": "https://juniorweb.test-value.it/juniorweb/files/payroll.pdf",
                    "is_sent": False,
                }
            ],
        )

    def test_save_file_list_refuses_empty_response_and_writes_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "file_list.json")
            with open(file_path, "w") as file:
                file.write("previous data\n")

            with patch.object(main, "FILE_LIST", file_path):
                with self.assertRaises(ValueError):
                    main.save_file_list([])

                with open(file_path) as file:
                    self.assertEqual(file.read(), "previous data\n")

                main.save_file_list(
                    [
                        {
                            "file_name": "payroll.pdf",
                            "file_url": "https://example.test/payroll.pdf",
                            "is_sent": False,
                        }
                    ]
                )

            with open(file_path) as file:
                self.assertEqual(json.load(file)[0]["file_name"], "payroll.pdf")
            self.assertFalse(os.path.exists(f"{file_path}.tmp"))


if __name__ == "__main__":
    unittest.main()
