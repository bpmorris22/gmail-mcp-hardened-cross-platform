import os
import re
import stat
import sys
from pathlib import Path
from typing import Callable, List, Optional, Union

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# gmail.modify covers the exposed Gmail read, draft, send, label, and trash
# actions without allowing immediate permanent deletion. Calendar operations
# are read-only and request only list/event access used by gcalendar.py.
# Re-run setup_auth.py after changing this list.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]

# Account names are used as filenames in credentials/tokens/. Restrict to a
# safe charset so a config typo like "../foo" can't write tokens outside the
# tokens directory. `@` is allowed so accounts can be named like an email
# (e.g. "personal@", "work@") — but `.`, `/`, `\`, and spaces are still blocked
# to prevent path traversal and other surprises.
_VALID_ACCOUNT_NAME = re.compile(r"^[A-Za-z0-9_@-]+$")


class AuthManager:
    def __init__(
        self,
        credentials_dir: Path,
        client_secret_resolver: Union[Callable[[str], Path], Path, str],
    ):
        """Per-account OAuth manager.

        `client_secret_resolver` is a callable `account_name -> Path` that
        returns the OAuth client_secret.json for a given account. Each account
        can map to its own Cloud project (different client_secret file) so the
        blast radius of a single compromised client is limited to one mailbox.

        A bare Path or str is also accepted for the single-project case — it
        gets wrapped into a resolver that returns the same path for every
        account.
        """
        self.credentials_dir = Path(credentials_dir)
        if callable(client_secret_resolver):
            self.client_secret_resolver: Callable[[str], Path] = client_secret_resolver
        else:
            fixed_path = Path(client_secret_resolver)
            self.client_secret_resolver = lambda _account: fixed_path
        self.tokens_dir = self.credentials_dir / "tokens"
        self.tokens_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.credentials_dir, stat.S_IRWXU)
            os.chmod(self.tokens_dir, stat.S_IRWXU)
        except OSError as exc:
            print(
                f"[gmail-mcp][WARN] Could not restrict credential directory "
                f"permissions: {type(exc).__name__}. Restrict access manually.",
                file=sys.stderr,
                flush=True,
            )

    def get_client_secret_path(self, account_name: str) -> Path:
        return Path(self.client_secret_resolver(account_name))

    def get_token_path(self, account_name: str) -> Path:
        if not _VALID_ACCOUNT_NAME.match(account_name):
            raise ValueError(
                f"Invalid account name '{account_name}'. Account names may only "
                "contain letters, digits, '@', underscores, and hyphens — no "
                "slashes, dots, spaces, or other characters."
            )
        return self.tokens_dir / f"{account_name}.json"

    def get_credentials(self, account_name: str) -> Optional[Credentials]:
        token_path = self.get_token_path(account_name)
        if not token_path.exists():
            return None

        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as exc:
            print(
                f"[gmail-mcp][WARN] Failed to load token for '{account_name}' from "
                f"{token_path}: {type(exc).__name__}: {exc}. Delete the file and "
                "re-run `python setup_auth.py` if this persists.",
                file=sys.stderr,
                flush=True,
            )
            return None

        if creds.valid:
            self._warn_if_scopes_missing(account_name, creds)
            return creds

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                self._save_token(account_name, creds)
                self._warn_if_scopes_missing(account_name, creds)
                return creds
            except Exception as exc:
                print(
                    f"[gmail-mcp][WARN] Failed to refresh token for '{account_name}': "
                    f"{type(exc).__name__}: {exc}. The refresh token may have been "
                    "revoked. Re-run `python setup_auth.py` to re-authenticate.",
                    file=sys.stderr,
                    flush=True,
                )
                return None

        return None

    @staticmethod
    def _warn_if_scopes_missing(account_name: str, creds: Credentials) -> None:
        """Print a one-line stderr warning if the token is missing any SCOPES.

        Calling code still gets the credentials; tools requiring omitted scopes
        can fail until the user re-runs setup_auth.py."""
        granted = set(creds.scopes or [])
        missing = [s for s in SCOPES if s not in granted]
        if missing:
            print(
                f"[gmail-mcp][WARN] Token for '{account_name}' is missing scopes: "
                f"{missing}. Tools depending on these scopes will fail. "
                f"Re-run `python setup_auth.py` to grant them.",
                file=sys.stderr,
                flush=True,
            )

    def authenticate(self, account_name: str, email: Optional[str] = None) -> Credentials:
        client_secret_path = self.get_client_secret_path(account_name)
        if not client_secret_path.exists():
            raise FileNotFoundError(
                f"client_secret.json for account '{account_name}' not found at "
                f"{client_secret_path}.\n"
                "Download it from Google Cloud Console > APIs & Services > "
                "Credentials for the project bound to this account."
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path), SCOPES
        )

        # login_hint pre-fills the email field; prompt=select_account
        # forces account picker even if already signed in.
        kwargs: dict = {"port": 0, "prompt": "select_account"}
        if email:
            kwargs["login_hint"] = email

        creds = flow.run_local_server(**kwargs)
        self._save_token(account_name, creds)
        return creds

    def _save_token(self, account_name: str, creds: Credentials) -> None:
        token_path = self.get_token_path(account_name)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        try:
            os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError as exc:
            print(
                f"[gmail-mcp][WARN] Could not restrict token permissions for "
                f"'{account_name}': {type(exc).__name__}. Restrict access to "
                "the credentials directory manually.",
                file=sys.stderr,
                flush=True,
            )

    def is_authenticated(self, account_name: str) -> bool:
        return self.get_credentials(account_name) is not None

    def list_authenticated(self) -> List[str]:
        if not self.tokens_dir.exists():
            return []
        return [p.stem for p in self.tokens_dir.glob("*.json")]
