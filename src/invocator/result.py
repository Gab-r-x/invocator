from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error_message: str | None = None
    error_context: dict[str, str] = Field(default_factory=dict)
    error_code: str | None = None
    error_grouping_prefix: str | None = None

    def add_context(self, *, key: str, value: str) -> "Result[T]":
        self.error_context[key] = value
        return self

    def get_error_message(self) -> str:
        if self.success:
            return ""
        parts: list[str] = []
        if self.error_code:
            parts.append(f"[{self.error_code}]")
        if self.error_message:
            parts.append(self.error_message)
        if self.error_context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.error_context.items())
            parts.append(f"({context_str})")
        return " ".join(parts)
