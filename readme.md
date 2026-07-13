# MfPlugin

MfPlugin is a Vim plugin for selecting project files, sending them together with
a prompt to an LLM endpoint, and optionally applying AI-generated file changes
back to your project.

It opens a popup file picker, lets you select files or directories as context,
accepts free-form user input, and displays the LLM response in Vim.

## Features

- Popup-based file and directory selector
- Sends selected file contents as context to a configured LLM endpoint
- Optional save-output mode for writing AI-generated file blocks to disk
- Project-local `.mfhist` file for prompt history and revert data
- Revert support for the last saved AI-generated change
- Configurable path blacklist for directory expansion
- Vim help documentation included

## Requirements

- Vim with popup support
- Vim compiled with Python 3 support
- Python package: `requests`
- A compatible LLM API endpoint

Check Vim support:

```vim
:echo exists('*popup_create')
:echo has('python3')
```

Install the Python dependency:

```sh
python3 -m pip install requests
```

## Installation

Using vim-plug:

```vim
Plug 'filematyi/mfplugin'
```

Then run:

```vim
:PlugInstall
```

If your plugin manager does not generate helptags automatically, run:

```vim
:helptags ALL
```

Open the help document with:

```vim
:help mfplug
```

## Configuration

Add the required variables to your Vim configuration:

```vim
let g:mfplugin_url = 'https://example.openai.azure.com/openai/responses?api-version=2024-xx-xx'
let g:mfplugin_api_key = 'your-api-key'
let g:mfplugin_model = 'gpt-4.1'
```

Optional path blacklist used when selected directories are expanded:

```vim
let g:mfplugin_file_blacklist = [
      \ '.git',
      \ 'node_modules',
      \ '__pycache__',
      \ '.venv',
      \ 'dist',
      \ 'build',
      \ ]
```

If `g:mfplugin_file_blacklist` is not set, MfPlugin uses a built-in default
blacklist for common generated or local-only directories.

## Usage

Open MfPlugin in the current working directory:

```vim
:Mf
```

Open MfPlugin for a specific directory:

```vim
:Mf /path/to/project
```

Typical workflow:

1. Run `:Mf`.
2. Select files or directories with `<Leader>1`.
3. Type your prompt.
4. Optionally toggle save-output mode with `<Leader>2`.
5. Press `<Enter>` to submit.
6. Read the result popup.
7. Press `<Esc>` to close the result popup.

## Main popup controls

| Key | Action |
| --- | --- |
| `<Up>` | Move cursor up |
| `<Down>` | Move cursor down |
| `<Left>` | Move input cursor left |
| `<Right>` | Move input cursor right |
| `<Leader>1` | Toggle current file or directory |
| `<Leader>2` | Toggle save-output mode |
| `<Leader>3` | Clear input |
| `<Leader>4` | Revert last saved change |
| `<BS>` | Delete character before input cursor |
| `<Del>` / `<C-D>` | Delete character under input cursor |
| `<Enter>` | Submit request |
| `<Esc>` | Close popup |

## Save-output mode

When save-output mode is enabled, MfPlugin asks the LLM to respond with file
blocks in this format:

```text
