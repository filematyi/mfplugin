import requests
import time
import json
from urllib.parse import urlparse, parse_qs
import vim
import re
import textwrap
import os

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


def _extract_files(text: str) -> dict[str, str]:
    text = textwrap.dedent(text).strip()

    result: dict[str, str] = {}
    for match in FILE_BLOCK_PATTERN.finditer(text):
        filename = match.group("filepath").strip()
        content = match.group("content").rstrip()
        if content.endswith("==="):
            content = content[0:-3]
        result[filename] = content

    return result


def _send_llm_call(prompt: str) -> str:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    try:
        url = vim.eval('g:mfplugin_url')
        api_key = vim.eval('g:mfplugin_api_key')
        model = vim.eval('g:mfplugin_model')
    except NameError:
        raise RuntimeError("vim is not available in this environment")
    except Exception as e:
        raise RuntimeError(f"Failed to read vim configuration variables: {e}")

    if not isinstance(url, str) or not url.strip():
        raise ValueError("g:mfplugin_url must be a non-empty string")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("g:mfplugin_api_key must be a non-empty string")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("g:mfplugin_model must be a non-empty string")

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    api_versions = qs.get("api-version") or qs.get("api_version")  # accept underscore variant just in case

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "api-key": api_key
    }
    payload = {
        "input": prompt,
        "model": model,
    }

    max_attempts = 4
    backoff_base = 1.0
    timeout_seconds = 120

    last_exception = None
    last_response_text = None

    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
            last_response_text = resp.text
            # handle rate limiting
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                try:
                    wait = int(retry_after) if retry_after is not None else backoff_base * (2 ** (attempt - 1))
                except Exception:
                    wait = backoff_base * (2 ** (attempt - 1))
                if attempt == max_attempts:
                    resp.raise_for_status()
                time.sleep(wait)
                continue
            # retry on server errors
            if 500 <= resp.status_code < 600:
                if attempt == max_attempts:
                    resp.raise_for_status()
                time.sleep(backoff_base * (2 ** (attempt - 1)))
                continue
            if not (200 <= resp.status_code < 300):
                raise requests.HTTPError(f"Unexpected status code: {resp.status_code}; body: {resp.text}")

            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                raise ValueError(f"Response is not valid JSON: {e}; body: {resp.text}")

            try:
                output = data.get("output")
                if not isinstance(output, list) or len(output) < 1:
                    raise KeyError("missing or malformed 'output' list")
                items = [op for op in output if 'content' in op]

                first_content = None
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if 'content' not in item.keys():
                        continue
                    tmp_content = item['content']
                    if len(tmp_content) == 0:
                        continue
                    if not isinstance(tmp_content, list) or len(tmp_content) == 0:
                        continue
                    if 'text' not in tmp_content[0].keys():
                        continue
                    first_content = tmp_content[0]

                if not isinstance(first_content, dict) or "text" not in first_content:
                    raise KeyError("content[0] missing 'text' field")
                text = first_content["text"]
                if not isinstance(text, str):
                    raise ValueError("extracted text is not a string")
                return text
            except Exception as e:
                # surface the full response to aid debugging
                raise ValueError(
                    f"Unexpected response structure: {e}; response JSON: {json.dumps(data, ensure_ascii=False)}"
                )

        except requests.RequestException as e:
            last_exception = e
            # network error / timeout etc -> retry with backoff
            if attempt == max_attempts:
                break
            time.sleep(backoff_base * (2 ** (attempt - 1)))
            continue
        except Exception:
            # any other exception (parsing/structure), don't retry further
            raise

    err_msg = "Failed to complete LLM call after retries."
    if last_exception:
        raise RuntimeError(f"{err_msg} Last exception: {last_exception}. Last response body: {last_response_text}")
    else:
        raise RuntimeError(f"{err_msg} Last response body: {last_response_text}")


def _to_path_string(path) -> str:
    if isinstance(path, bytes):
        return path.decode('utf-8')
    return str(path)


def _normalize_root_path(root_path=None) -> str:
    if root_path is None:
        return os.getcwd()

    root_path = _to_path_string(root_path)
    if not root_path:
        return os.getcwd()

    return os.path.abspath(os.path.normpath(root_path))


def _history_file_path(root_path=None) -> str:
    return os.path.join(_normalize_root_path(root_path), ".mfhist")


def _default_history() -> dict:
    return {
        "version": 1,
        "user_input": "",
        "last_change": {
            "changed_at": "",
            "files": [],
        },
    }


def _load_history(root_path=None) -> dict:
    histfile = _history_file_path(root_path)

    if not os.path.isfile(histfile):
        return _default_history()

    with open(histfile, "r", encoding="utf-8") as f:
        raw = f.read()

    if not raw:
        return _default_history()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            history = _default_history()

            user_input = parsed.get("user_input", "")
            history["user_input"] = user_input if isinstance(user_input, str) else str(user_input)

            last_change = parsed.get("last_change", {})
            if isinstance(last_change, dict):
                files = last_change.get("files", [])
                history["last_change"] = {
                    "changed_at": last_change.get("changed_at", ""),
                    "files": files if isinstance(files, list) else [],
                }

            return history
    except Exception:
        # Backward compatibility with old .mfhist format where the file
        # contained only raw user input.
        pass

    history = _default_history()
    history["user_input"] = raw
    return history


def _write_history(root_path, history: dict) -> None:
    histfile = _history_file_path(root_path)
    directory = os.path.dirname(histfile)

    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    data = _default_history()
    data["user_input"] = history.get("user_input", "")
    data["last_change"] = history.get("last_change", {"changed_at": "", "files": []})

    tmpfile = histfile + ".tmp"
    with open(tmpfile, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(tmpfile, histfile)


def _path_relative_to_root(path: str, root_path=None) -> str:
    root_path = _normalize_root_path(root_path)
    abs_path = os.path.abspath(os.path.normpath(path))

    try:
        common = os.path.commonpath([root_path, abs_path])
        if common == root_path:
            return os.path.relpath(abs_path, root_path).replace(os.sep, "/")
    except ValueError:
        # Different Windows drives, etc.
        pass

    return abs_path


def _resolve_path_against_root(path: str, root_path=None) -> str:
    path = _to_path_string(path).strip()
    root_path = _normalize_root_path(root_path)

    if os.path.isabs(path):
        return os.path.abspath(os.path.normpath(path))

    return os.path.abspath(os.path.normpath(os.path.join(root_path, path)))


def _is_history_file(path: str, root_path=None) -> bool:
    return os.path.abspath(os.path.normpath(path)) == os.path.abspath(os.path.normpath(_history_file_path(root_path)))


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _save_file(path: str, content: str) -> None:
    if isinstance(content, bytes):
        content = content.decode('utf-8')

    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)

    with open(path, 'w', encoding="utf-8") as f:
        f.write(content)


def _get_blacklist_substrings() -> list[str]:
    """
    Returns file path blacklist substrings.

    Optional Vim config:
        let g:mfplugin_file_blacklist = ['node_modules', '.git', '__pycache__']

    If the Vim variable is not set, DEFAULT_FILE_PATH_BLACKLIST_SUBSTRINGS is used.
    """
    try:
        configured_blacklist = vim.eval("get(g:, 'mfplugin_file_blacklist', [])")
    except Exception:
        configured_blacklist = []

    if isinstance(configured_blacklist, str):
        configured_blacklist = [configured_blacklist]

    if configured_blacklist:
        return [_to_path_string(item) for item in configured_blacklist if _to_path_string(item)]

    return DEFAULT_FILE_PATH_BLACKLIST_SUBSTRINGS


def _is_blacklisted_path(path: str, blacklist_substrings: list[str]) -> bool:
    normalized_path = os.path.normpath(path)
    posix_path = normalized_path.replace(os.sep, "/")

    for substring in blacklist_substrings:
        if not substring:
            continue
        if substring in path or substring in normalized_path or substring in posix_path:
            return True

    return False


def _resolve_selected_files(selected_paths: list, root_path=None) -> list[str]:
    """
    selected_paths can contain files and/or folders.

    If a selected path is a file, it is added directly.
    If a selected path is a folder, every file inside that folder is added recursively.
    Any file path containing a blacklist substring is skipped.
    """
    root_path = _normalize_root_path(root_path)
    blacklist_substrings = _get_blacklist_substrings()
    resolved_files = []
    seen = set()

    def add_file(file_path: str) -> None:
        if _is_blacklisted_path(file_path, blacklist_substrings):
            return

        if _is_history_file(file_path, root_path):
            return

        key = os.path.abspath(os.path.normpath(file_path))
        if key in seen:
            return

        seen.add(key)
        resolved_files.append(file_path)

    for selected_path in selected_paths or []:
        selected_path = _to_path_string(selected_path)

        if _is_blacklisted_path(selected_path, blacklist_substrings):
            continue

        abs_selected_path = _resolve_path_against_root(selected_path, root_path)

        if os.path.isfile(abs_selected_path):
            add_file(abs_selected_path)
            continue

        if os.path.isdir(abs_selected_path):
            for root, dirs, files in os.walk(abs_selected_path):
                dirs[:] = sorted(
                    d for d in dirs
                    if not _is_blacklisted_path(os.path.join(root, d), blacklist_substrings)
                )

                for filename in sorted(files):
                    file_path = os.path.join(root, filename)
                    if os.path.isfile(file_path):
                        add_file(file_path)
            continue

        # Preserve old behavior for unknown paths:
        # it will fail later in _read_file just like before.
        add_file(abs_selected_path)

    return resolved_files


def _build_prompt(selected_files: list, user_input: str, save_output: bool, root_path=None) -> list:
    root_path = _normalize_root_path(root_path)

    prompt = ["You are an enchanced AI assistant. Your task is to help a human to find answers to his questions."]
    prompt.append("Sometimes its coding related question, sometimes some basic information what they need.")
    prompt.append("===")
    prompt.append(f"The User Input and Question: {user_input}")
    prompt.append("===")

    resolved_files = _resolve_selected_files(selected_files, root_path)

    if resolved_files:
        prompt.append("===")
        prompt.append("This is the list of files and their contant as context:")
        for f in resolved_files:
            prompt.append("===")
            prompt.append(f"filepath: {_path_relative_to_root(f, root_path)}")
            prompt.append("===")
            prompt.append(_read_file(f))
            prompt.append("===")

    if save_output:
        prompt.append("The user wants you to save the output into files.")
        prompt.append("That requires a strict structure in your response.")
        prompt.append("Your response must follow this structure for each file.")
        prompt.append("===\n===\nfilepath: <path>\n===\n<file content>\n===\n")

    return prompt


def _collect_backups_for_mapping(mapping: dict[str, str], root_path=None) -> tuple[list[dict], list[tuple[str, str, str]], list[str]]:
    root_path = _normalize_root_path(root_path)

    backups = []
    files_to_write = []
    skipped = []
    seen = set()

    for path, content in mapping.items():
        abs_path = _resolve_path_against_root(path, root_path)
        history_path = _path_relative_to_root(abs_path, root_path)

        if _is_history_file(abs_path, root_path):
            skipped.append(f"{history_path} skipped because .mfhist is managed by the plugin")
            continue

        key = os.path.abspath(os.path.normcase(os.path.normpath(abs_path)))
        if key in seen:
            skipped.append(f"{history_path} skipped because it was duplicated in the response")
            continue

        seen.add(key)

        if os.path.isdir(abs_path):
            skipped.append(f"{history_path} skipped because it is a directory")
            continue

        existed = os.path.exists(abs_path)
        original_content = ""

        if existed:
            original_content = _read_file(abs_path)

        backups.append({
            "path": history_path,
            "existed": bool(existed),
            "content": original_content,
        })
        files_to_write.append((abs_path, content, history_path))

    return backups, files_to_write, skipped


def build_result(selected_files, user_input, save_output, root_path=None):
    """
    selected_files: list[str]
    user_input: str
    save_output: bool
    root_path: project root where .mfhist is stored
    return: str
    """
    root_path = _normalize_root_path(root_path)

    history = _load_history(root_path)
    history["user_input"] = user_input
    _write_history(root_path, history)

    prompt = _build_prompt(selected_files, user_input, save_output, root_path)
    string_prompt = "\n".join(prompt)
    response = _send_llm_call(prompt=string_prompt)

    if save_output:
        mapping = _extract_files(response)

        if not mapping:
            return "No file blocks found in the response. No files were updated."

        backups, files_to_write, skipped = _collect_backups_for_mapping(mapping, root_path)

        if files_to_write:
            history = _load_history(root_path)
            history["user_input"] = user_input
            history["last_change"] = {
                "changed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "files": backups,
            }

            # Persist the original file contents before changing anything.
            # If a later write fails halfway, option 4 can still restore
            # the files that were already modified.
            _write_history(root_path, history)

            for abs_path, content, history_path in files_to_write:
                _save_file(abs_path, content)

        lines = []
        if files_to_write:
            lines.extend(["Files updated:"])
            lines.extend(history_path for _abs_path, _content, history_path in files_to_write)
            lines.append("End of updated files")
            lines.append("")
            lines.append("Original content was stored in .mfhist. Press option 4 to revert this change.")
        else:
            lines.append("No files were updated.")

        if skipped:
            lines.append("")
            lines.append("Skipped files:")
            lines.extend(skipped)

        return "\n".join(lines)

    return response


def revert_last_change(root_path=None):
    """
    Revert files using the last saved backup in .mfhist.

    Existing files are restored to their previous content.
    Files that did not exist before the last saved output are deleted.
    """
    root_path = _normalize_root_path(root_path)
    history = _load_history(root_path)

    last_change = history.get("last_change", {})
    files = last_change.get("files", []) if isinstance(last_change, dict) else []

    if not files:
        return "No last change found in .mfhist. Nothing to revert."

    restored = []
    deleted = []
    errors = []

    for item in files:
        if not isinstance(item, dict):
            continue

        path = item.get("path", "")
        existed = bool(item.get("existed", True))
        content = item.get("content", "")

        if not path:
            continue

        abs_path = _resolve_path_against_root(path, root_path)
        display_path = _path_relative_to_root(abs_path, root_path)

        try:
            if _is_history_file(abs_path, root_path):
                errors.append(f"{display_path}: refusing to modify .mfhist")
                continue

            if existed:
                _save_file(abs_path, content if isinstance(content, str) else str(content))
                restored.append(display_path)
            else:
                if os.path.isfile(abs_path):
                    os.remove(abs_path)
                    deleted.append(display_path)
                elif os.path.exists(abs_path):
                    errors.append(f"{display_path}: existed after change but is not a file, not deleted")
                else:
                    deleted.append(display_path)
        except Exception as e:
            errors.append(f"{display_path}: {e}")

    if not errors:
        history["last_change"] = {
            "changed_at": "",
            "files": [],
        }
        _write_history(root_path, history)

    lines = []

    if restored:
        lines.append("Files restored:")
        lines.extend(restored)

    if deleted:
        if lines:
            lines.append("")
        lines.append("Files deleted because they did not exist before the last change:")
        lines.extend(deleted)

    if errors:
        if lines:
            lines.append("")
        lines.append("Errors:")
        lines.extend(errors)
        lines.append("")
        lines.append(".mfhist was kept so you can try reverting again.")
    else:
        if lines:
            lines.append("")
        lines.append("Last change reverted successfully.")
        lines.append(".mfhist user input was kept, and the consumed backup was cleared.")

    return "\n".join(lines)
