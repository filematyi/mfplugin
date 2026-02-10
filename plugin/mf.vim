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
    return response["choices"][0]["message"]["content"]


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

EOF
" Expose :Mfs command that calls the Python function
command! -nargs=1 Mfai python3 mf_ai(vim.eval('<q-args>'))
