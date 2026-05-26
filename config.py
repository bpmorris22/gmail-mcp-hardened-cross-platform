import json
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    if not config_path.exists():
        example = config_path.parent / "config.json.example"
        raise FileNotFoundError(
            f"Config file not found at {config_path}.\n"
            f"Copy {example} to {config_path} and fill in your account details."
        )
    with open(config_path) as f:
        return json.load(f)


def get_accounts(config: Dict[str, Any]) -> Dict[str, Dict]:
    return config.get("accounts", {})


def get_credentials_dir(config: Dict[str, Any], base_dir: Path = DEFAULT_CONFIG_PATH.parent) -> Path:
    path = Path(config.get("credentials_dir", "./credentials"))
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def get_client_secret_path(
    config: Dict[str, Any], account_name: Optional[str] = None
) -> Path:
    """Resolve the client_secret.json path, optionally per account.

    Priority:
      1. accounts[account_name].client_secret   (per-account override)
      2. credentials_dir/client_secret.json     (shared default)

    Per-account values may be absolute or relative; relative paths are
    resolved against the repo root (the directory containing config.json).
    """
    if account_name:
        per_account = (
            config.get("accounts", {}).get(account_name, {}).get("client_secret")
        )
        if per_account:
            path = Path(per_account)
            if not path.is_absolute():
                path = DEFAULT_CONFIG_PATH.parent / path
            return path.resolve()

    return get_credentials_dir(config) / "client_secret.json"
