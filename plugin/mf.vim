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


def mf_hello():
    # Prints in the command line (message area)
    vim.command('echo "Hello world"')


def echo_first5_from_last_copy(parameter: str):
    text = ''
    selected_registry = None
    for reg in ['0', '"', '+', '*']:
        try:
            val = vim.eval(f'getreg("{reg}")')
        except Exception:
            val = ''
        if isinstance(val, str) and val:
            text = val
            selected_registry = reg
            break

    first5 = text[:5]

    # Escape characters that can break :echo
    safe = first5.replace('\\', '\\\\').replace('"', r'\"')
    printout_string = parameter + " " + safe

    vim.eval(f'setreg("{selected_registry}", "{printout_string}")')
    # Use :echo so it shows in the command area
    vim.command(f'echo "{printout_string}"')


def mf_ai(user_prompt: str) -> None:
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
    url = vim.eval('g:mfplugin_url')
    api_key = vim.eval('g:mfplugin_api_key')
    prompt_to_send = f"""
    	You are a python software developer.
       	You receives User Input as instructions and a snippet what can be used for the newly generated code.
	The response must contain only the generated python code.
	tUser Input: {user_prompt}. Provided snippet: {snippet}
    """    
    headers = {
	'Content-Type': 'application/json',
	'api-key': api_key
    }
    payload={"messages":[{"role":"system","content":[{"type":"text","text":prompt_to_send}]}],"temperature":0.7,"top_p":0.95,"max_tokens":6553}
    data = requests.post(url, headers=headers, json=payload)
    response = data.json()
    content = response["choices"][0]["message"]["content"]
    escaped_content = content.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    vim.eval(f'setreg("{selected_registry}", "{escaped_content}")')
    vim.command('echo "Done!"')
	
    vim.command('enew')
    vim.current.buffer[:] = content.splitlines()

EOF
" Expose :Mf command that calls the Python function
command! Mf python3 mf_hello()
command! -nargs=1 Mfcp python3 echo_first5_from_last_copy(vim.eval('<q-args>'))
command! -nargs=1 Mfai python3 mf_ai(vim.eval('<q-args>'))

