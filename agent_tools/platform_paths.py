from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


VSCODE_APP_NAMES = ("Code", "Code - Insiders", "VSCodium")


def normalized_platform(platform: str | None = None) -> str:
    value = platform or sys.platform
    if value.startswith("win"):
        return "windows"
    if value == "darwin":
        return "macos"
    return "linux"


def default_home(home: Path | None = None) -> Path:
    return home or Path.home()


def default_copilot_dir(home: Path | None = None) -> Path:
    return default_home(home) / ".copilot"


def default_cli_state_dir(home: Path | None = None) -> Path:
    return default_copilot_dir(home) / "session-state"


def default_cli_store_db(home: Path | None = None) -> Path:
    return default_copilot_dir(home) / "session-store.db"


def vscode_app_dirs(
    home: Path | None = None,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[Path]:
    current_home = default_home(home)
    current_env = os.environ if env is None else env
    platform_name = normalized_platform(platform)

    if platform_name == "windows":
        appdata = current_env.get("APPDATA")
        base_dir = Path(appdata) if appdata else current_home / "AppData" / "Roaming"
    elif platform_name == "macos":
        base_dir = current_home / "Library" / "Application Support"
    else:
        config_home = current_env.get("XDG_CONFIG_HOME")
        base_dir = Path(config_home) if config_home else current_home / ".config"

    return [base_dir / app_name for app_name in VSCODE_APP_NAMES]


def vscode_logs_dirs(
    home: Path | None = None,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[Path]:
    return [app_dir / "logs" for app_dir in vscode_app_dirs(home, platform, env)]


def vscode_workspace_storage_dirs(
    home: Path | None = None,
    platform: str | None = None,
    env: Mapping[str, str] | None = None,
) -> list[Path]:
    return [app_dir / "User" / "workspaceStorage" for app_dir in vscode_app_dirs(home, platform, env)]


def xcode_logs_dir(home: Path | None = None, platform: str | None = None) -> Path | None:
    if normalized_platform(platform) != "macos":
        return None
    return default_home(home) / "Library" / "Logs" / "GitHubCopilot"
