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
                item = [op for op in output if 'content' in op][0]
                if not isinstance(item, dict):
                    raise KeyError("output[1] is not an object")
                content = item.get("content")
                if not isinstance(content, list) or len(content) == 0:
                    raise KeyError("missing or malformed 'content' list in output[1]")
                first_content = content[0]
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


def _read_file(path: str) -> str:
    with open(path) as f:
        return f.read()


def _save_file(path: str, content: str) -> None:
    if isinstance(content, bytes):
        content = content.decode('utf-8')
    entities = path.split("/")
    if len(entities) > 1:
        folders = "/".join(entities[0: -1])
        if not os.path.exists(folders):
            os.makedirs(folders)
    with open(path, 'w') as f:
        f.write(content)


def _to_path_string(path) -> str:
    if isinstance(path, bytes):
        return path.decode('utf-8')
    return str(path)


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


def _resolve_selected_files(selected_paths: list) -> list[str]:
    """
    selected_paths can contain files and/or folders.

    If a selected path is a file, it is added directly.
    If a selected path is a folder, every file inside that folder is added recursively.
    Any file path containing a blacklist substring is skipped.
    """
    blacklist_substrings = _get_blacklist_substrings()
    resolved_files = []
    seen = set()

    def add_file(file_path: str) -> None:
        if _is_blacklisted_path(file_path, blacklist_substrings):
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

        if os.path.isfile(selected_path):
            add_file(selected_path)
            continue

        if os.path.isdir(selected_path):
            for root, dirs, files in os.walk(selected_path):
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
        add_file(selected_path)

    return resolved_files


def _build_prompt(selected_files: list, user_input: str, save_output: bool) -> list:
    prompt = ["You are an enchanced AI assistant. Your task is to help a human to find answers to his questions."]
    prompt.append("Sometimes its coding related question, sometimes some basic information what they need.")
    prompt.append("===")
    prompt.append(f"The User Input and Question: {user_input}")
    prompt.append("===")

    resolved_files = _resolve_selected_files(selected_files)

    if resolved_files:
        prompt.append("===")
        prompt.append("This is the list of files and their contant as context:")
        for f in resolved_files:
            prompt.append("===")
            prompt.append(f"filepath: {f}")
            prompt.append("===")
            prompt.append(_read_file(f))
            prompt.append("===")

    if save_output:
        prompt.append("The user wants you to save the output into files.")
        prompt.append("That requires a strict structure in your response.")
        prompt.append("Your response must follow this structure for each file.")
        prompt.append("===\n===\nfilepath: <path>\n===\n<file content>\n===\n")

    return prompt


def build_result(selected_files, user_input, save_output):
    """
    selected_files: list[str]
    user_input: str
    save_output: bool
    return: str
    """
    with open(".mfhist", "w") as f:
        f.write(user_input.decode('utf-8'))
    prompt = _build_prompt(selected_files, user_input, save_output)
    string_prompt = "\n".join(prompt)
    response = _send_llm_call(prompt=string_prompt)

    if save_output:
        mapping = _extract_files(response)

        for path, content in mapping.items():
            _save_file(path, content)
        return "\n".join(["Files updated:"] + list(mapping.keys()) + ["End of updated files"])

    return response
