from __future__ import annotations

import json
import os
import re
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urlparse

import requests


FILE_BLOCK_PATTERN = re.compile(
    r"(?:^===\s*\n|^)"
    r"filepath:\s*(?P<filepath>[^\n]+)\n"
    r"===\s*\n"
    r"(?P<content>.*?)(?=^===\s*\nfilepath:|^filepath:|\Z)",
    re.MULTILINE | re.DOTALL,
)

DEFAULT_FILE_PATH_BLACKLIST_SUBSTRINGS = [
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    ".DS_Store",
    ".mfhist",
]


@dataclass(frozen=True)
class MfConfig:
    url: str
    api_key: str
    model: str
    timeout_seconds: int = 120
    max_attempts: int = 4
    backoff_base: float = 1.0

    @classmethod
    def from_environment(cls) -> "MfConfig":
        return cls(
            url=os.environ.get("MFPLUGIN_URL", ""),
            api_key=os.environ.get("MFPLUGIN_API_KEY", ""),
            model=os.environ.get("MFPLUGIN_MODEL", ""),
        )

    def validate(self) -> None:
        if not self.url.strip():
            raise ValueError(
                "The LLM URL is missing. Set MFPLUGIN_URL or pass --url."
            )
        if not self.api_key.strip():
            raise ValueError(
                "The API key is missing. Set MFPLUGIN_API_KEY or pass "
                "--api-key."
            )
        if not self.model.strip():
            raise ValueError(
                "The model is missing. Set MFPLUGIN_MODEL or pass --model."
            )

        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("The LLM URL must be a valid HTTP or HTTPS URL.")

        # Parse the query for compatibility with endpoints using api-version.
        parse_qs(parsed.query)


class MfBackend:
    def __init__(
        self,
        root_path: str | os.PathLike[str],
        config: MfConfig,
        blacklist_substrings: Iterable[str] | None = None,
    ) -> None:
        self.root = Path(root_path).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f"Invalid directory: {self.root}")

        self.config = config
        self.blacklist_substrings = list(
            blacklist_substrings
            if blacklist_substrings is not None
            else DEFAULT_FILE_PATH_BLACKLIST_SUBSTRINGS
        )

    @property
    def history_path(self) -> Path:
        return self.root / ".mfhist"

    @staticmethod
    def default_history() -> dict:
        return {
            "version": 2,
            "user_input": "",
            "selected_files": [],
            "save_output": False,
            "last_change": {
                "changed_at": "",
                "files": [],
            },
        }

    @staticmethod
    def normalize_string_list(value) -> list[str]:
        if not isinstance(value, list):
            return []

        result: list[str] = []
        seen: set[str] = set()

        for item in value:
            path = str(item).strip()
            if not path or path in seen:
                continue
            seen.add(path)
            result.append(path)

        return result

    def load_history(self) -> dict:
        if not self.history_path.is_file():
            return self.default_history()

        raw = self.history_path.read_text(encoding="utf-8")
        if not raw:
            return self.default_history()

        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            history = self.default_history()
            history["user_input"] = raw
            return history

        if not isinstance(parsed, dict):
            history = self.default_history()
            history["user_input"] = raw
            return history

        history = self.default_history()

        user_input = parsed.get("user_input", "")
        history["user_input"] = (
            user_input if isinstance(user_input, str) else str(user_input)
        )
        history["selected_files"] = self.normalize_string_list(
            parsed.get("selected_files", [])
        )
        history["save_output"] = bool(parsed.get("save_output", False))

        last_change = parsed.get("last_change", {})
        if isinstance(last_change, dict):
            files = last_change.get("files", [])
            changed_at = last_change.get("changed_at", "")
            history["last_change"] = {
                "changed_at": (
                    changed_at
                    if isinstance(changed_at, str)
                    else str(changed_at)
                ),
                "files": files if isinstance(files, list) else [],
            }

        return history

    def write_history(self, history: dict) -> None:
        data = self.default_history()

        user_input = history.get("user_input", "")
        data["user_input"] = (
            user_input if isinstance(user_input, str) else str(user_input)
        )
        data["selected_files"] = self.normalize_string_list(
            history.get("selected_files", [])
        )
        data["save_output"] = bool(history.get("save_output", False))

        last_change = history.get("last_change", {})
        if isinstance(last_change, dict):
            files = last_change.get("files", [])
            changed_at = last_change.get("changed_at", "")
            data["last_change"] = {
                "changed_at": (
                    changed_at
                    if isinstance(changed_at, str)
                    else str(changed_at)
                ),
                "files": files if isinstance(files, list) else [],
            }

        self.root.mkdir(parents=True, exist_ok=True)

        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".mfhist.",
            suffix=".tmp",
            dir=self.root,
            text=True,
        )

        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary_name, self.history_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise

    def is_blacklisted(self, path: str | os.PathLike[str]) -> bool:
        path_text = str(path)
        normalized = os.path.normpath(path_text)
        posix_path = normalized.replace(os.sep, "/")

        return any(
            substring
            and (
                substring in path_text
                or substring in normalized
                or substring in posix_path
            )
            for substring in self.blacklist_substrings
        )

    def list_entries(self) -> list[str]:
        entries: list[str] = []

        for walk_root, directories, filenames in os.walk(self.root):
            walk_root_path = Path(walk_root)

            directories[:] = sorted(
                directory
                for directory in directories
                if directory != "node_modules"
                and not self.is_blacklisted(
                    walk_root_path / directory
                )
            )

            for directory in directories:
                path = walk_root_path / directory
                relative = path.relative_to(self.root).as_posix() + "/"
                entries.append(relative)

            for filename in sorted(filenames):
                path = walk_root_path / filename

                if path == self.history_path:
                    continue
                if self.is_blacklisted(path):
                    continue

                entries.append(path.relative_to(self.root).as_posix())

        return entries

    def resolve_inside_root(self, path: str) -> Path:
        raw_path = Path(str(path).rstrip("/"))

        if raw_path.is_absolute():
            resolved = raw_path.resolve()
        else:
            resolved = (self.root / raw_path).resolve()

        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise ValueError(
                f"Path is outside the selected folder: {path}"
            ) from error

        return resolved

    def relative_path(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path.resolve())

    def read_file(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def save_file(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(content), encoding="utf-8")

    def resolve_selected_files(
        self,
        selected_paths: Iterable[str],
    ) -> list[Path]:
        resolved_files: list[Path] = []
        seen: set[Path] = set()

        def add_file(file_path: Path) -> None:
            file_path = file_path.resolve()

            if file_path in seen:
                return
            if file_path == self.history_path:
                return
            if self.is_blacklisted(file_path):
                return

            seen.add(file_path)
            resolved_files.append(file_path)

        for selected_path in selected_paths:
            selected_text = str(selected_path).strip()
            if not selected_text or self.is_blacklisted(selected_text):
                continue

            absolute_path = self.resolve_inside_root(selected_text)

            if absolute_path.is_file():
                add_file(absolute_path)
                continue

            if absolute_path.is_dir():
                for walk_root, directories, filenames in os.walk(
                    absolute_path
                ):
                    walk_root_path = Path(walk_root)
                    directories[:] = sorted(
                        directory
                        for directory in directories
                        if not self.is_blacklisted(
                            walk_root_path / directory
                        )
                    )

                    for filename in sorted(filenames):
                        file_path = walk_root_path / filename
                        if file_path.is_file():
                            add_file(file_path)
                continue

            raise FileNotFoundError(
                f"Selected path does not exist: {selected_text}"
            )

        return resolved_files

    def build_prompt(
        self,
        selected_files: list[str],
        user_input: str,
        save_output: bool,
    ) -> str:
        prompt = [
            "You are an enchanced AI assistant. Your task is to help a "
            "human to find answers to his questions.",
            "Sometimes its coding related question, sometimes some basic "
            "information what they need.",
            "===",
            f"The User Input and Question: {user_input}",
            "===",
        ]

        resolved_files = self.resolve_selected_files(selected_files)

        if resolved_files:
            prompt.extend(
                [
                    "===",
                    "This is the list of files and their contant as context:",
                ]
            )

            for file_path in resolved_files:
                prompt.extend(
                    [
                        "===",
                        f"filepath: {self.relative_path(file_path)}",
                        "===",
                        self.read_file(file_path),
                        "===",
                    ]
                )

        if save_output:
            prompt.extend(
                [
                    "The user wants you to save the output into files.",
                    "That requires a strict structure in your response.",
                    "Your response must follow this structure for each file.",
                    "===\n===\nfilepath: <path>\n===\n"
                    "<file content>\n===\n",
                ]
            )

        return "\n".join(prompt)

    def send_llm_call(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string.")

        self.config.validate()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "api-key": self.config.api_key,
        }
        payload = {
            "input": prompt,
            "model": self.config.model,
        }

        last_exception: Exception | None = None
        last_response_text: str | None = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = requests.post(
                    self.config.url,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                last_response_text = response.text

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait = (
                            float(retry_after)
                            if retry_after is not None
                            else self.config.backoff_base
                            * (2 ** (attempt - 1))
                        )
                    except (TypeError, ValueError):
                        wait = self.config.backoff_base * (
                            2 ** (attempt - 1)
                        )

                    if attempt == self.config.max_attempts:
                        response.raise_for_status()

                    time.sleep(wait)
                    continue

                if 500 <= response.status_code < 600:
                    if attempt == self.config.max_attempts:
                        response.raise_for_status()

                    time.sleep(
                        self.config.backoff_base * (2 ** (attempt - 1))
                    )
                    continue

                if not 200 <= response.status_code < 300:
                    raise requests.HTTPError(
                        "Unexpected status code: "
                        f"{response.status_code}; body: {response.text}",
                        response=response,
                    )

                try:
                    data = response.json()
                except requests.exceptions.JSONDecodeError as error:
                    raise ValueError(
                        "Response is not valid JSON: "
                        f"{error}; body: {response.text}"
                    ) from error

                output = data.get("output")
                if not isinstance(output, list) or not output:
                    raise ValueError(
                        "Unexpected response structure: missing or "
                        "malformed 'output' list."
                    )

                for item in output:
                    if not isinstance(item, dict):
                        continue

                    content = item.get("content")
                    if not isinstance(content, list):
                        continue

                    for candidate in content:
                        if (
                            isinstance(candidate, dict)
                            and isinstance(candidate.get("text"), str)
                        ):
                            return candidate["text"]

                raise ValueError(
                    "Unexpected response structure: no text field found; "
                    f"response JSON: {json.dumps(data, ensure_ascii=False)}"
                )

            except requests.RequestException as error:
                last_exception = error
                if attempt == self.config.max_attempts:
                    break

                time.sleep(
                    self.config.backoff_base * (2 ** (attempt - 1))
                )

        message = "Failed to complete LLM call after retries."
        if last_exception is not None:
            raise RuntimeError(
                f"{message} Last exception: {last_exception}. "
                f"Last response body: {last_response_text}"
            ) from last_exception

        raise RuntimeError(
            f"{message} Last response body: {last_response_text}"
        )

    @staticmethod
    def extract_files(text: str) -> dict[str, str]:
        text = textwrap.dedent(text).strip()
        result: dict[str, str] = {}

        for match in FILE_BLOCK_PATTERN.finditer(text):
            filename = match.group("filepath").strip()
            content = match.group("content").rstrip()

            if content.endswith("==="):
                content = content[:-3].rstrip()

            result[filename] = content

        return result

    def collect_backups_for_mapping(
        self,
        mapping: dict[str, str],
    ) -> tuple[list[dict], list[tuple[Path, str, str]], list[str]]:
        backups: list[dict] = []
        files_to_write: list[tuple[Path, str, str]] = []
        skipped: list[str] = []
        seen: set[Path] = set()

        for path, content in mapping.items():
            try:
                absolute_path = self.resolve_inside_root(path)
            except ValueError as error:
                skipped.append(str(error))
                continue

            history_path = self.relative_path(absolute_path)

            if absolute_path == self.history_path:
                skipped.append(
                    f"{history_path} skipped because .mfhist is managed "
                    "by the application"
                )
                continue

            normalized = absolute_path.resolve()
            if normalized in seen:
                skipped.append(
                    f"{history_path} skipped because it was duplicated "
                    "in the response"
                )
                continue
            seen.add(normalized)

            if absolute_path.is_dir():
                skipped.append(
                    f"{history_path} skipped because it is a directory"
                )
                continue

            existed = absolute_path.exists()
            original_content = (
                self.read_file(absolute_path) if existed else ""
            )

            backups.append(
                {
                    "path": history_path,
                    "existed": bool(existed),
                    "content": original_content,
                }
            )
            files_to_write.append(
                (absolute_path, content, history_path)
            )

        return backups, files_to_write, skipped

    def build_result(
        self,
        selected_files: list[str],
        user_input: str,
        save_output: bool,
    ) -> str:
        selected_files = self.normalize_string_list(selected_files)
        save_output = bool(save_output)

        history = self.load_history()
        history["user_input"] = str(user_input)
        history["selected_files"] = selected_files
        history["save_output"] = save_output

        # Persist UI state even when the request subsequently fails.
        self.write_history(history)

        prompt = self.build_prompt(
            selected_files,
            str(user_input),
            save_output,
        )
        response = self.send_llm_call(prompt)

        if not save_output:
            return response

        mapping = self.extract_files(response)
        if not mapping:
            return (
                "No file blocks found in the response. "
                "No files were updated."
            )

        backups, files_to_write, skipped = (
            self.collect_backups_for_mapping(mapping)
        )

        if files_to_write:
            history = self.load_history()
            history["user_input"] = str(user_input)
            history["selected_files"] = selected_files
            history["save_output"] = save_output
            history["last_change"] = {
                "changed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "files": backups,
            }

            # Write backups before changing any target file.
            self.write_history(history)

            for absolute_path, content, _display_path in files_to_write:
                self.save_file(absolute_path, content)

        lines: list[str] = []

        if files_to_write:
            lines.append("Files updated:")
            lines.extend(
                display_path
                for _absolute_path, _content, display_path
                in files_to_write
            )
            lines.extend(
                [
                    "End of updated files",
                    "",
                    "Original content was stored in .mfhist. "
                    "Use Revert last change to restore it.",
                ]
            )
        else:
            lines.append("No files were updated.")

        if skipped:
            lines.extend(["", "Skipped files:"])
            lines.extend(skipped)

        return "\n".join(lines)

    def revert_last_change(self) -> str:
        history = self.load_history()
        last_change = history.get("last_change", {})
        files = (
            last_change.get("files", [])
            if isinstance(last_change, dict)
            else []
        )

        if not files:
            return "No last change found in .mfhist. Nothing to revert."

        restored: list[str] = []
        deleted: list[str] = []
        errors: list[str] = []

        for item in files:
            if not isinstance(item, dict):
                continue

            path = str(item.get("path", "")).strip()
            existed = bool(item.get("existed", True))
            content = item.get("content", "")

            if not path:
                continue

            try:
                absolute_path = self.resolve_inside_root(path)
                display_path = self.relative_path(absolute_path)

                if absolute_path == self.history_path:
                    errors.append(
                        f"{display_path}: refusing to modify .mfhist"
                    )
                    continue

                if existed:
                    self.save_file(
                        absolute_path,
                        content if isinstance(content, str) else str(content),
                    )
                    restored.append(display_path)
                elif absolute_path.is_file():
                    absolute_path.unlink()
                    deleted.append(display_path)
                elif absolute_path.exists():
                    errors.append(
                        f"{display_path}: path is not a file and was not "
                        "deleted"
                    )
                else:
                    deleted.append(display_path)
            except Exception as error:
                errors.append(f"{path}: {error}")

        if not errors:
            history["last_change"] = {
                "changed_at": "",
                "files": [],
            }
            self.write_history(history)

        lines: list[str] = []

        if restored:
            lines.append("Files restored:")
            lines.extend(restored)

        if deleted:
            if lines:
                lines.append("")
            lines.append(
                "Files deleted because they did not exist before the "
                "last change:"
            )
            lines.extend(deleted)

        if errors:
            if lines:
                lines.append("")
            lines.extend(
                [
                    "Errors:",
                    *errors,
                    "",
                    ".mfhist was kept so you can try reverting again.",
                ]
            )
        else:
            if lines:
                lines.append("")
            lines.extend(
                [
                    "Last change reverted successfully.",
                    ".mfhist input, selected files, and save-output "
                    "setting were kept, and the consumed backup was "
                    "cleared.",
                ]
            )

        return "\n".join(lines)
