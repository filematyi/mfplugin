"""Entry points used by the Vim plugin.

Vim passes the LLM configuration explicitly. Environment variables are not
read by this module.
"""

from __future__ import annotations

from .backend import MfBackend, MfConfig


def build_result(
    selected_files: list[str],
    user_input: str,
    save_output: bool,
    root_path: str,
    llm_url: str,
    llm_api_key: str,
    llm_model: str,
    timeout_seconds: int = 120,
) -> str:
    """Build an LLM result using configuration supplied by Vim."""

    config = MfConfig(
        url=llm_url,
        api_key=llm_api_key,
        model=llm_model,
        timeout_seconds=max(1, int(timeout_seconds)),
    )

    backend = MfBackend(root_path, config)
    return backend.build_result(
        selected_files,
        user_input,
        save_output,
    )


def revert_last_change(root_path: str) -> str:
    """Revert the latest file change.

    Reverting does not make an LLM request, so no LLM configuration is
    required.
    """

    config = MfConfig(
        url="",
        api_key="",
        model="",
    )
    backend = MfBackend(root_path, config)
    return backend.revert_last_change()