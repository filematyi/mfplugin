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
    model = vim.eval('g:mfplugin_model')
    headers = {
	'Content-Type': 'application/json',
	'Authorization': f'Bearer {api_key}'
    }
    payload={
        "input": prompt,
        "model": model
    }
    data = requests.post(url, headers=headers, json=payload)
    response = data.json()
    try:
        return response["output"][1]["content"][0]["text"]
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

    # Open a new tab (created at the end) and ensure it's a single full-screen window
    vim.command('tabnew')
    vim.command('tabonly')

    # Put the generated content into the new tab's buffer
    vim.current.buffer[:] = content.splitlines()

    vim.command('echo "Done!"')


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
    vim.command('enew')
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
