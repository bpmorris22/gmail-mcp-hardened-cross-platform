import asyncio
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ServerToolSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config_path = ROOT / "config.json"
        cls.credentials_path = ROOT / "credentials"
        cls.created_config = not cls.config_path.exists()
        cls.created_credentials = not cls.credentials_path.exists()
        if cls.created_config:
            shutil.copyfile(ROOT / "config.json.example", cls.config_path)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.created_config and cls.config_path.exists():
            cls.config_path.unlink()
        if cls.created_credentials and cls.credentials_path.exists():
            shutil.rmtree(cls.credentials_path)

    def test_tool_surface_loads_without_google_calls(self) -> None:
        import auth
        import server

        tools = asyncio.run(server.list_tools())
        names = {tool.name for tool in tools}
        required = {
            "list_accounts",
            "gmail_search",
            "gmail_send",
            "gmail_download_attachment",
            "calendar_list_calendars",
            "calendar_list_events",
        }
        self.assertTrue(required.issubset(names))
        self.assertFalse(any("drive" in name.lower() for name in names))
        self.assertFalse(any("drive" in scope.lower() for scope in auth.SCOPES))
        self.assertEqual(
            auth.SCOPES,
            [
                "https://www.googleapis.com/auth/gmail.modify",
                "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                "https://www.googleapis.com/auth/calendar.events.readonly",
            ],
        )

    def test_download_subdirectory_can_be_created_under_new_allowed_root(self) -> None:
        import server

        with tempfile.TemporaryDirectory() as temp_dir:
            downloads = Path(temp_dir) / "Downloads"
            destination = downloads / "gmail"
            with patch.object(server, "_ATTACHMENT_ROOTS", [downloads]):
                result = server._validate_save_dir(str(destination))
            self.assertEqual(result, destination.resolve())
            self.assertTrue(destination.is_dir())

    def test_calendar_names_are_marked_as_untrusted(self) -> None:
        import server

        class CalendarStub:
            def list_calendars(self):
                return [{"summary": "content outside the user's control"}]

        with patch.object(server, "_get_calendar", return_value=CalendarStub()):
            output = asyncio.run(
                server.call_tool("calendar_list_calendars", {"account": "personal"})
            )
        payload = json.loads(output[0].text)
        self.assertIn("_warning", payload)
        self.assertEqual(payload["data"][0]["summary"], "content outside the user's control")

    def test_credentials_cannot_be_attached_from_allowed_directory(self) -> None:
        import server

        with tempfile.TemporaryDirectory() as temp_dir:
            documents = Path(temp_dir) / "Documents"
            credential_dir = documents / "gmail-mcp" / "credentials"
            credential_dir.mkdir(parents=True)
            secret = credential_dir / "personal.json"
            secret.write_text("secret", encoding="utf-8")
            with (
                patch.object(server, "_ATTACHMENT_ROOTS", [documents]),
                patch.object(server, "_credentials_dir", credential_dir),
            ):
                with self.assertRaisesRegex(ValueError, "credentials directory"):
                    server._validate_attachment_read_path(str(secret))

    def test_configured_client_secret_cannot_be_attached_from_another_directory(self) -> None:
        import server

        with tempfile.TemporaryDirectory() as temp_dir:
            documents = Path(temp_dir) / "Documents"
            documents.mkdir()
            secret = documents / "oauth-client.json"
            secret.write_text("secret", encoding="utf-8")
            with (
                patch.object(server, "_ATTACHMENT_ROOTS", [documents]),
                patch.object(server, "_credentials_dir", Path(temp_dir) / "elsewhere"),
                patch.object(server, "_client_secret_paths", {secret.resolve()}),
            ):
                with self.assertRaisesRegex(ValueError, "OAuth client-secret"):
                    server._validate_attachment_read_path(str(secret))

    def test_retained_mac_send_requires_preview_token_before_execution(self) -> None:
        import server

        class GmailStub:
            sent = None

            def send_message(self, **kwargs):
                self.sent = kwargs
                return {"id": "message-1", "threadId": "thread-1"}

        args = {
            "account": "personal",
            "to": "recipient@example.test",
            "subject": "Reviewed subject",
            "body": "Reviewed body",
        }
        svc = GmailStub()
        with (
            patch.object(server, "_accounts", {"personal": {"email": "sender@example.test"}}),
            patch.object(server, "_get_service", return_value=svc),
        ):
            rejected = asyncio.run(server.call_tool("gmail_send", {**args, "confirm": True}))
            self.assertIn("confirmation_token", rejected[0].text)
            self.assertIsNone(svc.sent)

            preview = asyncio.run(server.call_tool("gmail_send", args))
            preview_payload = json.loads(preview[0].text)
            self.assertEqual(preview_payload["status"], "preview_only — NOT executed")
            self.assertIsNone(svc.sent)

            sent = asyncio.run(
                server.call_tool(
                    "gmail_send",
                    {
                        **args,
                        "confirm": True,
                        "confirmation_token": preview_payload["confirmation_token"],
                    },
                )
            )
        sent_payload = json.loads(sent[0].text)
        self.assertEqual(sent_payload["status"], "sent")
        self.assertEqual(svc.sent["to"], args["to"])

    def test_draft_write_requires_preview_token(self) -> None:
        import server

        class GmailStub:
            draft = None

            def create_draft(self, **kwargs):
                self.draft = kwargs
                return {"id": "draft-1"}

        args = {
            "account": "personal",
            "to": "recipient@example.test",
            "subject": "Draft subject",
            "body": "Draft body",
        }
        svc = GmailStub()
        with (
            patch.object(server, "_accounts", {"personal": {"email": "sender@example.test"}}),
            patch.object(server, "_get_service", return_value=svc),
        ):
            preview = asyncio.run(server.call_tool("gmail_create_draft", args))
            token = json.loads(preview[0].text)["confirmation_token"]
            self.assertIsNone(svc.draft)
            result = asyncio.run(
                server.call_tool(
                    "gmail_create_draft",
                    {**args, "confirm": True, "confirmation_token": token},
                )
            )
        self.assertEqual(json.loads(result[0].text)["status"], "draft created")
        self.assertEqual(svc.draft["subject"], args["subject"])

    def test_download_does_not_write_until_preview_is_confirmed(self) -> None:
        import server

        class GmailStub:
            reads = 0

            def get_attachment(self, message_id, attachment_id):
                self.reads += 1
                return b"attachment-bytes"

        svc = GmailStub()
        with tempfile.TemporaryDirectory() as temp_dir:
            downloads = Path(temp_dir) / "Downloads"
            args = {
                "account": "personal",
                "message_id": "message-1",
                "attachment_id": "attachment-1",
                "filename": "attachment.txt",
                "save_dir": str(downloads),
            }
            with (
                patch.object(server, "_accounts", {"personal": {"email": "sender@example.test"}}),
                patch.object(server, "_ATTACHMENT_ROOTS", [downloads]),
                patch.object(server, "_get_service", return_value=svc),
            ):
                preview = asyncio.run(server.call_tool("gmail_download_attachment", args))
                token = json.loads(preview[0].text)["confirmation_token"]
                self.assertFalse(downloads.exists())
                self.assertEqual(svc.reads, 0)
                result = asyncio.run(
                    server.call_tool(
                        "gmail_download_attachment",
                        {**args, "confirm": True, "confirmation_token": token},
                    )
                )
            saved_to = Path(json.loads(result[0].text)["saved_to"])
            self.assertEqual(saved_to.read_bytes(), b"attachment-bytes")
            self.assertEqual(svc.reads, 1)


if __name__ == "__main__":
    unittest.main()
