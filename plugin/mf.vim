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
EOF

" Expose :Mf command that calls the Python function
command! Mf python3 mf_hello()
