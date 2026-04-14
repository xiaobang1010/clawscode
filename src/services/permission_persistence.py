from __future__ import annotations

import json
from pathlib import Path


SETTINGS_FILENAME = "settings.json"
CLAWSCODE_DIR_NAME = ".clawscode"


class PermissionPersistence:
    def __init__(self, cwd: Path, home: Path | None = None):
        self._cwd = cwd
        self._home = home or Path.home()
        self._project_settings_path = cwd / CLAWSCODE_DIR_NAME / SETTINGS_FILENAME
        self._user_settings_path = self._home / CLAWSCODE_DIR_NAME / SETTINGS_FILENAME

    def load_rules(self) -> dict:
        rules: dict = {
            "deny": [],
            "ask": [],
            "allow": [],
        }

        user_rules = self._load_from_file(self._user_settings_path)
        project_rules = self._load_from_file(self._project_settings_path)

        for source in (user_rules, project_rules):
            for key in ("deny", "ask", "allow"):
                if key in source:
                    rules[key].extend(source[key])

        return rules

    def save_allow_rule(self, rule: str, scope: str = "project") -> None:
        self._save_rule("allow", rule, scope)

    def save_deny_rule(self, rule: str, scope: str = "project") -> None:
        self._save_rule("deny", rule, scope)

    def save_ask_rule(self, rule: str, scope: str = "project") -> None:
        self._save_rule("ask", rule, scope)

    def remove_allow_rule(self, rule: str, scope: str = "project") -> bool:
        return self._remove_rule("allow", rule, scope)

    def remove_deny_rule(self, rule: str, scope: str = "project") -> bool:
        return self._remove_rule("deny", rule, scope)

    def remove_ask_rule(self, rule: str, scope: str = "project") -> bool:
        return self._remove_rule("ask", rule, scope)

    def _save_rule(self, category: str, rule: str, scope: str) -> None:
        path = self._get_settings_path(scope)
        settings = self._load_from_file(path)

        if category not in settings:
            settings[category] = []

        if rule not in settings[category]:
            settings[category].append(rule)

        self._save_to_file(path, settings)

    def _remove_rule(self, category: str, rule: str, scope: str) -> bool:
        path = self._get_settings_path(scope)
        settings = self._load_from_file(path)

        if category not in settings:
            return False

        if rule in settings[category]:
            settings[category].remove(rule)
            self._save_to_file(path, settings)
            return True

        return False

    def _get_settings_path(self, scope: str) -> Path:
        if scope == "user":
            return self._user_settings_path
        return self._project_settings_path

    def _load_from_file(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            content = path.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}

    def _save_to_file(self, path: Path, settings: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            content = json.dumps(settings, indent=2, ensure_ascii=False)
            path.write_text(content, encoding="utf-8")
        except OSError:
            pass
