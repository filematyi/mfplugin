if exists('g:loaded_problem_files')
  finish
endif
let g:loaded_problem_files = 1

let s:script_dir = fnamemodify(resolve(expand('<sfile>:p')), ':h')
let s:state = {}

command! -nargs=? Mf call s:open_problem_files(<q-args>)

function! s:relative_to_root(root, path) abort
  let l:root = fnamemodify(a:root, ':p')
  let l:path = fnamemodify(a:path, ':p')

  if stridx(l:path, l:root) == 0
    return strpart(l:path, strlen(l:root))
  endif

  return fnamemodify(l:path, ':.')
endfunction

function! s:popup_dimensions() abort
  let l:width = max([1, float2nr(&columns * 0.9)])
  let l:height = max([1, float2nr(&lines * 0.7)])

  return {
        \ 'width': l:width,
        \ 'height': l:height,
        \ 'line': max([1, float2nr((&lines - l:height) / 2.0) + 1]),
        \ 'col': max([1, float2nr((&columns - l:width) / 2.0) + 1]),
        \ }
endfunction

function! s:leader_key() abort
  let l:leader = get(g:, 'mapleader', '\')
  return empty(l:leader) ? '\' : l:leader
endfunction

function! s:leader_label() abort
  let l:leader = s:leader_key()

  if l:leader ==# ' '
    return '<Space>'
  endif

  if l:leader ==# "\t"
    return '<Tab>'
  endif

  return l:leader
endfunction

function! s:read_history_input(histfile) abort
  if !filereadable(a:histfile)
    return ''
  endif

  let l:raw = join(readfile(a:histfile), "\n")

  " New .mfhist format is JSON:
  " {
  "   "version": 1,
  "   "user_input": "...",
  "   "last_change": { ... }
  " }
  "
  " Keep backward compatibility with the old format where .mfhist
  " contained only the raw user input.
  if exists('*json_decode')
    try
      let l:decoded = json_decode(l:raw)
      if type(l:decoded) == type({}) && has_key(l:decoded, 'user_input')
        return type(l:decoded.user_input) == type('') ? l:decoded.user_input : string(l:decoded.user_input)
      endif
    catch
      " Old raw text format or invalid JSON. Fall through.
    endtry
  endif

  return l:raw
endfunction

function! s:open_problem_files(root) abort
  if !exists('*popup_create')
    echoerr 'This plugin requires Vim with popup support.'
    return
  endif

  let l:root = empty(a:root) ? getcwd() : fnamemodify(a:root, ':p')
  let l:root = fnamemodify(l:root, ':p')

  if !isdirectory(l:root)
    echoerr 'Invalid directory: ' . l:root
    return
  endif

  " Check for .mfhist in the root directory
  let l:histfile = l:root . '/.mfhist'
  let l:initial_input = ''

  if filereadable(l:histfile)
    echom '.mfhist found: ' . l:histfile
    let l:initial_input = s:read_history_input(l:histfile)
  else
    echom '.mfhist not found in: ' . l:root
  endif

  let l:entries = globpath(l:root, '**/*', 0, 1)

  " Remove anything inside node_modules, including the node_modules directory itself
  let l:entries = filter(l:entries, 'v:val !~# ''\v(^|[\/\\])node_modules([\/\\]|$)''')

  " Hide the history file from the selectable file list. It is managed by the plugin.
  let l:entries = filter(l:entries, 'fnamemodify(v:val, ":t") !=# ''.mfhist''')

  " Keep both readable files and directories
  let l:entries = filter(l:entries, 'filereadable(v:val) || isdirectory(v:val)')

  " Convert to paths relative to the chosen root directory
  let l:entries = map(l:entries, 's:relative_to_root(l:root, v:val)')

  " Optional: add trailing slash to directories for clarity
  let l:entries = map(l:entries, 'isdirectory(fnamemodify(l:root . "/" . v:val, ":p")) ? v:val . "/" : v:val')

  let l:files = l:entries
  if empty(l:files)
    echo 'No files found.'
    return
  endif

  let l:popup = s:popup_dimensions()

  let s:state = {
        \ 'root': l:root,
        \ 'files': l:files,
        \ 'selected': {},
        \ 'cursor': 0,
        \ 'offset': 0,
        \ 'height': max([1, l:popup.height - 6]),
        \ 'input': l:initial_input,
        \ 'input_cursor': strchars(l:initial_input),
        \ 'save_output': 0,
        \ 'pending_leader': 0,
        \ }

  let l:lines = s:render_lines()
  let s:state.winid = popup_create(l:lines, {
        \ 'title': ' MfPlugin ',
        \ 'line': l:popup.line,
        \ 'col': l:popup.col,
        \ 'minwidth': l:popup.width,
        \ 'maxwidth': l:popup.width,
        \ 'minheight': l:popup.height,
        \ 'maxheight': l:popup.height,
        \ 'border': [],
        \ 'padding': [0,1,0,1],
        \ 'mapping': 0,
        \ 'filter': function('s:popup_filter'),
        \ })

  call s:redraw()
endfunction

function! s:input_len() abort
  return strchars(get(s:state, 'input', ''))
endfunction

function! s:clamp_input_cursor() abort
  let s:state.input_cursor = max([0, min([s:input_len(), get(s:state, 'input_cursor', 0)])])
endfunction

function! s:render_lines() abort
  call s:clamp_input_cursor()

  let l:lines = []
  let l:max = min([len(s:state.files), s:state.offset + s:state.height])

  for l:i in range(s:state.offset, l:max - 1)
    let l:mark = has_key(s:state.selected, l:i) ? '[x]' : '[ ]'
    let l:pointer = (l:i == s:state.cursor) ? '>' : ' '
    call add(l:lines, printf('%s %s %s', l:pointer, l:mark, s:state.files[l:i]))
  endfor

  call add(l:lines, repeat('─', 76))
  call add(l:lines, 'Save output? ' . (s:state.save_output ? '[x]' : '[ ]'))

  let l:prefix = 'Input: '
  let l:input_display = l:prefix . s:state.input
  let l:cursor_col = strchars(l:prefix) + s:state.input_cursor
  let l:input_display = strcharpart(l:input_display, 0, l:cursor_col) . '|' . strcharpart(l:input_display, l:cursor_col)

  call add(l:lines, l:input_display)
  call add(l:lines, '↓/↑: move | <Leader>1: toggle file | <Leader>2: toggle save output')
  call add(l:lines, '<Leader>3: clear input | <Leader>4: revert last change | Leader: ' . s:leader_label())
  call add(l:lines, 'Type: input | <BS>/<Del>: backspace | <C-D>: delete | <Enter>: submit | ESC: quit')
  return l:lines
endfunction

function! s:redraw() abort
  if has_key(s:state, 'winid')
    call popup_settext(s:state.winid, s:render_lines())
  endif
endfunction

function! s:move_cursor(delta) abort
  let l:new = s:state.cursor + a:delta
  let l:new = max([0, min([len(s:state.files) - 1, l:new])])
  let s:state.cursor = l:new

  if s:state.cursor < s:state.offset
    let s:state.offset = s:state.cursor
  elseif s:state.cursor >= s:state.offset + s:state.height
    let s:state.offset = s:state.cursor - s:state.height + 1
  endif

  call s:redraw()
endfunction

function! s:toggle_current() abort
  let l:i = s:state.cursor
  if has_key(s:state.selected, l:i)
    call remove(s:state.selected, l:i)
  else
    let s:state.selected[l:i] = 1
  endif
  call s:redraw()
endfunction

function! s:toggle_save_output() abort
  let s:state.save_output = !s:state.save_output
  call s:redraw()
endfunction

function! s:clear_input() abort
  let s:state.input = ''
  let s:state.input_cursor = 0
  call s:redraw()
endfunction

function! s:insert_input_char(char) abort
  call s:clamp_input_cursor()

  let l:before = strcharpart(s:state.input, 0, s:state.input_cursor)
  let l:after = strcharpart(s:state.input, s:state.input_cursor)
  let s:state.input = l:before . a:char . l:after
  let s:state.input_cursor += strchars(a:char)
  call s:redraw()
endfunction

function! s:backspace_input() abort
  call s:clamp_input_cursor()

  if s:state.input_cursor <= 0
    return
  endif

  let l:before = strcharpart(s:state.input, 0, s:state.input_cursor - 1)
  let l:after = strcharpart(s:state.input, s:state.input_cursor)
  let s:state.input = l:before . l:after
  let s:state.input_cursor -= 1
  call s:redraw()
endfunction

function! s:delete_input_char() abort
  call s:clamp_input_cursor()

  if s:state.input_cursor >= s:input_len()
    return
  endif

  let l:before = strcharpart(s:state.input, 0, s:state.input_cursor)
  let l:after = strcharpart(s:state.input, s:state.input_cursor + 1)
  let s:state.input = l:before . l:after
  call s:redraw()
endfunction

function! s:move_input_cursor(delta) abort
  let s:state.input_cursor = max([0, min([s:input_len(), s:state.input_cursor + a:delta])])
  call s:redraw()
endfunction

function! s:show_text_popup(title, text) abort
  let l:content_lines = s:text_to_lines(a:text)
  let l:popup = s:popup_dimensions()

  let l:lines = ['']
  call extend(l:lines, l:content_lines)
  call extend(l:lines, ['', 'Press <Esc> to close'])
  call extend(l:lines, ['Use arrows, PgUp/PgDn, mouse wheel to scroll'])

  call popup_create(l:lines, {
        \ 'title': a:title,
        \ 'line': l:popup.line,
        \ 'col': l:popup.col,
        \ 'minwidth': l:popup.width,
        \ 'maxwidth': l:popup.width,
        \ 'minheight': l:popup.height,
        \ 'maxheight': l:popup.height,
        \ 'border': [],
        \ 'padding': [0,1,0,1],
        \ 'mapping': 0,
        \ 'wrap': 1,
        \ 'scrollbar': 1,
        \ 'filter': function('s:result_popup_filter'),
        \ })
endfunction

function! s:show_result_popup(selected_files, user_input, save_output) abort
  let l:python_output = s:call_python_backend(a:selected_files, a:user_input, a:save_output)
  call s:show_text_popup(' Results ', l:python_output)
endfunction

function! s:result_popup_filter(winid, key) abort
  if a:key ==# "\<Esc>"
    call popup_close(a:winid)
    return 1
  endif

  if a:key ==# "\<Down>"
        \ || a:key ==# "\<C-E>"
        \ || a:key ==# "\<ScrollWheelDown>"
    call win_execute(a:winid, "normal! \<C-E>")
    return 1
  endif

  if a:key ==# "\<Up>"
        \ || a:key ==# "\<C-Y>"
        \ || a:key ==# "\<ScrollWheelUp>"
    call win_execute(a:winid, "normal! \<C-Y>")
    return 1
  endif

  if a:key ==# "\<PageDown>" || a:key ==# "\<C-F>"
    call win_execute(a:winid, "normal! \<C-F>")
    return 1
  endif

  if a:key ==# "\<PageUp>" || a:key ==# "\<C-B>"
    call win_execute(a:winid, "normal! \<C-B>")
    return 1
  endif

  if a:key ==# "\<C-D>"
    call win_execute(a:winid, "normal! \<C-D>")
    return 1
  endif

  if a:key ==# "\<C-U>"
    call win_execute(a:winid, "normal! \<C-U>")
    return 1
  endif

  return 0
endfunction

function! s:submit() abort
  let l:selected_files = []
  for l:i in sort(map(keys(s:state.selected), 'str2nr(v:val)'))
    call add(l:selected_files, s:state.files[l:i])
  endfor

  let l:user_input = s:state.input
  let l:save_output = s:state.save_output

  call popup_close(s:state.winid)
  call s:show_result_popup(l:selected_files, l:user_input, l:save_output)
endfunction

function! s:revert_last_change() abort
  let l:root = s:state.root

  if has_key(s:state, 'winid')
    call popup_close(s:state.winid)
  endif

  let l:result = s:call_python_revert(l:root)
  call s:show_text_popup(' Revert last change ', l:result)
endfunction

function! s:handle_leader_command(key) abort
  if a:key ==# '1'
    call s:toggle_current()
    return 1
  endif

  if a:key ==# '2'
    call s:toggle_save_output()
    return 1
  endif

  if a:key ==# '3'
    call s:clear_input()
    return 1
  endif

  if a:key ==# '4'
    call s:revert_last_change()
    return 1
  endif

  return 0
endfunction

function! s:popup_filter(winid, key) abort
  let l:skip_leader_detection = 0

  if get(s:state, 'pending_leader', 0)
    let s:state.pending_leader = 0

    if s:handle_leader_command(a:key)
      return 1
    endif

    if strchars(s:leader_key()) == 1
      call s:insert_input_char(s:leader_key())
    endif

    let l:skip_leader_detection = 1
  endif

  if !l:skip_leader_detection && a:key ==# s:leader_key()
    let s:state.pending_leader = 1
    return 1
  elseif a:key ==# "\<Down>"
    call s:move_cursor(1)
  elseif a:key ==# "\<Up>"
    call s:move_cursor(-1)
  elseif a:key ==# "\<Left>"
    call s:move_input_cursor(-1)
  elseif a:key ==# "\<Right>"
    call s:move_input_cursor(1)
  elseif a:key ==# "\<BS>"
    call s:backspace_input()
  elseif a:key ==# "\<Del>"
    call s:delete_input_char()
  elseif a:key ==# "\<CR>"
    call s:submit()
  elseif a:key ==# "\<Esc>"
    call popup_close(a:winid)
  elseif a:key ==# ' '
    call s:insert_input_char(' ')
  elseif strchars(a:key) == 1
    call s:insert_input_char(a:key)
  endif
  return 1
endfunction

function! s:call_python_backend(selected_files, user_input, save_output) abort
  if !has('python3')
    return 'Python support is not available in this Vim.'
  endif

  let g:problem_files_py_selected_files = a:selected_files
  let g:problem_files_py_user_input = a:user_input
  let g:problem_files_py_save_output = a:save_output
  let g:problem_files_py_plugin_dir = s:script_dir
  let g:problem_files_py_root = get(s:state, 'root', getcwd())

python3 << EOF
import sys
import vim
import os

plugin_dir = vim.vars['problem_files_py_plugin_dir']
str_plugin_dir = plugin_dir.decode("utf-8") if isinstance(plugin_dir, bytes) else str(plugin_dir)
python_dir = os.path.join(str_plugin_dir, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from mypythonscript import build_result

selected_files = list(vim.vars['problem_files_py_selected_files'])
user_input_raw = vim.vars['problem_files_py_user_input']
user_input = user_input_raw.decode('utf-8') if isinstance(user_input_raw, bytes) else str(user_input_raw)
save_output = bool(int(vim.vars['problem_files_py_save_output']))
root_raw = vim.vars['problem_files_py_root']
root_path = root_raw.decode('utf-8') if isinstance(root_raw, bytes) else str(root_raw)

result = build_result(selected_files, user_input, save_output, root_path)
vim.vars['problem_files_py_result'] = result
EOF

  return get(g:, 'problem_files_py_result', '')
endfunction

function! s:call_python_revert(root) abort
  if !has('python3')
    return 'Python support is not available in this Vim.'
  endif

  let g:problem_files_py_plugin_dir = s:script_dir
  let g:problem_files_py_root = a:root

python3 << EOF
import sys
import vim
import os

plugin_dir = vim.vars['problem_files_py_plugin_dir']
str_plugin_dir = plugin_dir.decode("utf-8") if isinstance(plugin_dir, bytes) else str(plugin_dir)
python_dir = os.path.join(str_plugin_dir, 'python')
if python_dir not in sys.path:
    sys.path.insert(0, python_dir)

from mypythonscript import revert_last_change

root_raw = vim.vars['problem_files_py_root']
root_path = root_raw.decode('utf-8') if isinstance(root_raw, bytes) else str(root_raw)

result = revert_last_change(root_path)
vim.vars['problem_files_py_revert_result'] = result
EOF

  return get(g:, 'problem_files_py_revert_result', '')
endfunction

function! s:text_to_lines(text) abort
  return split(a:text, "\n", 1)
endfunction
