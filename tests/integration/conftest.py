"""Integration-test helpers — exercise the REAL backends, skip cleanly when absent.

These tests run the actual seams against real langgraph / mlflow / opentelemetry / ollama /
qdrant / postgres rather than mocks, so the backend code paths (the per-seam audits' coverage
gaps) are genuinely executed. Each skips when its extra or live service is unavailable, so the
dependency-free `.[dev]` lane still passes; the extras CI lane runs them for real.
"""

from __future__ import annotations

import importlib.util
import socket
import urllib.request

import pytest


def have(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except Exception:
        return False


def ollama_up() -> bool:
    return have("langchain_ollama") and http_ok("http://localhost:11434/api/tags")


def qdrant_up() -> bool:
    return have("qdrant_client") and tcp_open("localhost", 6333)


def postgres_up() -> bool:
    return have("psycopg") and tcp_open("localhost", 5432)


@pytest.fixture
def require_ollama():
    if not ollama_up():
        pytest.skip("ollama not available on localhost:11434")
