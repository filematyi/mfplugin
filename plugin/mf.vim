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
     


def _send_llm_call(prompt: str) -> str:
    url = vim.eval('g:mfplugin_url')
    api_key = vim.eval('g:mfplugin_api_key')
    headers = {
	'Content-Type': 'application/json',
	'api-key': api_key
    }
    payload={
        "messages": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "temperature": 0.7,
        "top_p": 0.95,
        "max_tokens": 6553
    }
    data = requests.post(url, headers=headers, json=payload)
    response = data.json()
    try:
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        print(response)
        raise e

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

    vim.command('echo "Done!"')
    vim.command('enew')
    vim.current.buffer[:] = content.splitlines()


def mf_ai(user_prompt: str) -> None:
    snippet, selected_registry = _get_registry_text()
    
    prompt_to_send = f"""
    	You are a python software developer.
       	You receives User Input as instructions and a snippet what can be used for the newly generated code.
	The response must contain only the generated python code.
	User Input: {user_prompt}. Provided snippet: {snippet}
    """
    content = _send_llm_call(prompt=prompt_to_send)
    escaped_content = content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    vim.eval(f'setreg("{selected_registry}", "{escaped_content}")')
    vim.command('echo "Done!"')
	
    vim.command('enew')
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
    files = _list_files(".")
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
        4. the output must be in the same format as the codebase section. You don't have to explain the changes.
            Just provide a list where the first element is the filepath, second element is a markdown snippet block.
            For already existing modules, sow the whole module not just the changes lines.
            For new modules show the whole module.
	Section user_input: {user_input}. Section codebase: {codebase}
    """
    content = _send_llm_call(prompt=prompt_to_send)
    escaped_content = content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    vim.command('echo "Done!"')
    vim.command('enew')
    vim.current.buffer[:] = content.splitlines()


EOF
" Expose :Mfs command that calls the Python function
command! -nargs=1 Mfai python3 mf_ai(vim.eval('<q-args>'))
command! -nargs=1 Mfch python3 mf_chat(vim.eval('<q-args>'))
command! -nargs=1 Mfref python3 mf_refactor(vim.eval('<q-args>'))
