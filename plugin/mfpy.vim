if exists('g:loaded_mfpy_command')
  finish
endif
let g:loaded_mfpy_command = 1

let s:plugin_root = fnamemodify(
      \ resolve(expand('<sfile>:p')),
      \ ':h:h')
let s:mfpy_job = v:null

command! -nargs=0 Mfpy call s:launch_mfpy()

function! s:python_executable() abort
  if exists('g:mfpy_python') && !empty(g:mfpy_python)
    return g:mfpy_python
  endif

  if executable('python3')
    return exepath('python3')
  endif

  if executable('python')
    return exepath('python')
  endif

  return ''
endfunction

function! s:job_error(channel, message) abort
  if !empty(a:message)
    echohl ErrorMsg
    echom 'Mfpy: ' . a:message
    echohl None
  endif
endfunction

function! s:job_exit(job, status) abort
  if a:status != 0
    echohl ErrorMsg
    echom 'Mfpy exited with status ' . a:status
    echohl None
  endif
endfunction

function! s:launch_mfpy() abort
  if !exists('*job_start')
    echoerr 'Mfpy requires Vim job support.'
    return
  endif

  let l:python = s:python_executable()
  if empty(l:python)
    echoerr 'Mfpy could not find Python 3. Set g:mfpy_python to its executable path.'
    return
  endif

  let l:folder = fnamemodify(getcwd(), ':p')
  if !isdirectory(l:folder)
    echoerr 'Mfpy cannot open the current directory: ' . l:folder
    return
  endif

    

  let l:command = [l:python, '-m', 'mfpy', l:folder]
  let s:mfpy_job = job_start(l:command, {
        \ 'cwd': s:plugin_root,
        \ 'in_io': 'null',
        \ 'out_io': 'null',
        \ 'err_io': 'pipe',
        \ 'err_cb': function('s:job_error'),
        \ 'exit_cb': function('s:job_exit'),
        \ })

  if job_status(s:mfpy_job) ==# 'fail'
    echoerr 'Mfpy failed to start.'
    return
  endif

  echom 'Mfpy opened for: ' . l:folder
endfunction
