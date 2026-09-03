"""Bridge between Vim's embedded Python and the mfpy package.

LLM settings are taken only from Vim global variables. This module does not
read configuration from environment variables.

Supported Vim variables:

    let g:mfplugin_llm_url = 'https://example.com/v1/responses'
    let g:mfplugin_llm_api_key = '...'
    let g:mfplugin_llm_model = '...'
    let g:mfplugin_llm_timeout = 120
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import vim


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mfpy.vim_entrypoint import (  # noqa: E402
    build_result as build_mfpy_result,
)
from mfpy.vim_entrypoint import (  # noqa: E402
    revert_last_change as revert_mfpy_last_change,
)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _decode_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []

    return [_decode(value) for value in values]


def _vim_variable(name: str, default: Any = "") -> Any:
    try:
        return vim.vars[name]
    except KeyError:
        return default


def _vim_string(name: str, default: str = "") -> str:
    return _decode(_vim_variable(name, default))


def _vim_integer(name: str, default: int) -> int:
    raw_value = _vim_variable(name, default)

    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return default


def build_result(
    selected_files: list[str],
    user_input: str,
    save_output: bool,
    root_path: str,
) -> str:
    """Call mfpy with LLM settings provided by Vim globals."""

    llm_url = _vim_string("mfplugin_llm_url")
    llm_api_key = _vim_string("mfplugin_llm_api_key")
    llm_model = _vim_string("mfplugin_llm_model")
    timeout_seconds = _vim_integer("mfplugin_llm_timeout", 120)

    return build_mfpy_result(
        selected_files=_decode_list(selected_files),
        user_input=_decode(user_input),
        save_output=bool(save_output),
        root_path=_decode(root_path),
        llm_url=llm_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        timeout_seconds=timeout_seconds,
    )


def revert_last_change(root_path: str) -> str:
    return revert_mfpy_last_change(_decode(root_path))