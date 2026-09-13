"""Remote LLM communication service."""

from __future__ import annotations

import json
import time
from typing import Any

import requests

from ..schemas import MfConfig


class LlmService:
    """Send prompts to the configured LLM endpoint."""

    def __init__(self, config: MfConfig) -> None:
        """Initialize the service."""
        self.config = config

    @staticmethod
    def _extract_text(data: Any) -> str:
        if not isinstance(data, dict):
            raise ValueError("Unexpected response structure: expected object.")

        output = data.get("output")
        if not isinstance(output, list) or not output:
            raise ValueError(
                "Unexpected response structure: missing or malformed "
                "'output' list."
            )

        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for candidate in content:
                if (
                    isinstance(candidate, dict)
                    and isinstance(candidate.get("text"), str)
                ):
                    return candidate["text"]

        raise ValueError(
            "Unexpected response structure: no text field found; "
            f"response JSON: {json.dumps(data, ensure_ascii=False)}"
        )

    def _backoff(self, attempt: int) -> float:
        return self.config.backoff_base * (2 ** (attempt - 1))

    def send(self, prompt: str) -> str:
        """Send a prompt and return the first text response.

        Raises:
            ValueError: If the prompt or response is invalid.
            RuntimeError: If all HTTP attempts fail.
        """
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt must be a non-empty string.")

        self.config.validate()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "api-key": self.config.api_key,
        }
        payload = {"input": prompt, "model": self.config.model}
        last_exception: requests.RequestException | None = None
        last_response_text: str | None = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                response = requests.post(
                    self.config.url,
                    headers=headers,
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
                last_response_text = response.text

                if response.status_code == 429:
                    if attempt == self.config.max_attempts:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    try:
                        wait = float(retry_after)
                    except (TypeError, ValueError):
                        wait = self._backoff(attempt)
                    time.sleep(max(0, wait))
                    continue

                if 500 <= response.status_code < 600:
                    if attempt == self.config.max_attempts:
                        response.raise_for_status()
                    time.sleep(self._backoff(attempt))
                    continue

                if not 200 <= response.status_code < 300:
                    raise requests.HTTPError(
                        "Unexpected status code: "
                        f"{response.status_code}; body: {response.text}",
                        response=response,
                    )

                try:
                    data = response.json()
                except requests.exceptions.JSONDecodeError as error:
                    raise ValueError(
                        "Response is not valid JSON: "
                        f"{error}; body: {response.text}"
                    ) from error

                return self._extract_text(data)
            except requests.RequestException as error:
                last_exception = error
                if attempt < self.config.max_attempts:
                    time.sleep(self._backoff(attempt))

        message = "Failed to complete LLM call after retries."
        if last_exception is not None:
            raise RuntimeError(
                f"{message} Last exception: {last_exception}. "
                f"Last response body: {last_response_text}"
            ) from last_exception

        raise RuntimeError(
            f"{message} Last response body: {last_response_text}"
        )