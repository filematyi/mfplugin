" plugin/mf.vim
if !has('python3')
  echoerr 'Python3 support is required for mfplugin'
  finish
endif

" Define the Python function using Vim's embedded Python 3
python3 << EOF
import vim

def mf_hello():
    # Prints in the command line (message area)
    vim.command('echo "Hello world"')


def echo_first5_from_last_copy(parameter: str):
    text = ''
    for reg in ['0', '"', '+', '*']:
        try:
            val = vim.eval(f'getreg("{reg}")')
        except Exception:
            val = ''
        if isinstance(val, str) and val:
            text = val
            break

    first5 = text[:5]

    # Escape characters that can break :echo
    safe = first5.replace('\\', '\\\\').replace('"', r'\"')
    # Use :echo so it shows in the command area
    vim.command(f'echo "{parameter + safe}"')

EOF

" Expose :Mf command that calls the Python function
command! Mf python3 mf_hello()
command! -nargs=1 Mfcp python3 echo_first5_from_last_copy(vim.eval('<q-args>'))


