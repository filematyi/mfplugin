" plugin/mf.vim
if !has('python3')
  echoerr 'Python3 support is required for mfplugin'
  finish
endif

" Define the Python function using Vim's embedded Python 3
python3 << EOF
import vim
import requests
import re
import os
from pathlib import Path  
from typing import List, Union  
import time
import json
from urllib.parse import urlparse, parse_qs
    

def _send_llm_call(prompt: str) -> str:
    # basic input validation
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")

    # attempt to get vim variables (raises if vim not available)
    try:
        url = vim.eval('g:mfplugin_url')
        api_key = vim.eval('g:mfplugin_api_key')
        model = vim.eval('g:mfplugin_model')
    except NameError:
        raise RuntimeError("vim is not available in this environment")
    except Exception as e:
        raise RuntimeError(f"Failed to read vim configuration variables: {e}")

    # validate url, api_key and model
    if not isinstance(url, str) or not url.strip():
        raise ValueError("g:mfplugin_url must be a non-empty string")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("g:mfplugin_api_key must be a non-empty string")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("g:mfplugin_model must be a non-empty string")

    # validate azure openai api-version query param
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    api_versions = qs.get("api-version") or qs.get("api_version")  # accept underscore variant just in case
    # expected_version = "2025-04-01-preview"
    # if not api_versions or expected_version not in api_versions:
    #     raise ValueError(f"URL must include api-version={expected_version} as a query parameter")

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
    timeout_seconds = 60

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
            # for other non-2xx codes, raise to surface the error
            if not (200 <= resp.status_code < 300):
                raise requests.HTTPError(f"Unexpected status code: {resp.status_code}; body: {resp.text}")

            # parse JSON
            try:
                data = resp.json()
            except json.JSONDecodeError as e:
                raise ValueError(f"Response is not valid JSON: {e}; body: {resp.text}")

            # validate expected response structure and extract text
            # expected: response["output"][1]["content"][0]["text"]
            try:
                output = data.get("output")
                if not isinstance(output, list) or len(output) < 1:
                    raise KeyError("missing or malformed 'output' list")
                item = output[1] if len(output) > 1 else output[0]
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
                raise ValueError(f"Unexpected response structure: {e}; response JSON: {json.dumps(data, ensure_ascii=False)}")

        except requests.RequestException as e:
            last_exception = e
            vim.eval('echo "LLM call falied"')
            # network error / timeout etc -> retry with backoff
            if attempt == max_attempts:
                break
            time.sleep(backoff_base * (2 ** (attempt - 1)))
            continue
        except Exception:
            # any other exception (parsing/structure), don't retry further
            raise

    # if we reach here, all retries failed
    err_msg = "Failed to complete LLM call after retries."
    if last_exception:
        raise RuntimeError(f"{err_msg} Last exception: {last_exception}. Last response body: {last_response_text}")
    else:
        raise RuntimeError(f"{err_msg} Last response body: {last_response_text}")


def _get_registry_text() -> tuple[str, str]:
    snippet = ''
    selected_registry = None
    for reg in ['0', '"', '+', '*']:
        try:
            val = vim.eval(f'getreg("{reg}")')
        except Exception:
            val = ''
        if isinstance(val, str) and val:
            snippet = val
            selected_registry = reg
            break
    return (snippet, selected_registry)


def mf_chat(user_prompt: str) -> None:
    content = _send_llm_call(prompt=user_prompt)
    escaped_content = content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    vim.command('tabnew LLMAnswer')
    vim.current.buffer[:] = content.splitlines()
    vim.command('echo "Done!"')


def mf_ai(user_prompt: str) -> None:
    snippet, selected_registry = _get_registry_text()
    
    prompt_to_send = f"""
        You are a python software developer.
           You receives User Input as instructions and a snippet what can be used for the newly generated code.
    User Input: {user_prompt}. Provided snippet: {snippet}
    """
    content = _send_llm_call(prompt=prompt_to_send)
    escaped_content = content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    vim.eval(f'setreg("{selected_registry}", "{escaped_content}")')
    vim.command('echo "Done!"')
    vim.command('tabnew LLMAnswer')
    vim.current.buffer[:] = content.splitlines()

    vim.command('setlocal filetype=python')

def _is_hidden(path: Union[str, Path]) -> bool:  
    p = Path(path)  
    if p.name.startswith('.'):  
        return True  
    if os.name == 'nt':  
        try:  
            import ctypes  
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))  
            if attrs == -1:  
                return False  
            FILE_ATTRIBUTE_HIDDEN = 0x02  
            return bool(attrs & FILE_ATTRIBUTE_HIDDEN)  
        except Exception:  
            return False  
    return False  
  
def _list_files(folder: Union[str, Path], *, follow_symlinks: bool = False) -> List[str]:  
    root = Path(folder)  
    if not root.is_dir():  
        raise NotADirectoryError(f"{root!s} is not a directory")  
  
    files: List[str] = []  
    for entry in root.iterdir():  
        if _is_hidden(entry):  
            continue  
        if entry.is_symlink() and not follow_symlinks:  
            continue  
        if entry.is_dir():  
            files.extend(_list_files(entry, follow_symlinks=follow_symlinks))  
        elif entry.is_file():  
            files.append(str(entry))  
    return files  

def _python_filter(files: list) -> list:
    return [
        f
        for f in files
        if "__pycache__" not in f
    ]


def mf_refactor(user_prompt: str) -> None:
    # current_path = vim.eval("@%")
    folder, user_input = user_prompt.split(" ", 1)
    files = _list_files(folder)
    files = _python_filter(files)
    codebase = ""
    for fname in files:
        with open(fname) as f:
            codebase += f"======\n{fname}\n=======\n{f.read()}\n========" 

    prompt_to_send = f"""
        You are a senior software developer.
           You receives user_input as instructions and the codebase from a repository with module paths.
        Your jobs are the following:
        1. understand the folder structure and functionalities of the given codebase.
        2. understand the user_input. It can be a new feature request, a bug report or change on the existing codebase
        3. provide solution which fullfill the user_input
        4. the output must be in the following format:
            - the format is markdown
            - an example:
        # src/mymodule.py
           An explanation of the change, what news are implemented in it
           ```python
           def mydefinition(string: str):
               print(string)
           ```
        Section user_input: {user_input}. Section codebase: {codebase}
    """
    content = _send_llm_call(prompt=prompt_to_send)
    escaped_content = content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    vim.command('echo "Done!"')
    vim.command('tabnew LLMAnswer')
    vim.current.buffer[:] = content.splitlines()
    vim.command('setlocal filetype=markdown')
    vim.command('%s/\\n/\r/g')

def mf_create_file(file_path: str) -> None:
    snippet, selected_registry = _get_registry_text()
    
    try:
        os.makedirs(os.path.dirname(file_path))
    except:
        pass

    with open(file_path, "w") as f:
        f.write(snippet)

EOF
" Expose :Mfs command that calls the Python function
command! -nargs=1 Mfai python3 mf_ai(vim.eval('<q-args>'))
command! -nargs=1 Mfch python3 mf_chat(vim.eval('<q-args>'))
command! -nargs=1 Mfref python3 mf_refactor(vim.eval('<q-args>'))
command! -nargs=1 Mfc python3 mf_create_file(vim.eval('<q-args>'))
