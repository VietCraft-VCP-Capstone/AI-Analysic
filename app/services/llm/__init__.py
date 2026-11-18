"""Gói LLM dùng chung: `from app.services.llm import generate_json, generate_text, available`."""

from app.services.llm.client import available, generate_json, generate_text

__all__ = ["available", "generate_json", "generate_text"]
