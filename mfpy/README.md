# MfPlugin Tkinter application

This folder contains a standalone Python/Tkinter implementation of the Vim
plugin.

## Features

- Accepts a project folder as a command-line argument.
- Opens a folder chooser when no folder is supplied.
- Recursively displays selectable files and directories.
- Restores the previous input, selection, and save-output setting from
  `.mfhist`.
- Sends the same `input` and `model` request payload used by the Vim backend.
- Supports bearer-token and `api-key` authentication headers.
- Retries rate-limited and server-error responses.
- Can parse file blocks from an LLM response and save them under the selected
  project folder.
- Stores original file contents in `.mfhist`.
- Can revert the most recent saved-file operation.
- Performs network and revert operations on background threads so the Tkinter
  interface remains responsive.

## Requirements

Python 3.9 or newer is recommended. Tkinter must be available in the Python
installation.

Install the HTTP dependency:

```bash
python -m pip install -r mfpy/requirements.txt
```

On Debian or Ubuntu, Tkinter can be installed with:

```bash
sudo apt install python3-tk
```

## Configuration

Configure the LLM endpoint with environment variables:

```bash
export MFPLUGIN_URL=""
export MFPLUGIN_API_KEY=""
export MFPLUGIN_MODEL="gpt-56-sol"
```

The values can also be supplied as command-line options.

## Running

Run with a project folder:

```bash
python -m mfpy /path/to/project
```

Run without a folder to open the folder chooser:

```bash
python -m mfpy
```

Pass the LLM configuration directly:

```bash
python -m mfpy /path/to/project \
  --url "https://example.com/v1/responses" \
  --api-key "your-api-key" \
  --model "your-model"
```

The application writes `.mfhist` inside the selected project folder. This file
contains the UI state and the backup required by the Revert last change
button.
