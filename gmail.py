import base64
import mimetypes
import os
import re
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# MIME trees in real-world mail rarely nest more than a few levels deep
# (multipart/mixed → multipart/alternative → text). 20 leaves generous
# headroom while preventing a maliciously deep tree from blowing the
# Python recursion limit.
_MAX_MIME_DEPTH = 20

# Gmail caps a single message (including all attachments, base64-encoded) at
# ~25 MB. We surface this as a soft check before the API call so the user
# sees a clear error instead of a generic HttpError from Google.
_MAX_ATTACHMENT_BYTES_TOTAL = 25 * 1024 * 1024


class GmailService:
    def __init__(self, credentials: Credentials, account_name: str = ""):
        self.service = build("gmail", "v1", credentials=credentials)
        self.account_name = account_name

    # ------------------------------------------------------------------ profile

    def get_profile(self) -> Dict[str, Any]:
        return self.service.users().getProfile(userId="me").execute()

    # ------------------------------------------------------------------ search / read

    def search_messages(
        self,
        query: str,
        max_results: int = 20,
        page_token: Optional[str] = None,
        include_body: bool = False,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "userId": "me",
            "q": query,
            "maxResults": min(max_results, 100),
        }
        if page_token:
            params["pageToken"] = page_token

        result = self.service.users().messages().list(**params).execute()
        raw_messages = result.get("messages", [])

        messages = []
        for raw in raw_messages:
            fmt = "full" if include_body else "metadata"
            msg = self._get_raw_message(raw["id"], format=fmt)
            messages.append(self._parse_message(msg))

        return {
            "messages": messages,
            "nextPageToken": result.get("nextPageToken"),
            "resultSizeEstimate": result.get("resultSizeEstimate", 0),
        }

    def get_message(self, message_id: str) -> Dict[str, Any]:
        msg = self._get_raw_message(message_id, format="full")
        return self._parse_message(msg)

    def get_thread(self, thread_id: str) -> Dict[str, Any]:
        thread = self.service.users().threads().get(userId="me", id=thread_id).execute()
        messages = [self._parse_message(m) for m in thread.get("messages", [])]
        return {
            "id": thread["id"],
            "messageCount": len(messages),
            "messages": messages,
        }

    # ------------------------------------------------------------------ send / draft

    def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        attachments: Optional[List[Union[str, Path]]] = None,
    ) -> Dict[str, Any]:
        msg = self._build_message(to, subject, body, cc, bcc, attachments)
        return self.service.users().messages().send(
            userId="me", body={"raw": self._encode(msg)}
        ).execute()

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        attachments: Optional[List[Union[str, Path]]] = None,
    ) -> Dict[str, Any]:
        msg = self._build_message(to, subject, body, cc, bcc, attachments)
        return self.service.users().drafts().create(
            userId="me", body={"message": {"raw": self._encode(msg)}}
        ).execute()

    @staticmethod
    def _build_message(
        to: str,
        subject: str,
        body: str,
        cc: str,
        bcc: str,
        attachments: Optional[List[Union[str, Path]]],
    ) -> Union[MIMEText, MIMEMultipart]:
        """Build a plain-text MIMEText or a multipart message with attachments.

        Path validation is the caller's responsibility (see server._validate_attachment_path).
        We assume each path is a regular file the user is allowed to read.
        """
        if not attachments:
            msg = MIMEText(body, "plain")
            msg["to"] = to
            msg["subject"] = subject
            if cc:
                msg["cc"] = cc
            if bcc:
                msg["bcc"] = bcc
            return msg

        # Multipart path
        msg = MIMEMultipart()
        msg["to"] = to
        msg["subject"] = subject
        if cc:
            msg["cc"] = cc
        if bcc:
            msg["bcc"] = bcc
        msg.attach(MIMEText(body, "plain"))

        total_bytes = 0
        for raw_path in attachments:
            path = Path(raw_path)
            with open(path, "rb") as f:
                data = f.read()
            total_bytes += len(data)
            if total_bytes > _MAX_ATTACHMENT_BYTES_TOTAL:
                raise ValueError(
                    f"Attachments exceed Gmail's ~25 MB per-message limit "
                    f"(running total: {total_bytes} bytes)."
                )
            mime_type, _ = mimetypes.guess_type(str(path))
            if mime_type is None:
                mime_type = "application/octet-stream"
            maintype, _, subtype = mime_type.partition("/")
            part = MIMEBase(maintype, subtype or "octet-stream")
            part.set_payload(data)
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                "attachment",
                filename=os.path.basename(path),
            )
            msg.attach(part)

        return msg

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        """Fetch a single attachment's raw bytes by ID."""
        result = self.service.users().messages().attachments().get(
            userId="me", messageId=message_id, id=attachment_id
        ).execute()
        return base64.urlsafe_b64decode(result["data"].encode())

    def list_drafts(self, max_results: int = 20) -> List[Dict[str, Any]]:
        result = self.service.users().drafts().list(
            userId="me", maxResults=min(max_results, 50)
        ).execute()

        drafts = []
        for draft in result.get("drafts", []):
            details = self.service.users().drafts().get(
                userId="me", id=draft["id"], format="full"
            ).execute()
            msg = self._parse_message(details.get("message", {}))
            msg["draft_id"] = draft["id"]
            drafts.append(msg)

        return drafts

    # ------------------------------------------------------------------ labels

    def list_labels(self) -> List[Dict[str, Any]]:
        result = self.service.users().labels().list(userId="me").execute()
        return [
            {"id": lbl["id"], "name": lbl["name"], "type": lbl.get("type", "")}
            for lbl in result.get("labels", [])
        ]

    def modify_labels(
        self,
        message_id: str,
        add_labels: Optional[List[str]] = None,
        remove_labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels

        return self.service.users().messages().modify(
            userId="me", id=message_id, body=body
        ).execute()

    def trash_message(self, message_id: str) -> Dict[str, Any]:
        return self.service.users().messages().trash(
            userId="me", id=message_id
        ).execute()

    # ------------------------------------------------------------------ internals

    def _get_raw_message(self, message_id: str, format: str = "full") -> Dict[str, Any]:
        return self.service.users().messages().get(
            userId="me", id=message_id, format=format
        ).execute()

    def _parse_message(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        payload = msg.get("payload", {})
        headers: Dict[str, str] = {}
        for h in payload.get("headers", []):
            headers[h["name"].lower()] = h["value"]

        body = self._extract_body(payload)
        attachments = self._extract_attachments(payload)

        return {
            "id": msg.get("id", ""),
            "threadId": msg.get("threadId", ""),
            "labels": msg.get("labelIds", []),
            "snippet": msg.get("snippet", ""),
            "date": headers.get("date", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "cc": headers.get("cc", ""),
            "subject": headers.get("subject", "(no subject)"),
            "body": body,
            "attachments": attachments,
            "has_attachments": bool(attachments),
        }

    def _extract_attachments(
        self,
        payload: Dict[str, Any],
        _depth: int = 0,
        _out: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Walk the MIME tree and collect attachment metadata (no payload bytes)."""
        if _out is None:
            _out = []
        if _depth > _MAX_MIME_DEPTH or not payload:
            return _out

        filename = payload.get("filename", "") or ""
        body = payload.get("body", {}) or {}
        attachment_id = body.get("attachmentId", "")
        if filename and attachment_id:
            _out.append({
                "filename": filename,
                "mimeType": payload.get("mimeType", ""),
                "size": body.get("size", 0),
                "attachment_id": attachment_id,
            })

        for part in payload.get("parts", []) or []:
            self._extract_attachments(part, _depth + 1, _out)

        return _out

    def _extract_body(self, payload: Dict[str, Any], _depth: int = 0) -> str:
        if _depth > _MAX_MIME_DEPTH or not payload:
            return ""

        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data", "")

        if body_data:
            decoded = base64.urlsafe_b64decode(body_data.encode()).decode(
                "utf-8", errors="replace"
            )
            if "html" in mime_type:
                # Strip script/style block contents and HTML comments FIRST so
                # the text between the tags doesn't leak through after tag
                # removal — closes a prompt-injection vector via inline JS/CSS.
                decoded = re.sub(r"<script\b[^>]*>.*?</script\s*>", " ", decoded, flags=re.IGNORECASE | re.DOTALL)
                decoded = re.sub(r"<style\b[^>]*>.*?</style\s*>", " ", decoded, flags=re.IGNORECASE | re.DOTALL)
                decoded = re.sub(r"<!--.*?-->", " ", decoded, flags=re.DOTALL)
                decoded = re.sub(r"<[^>]+>", " ", decoded)
                decoded = (
                    decoded.replace("&nbsp;", " ")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                    .replace("&amp;", "&")
                    .replace("&quot;", '"')
                )
                decoded = re.sub(r"\s+", " ", decoded)
            return decoded.strip()

        parts = payload.get("parts", [])

        # Prefer text/plain parts
        for part in parts:
            if part.get("mimeType") == "text/plain":
                result = self._extract_body(part, _depth + 1)
                if result:
                    return result

        # Fallback: any part that returns content
        for part in parts:
            result = self._extract_body(part, _depth + 1)
            if result:
                return result

        return ""

    @staticmethod
    def _encode(msg: MIMEText | MIMEMultipart) -> str:
        return base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
