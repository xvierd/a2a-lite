"""
Multi-modal parts support (Text, File, Data).

OPTIONAL - Only use if you need files or structured data.
Simple text skills work without any of this.

Example (simple - no parts needed):
    @agent.skill("greet")
    async def greet(name: str) -> str:
        return f"Hello, {name}!"

Example (with files - opt-in):
    from a2a_lite import FilePart, DataPart

    @agent.skill("summarize")
    async def summarize(document: FilePart) -> str:
        content = await document.read_text()
        return summarize(content)
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Union


@dataclass
class TextPart:
    """Simple text content."""

    text: str

    def to_a2a(self) -> dict[str, Any]:
        return {"text": self.text}

    @classmethod
    def from_a2a(cls, data: dict) -> TextPart:
        return cls(text=data.get("text", ""))


@dataclass
class FilePart:
    """
    File content - can be bytes or a URI.

    Example:
        @agent.skill("process")
        async def process(file: FilePart) -> str:
            if file.is_uri:
                # Download from URI
                content = await fetch(file.uri)
            else:
                # Use bytes directly
                content = file.data

            return process_content(content)
    """

    name: str
    mime_type: str = "application/octet-stream"
    data: bytes | None = None
    uri: str | None = None

    @property
    def is_uri(self) -> bool:
        return self.uri is not None

    @property
    def is_bytes(self) -> bool:
        return self.data is not None

    async def read_bytes(self) -> bytes:
        """Read file content as bytes."""
        if self.data:
            return self.data
        if self.uri:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(self.uri)
                response.raise_for_status()
                return response.content
        raise ValueError("FilePart has no data or URI")

    async def read_text(self, encoding: str = "utf-8") -> str:
        """Read file content as text."""
        data = await self.read_bytes()
        return data.decode(encoding)

    def to_a2a(self) -> dict[str, Any]:
        if self.uri:
            return {
                "url": self.uri,
                "filename": self.name,
                "mediaType": self.mime_type,
            }
        else:
            return {
                "raw": base64.b64encode(self.data or b"").decode(),
                "filename": self.name,
                "mediaType": self.mime_type,
            }

    @classmethod
    def from_a2a(cls, data: dict) -> FilePart:
        bytes_data = data.get("raw")
        return cls(
            name=data.get("filename", "unknown"),
            mime_type=data.get("mediaType", "application/octet-stream"),
            data=base64.b64decode(bytes_data) if bytes_data else None,
            uri=data.get("url"),
        )

    @classmethod
    def from_path(cls, path: Union[str, Path], mime_type: str | None = None) -> FilePart:
        """Create FilePart from a local file path."""
        path = Path(path)
        if mime_type is None:
            import mimetypes

            mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        return cls(
            name=path.name,
            mime_type=mime_type,
            data=path.read_bytes(),
        )


@dataclass
class DataPart:
    """
    Structured JSON data.

    Example:
        @agent.skill("analyze")
        async def analyze(data: DataPart) -> DataPart:
            result = process(data.data)
            return DataPart(data=result)
    """

    data: dict[str, Any]
    mime_type: str = "application/json"

    def to_a2a(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "mediaType": self.mime_type,
        }

    @classmethod
    def from_a2a(cls, data: dict) -> DataPart:
        return cls(data=data.get("data", {}))


@dataclass
class Artifact:
    """
    Rich output artifact.

    Use when you need more than just text/JSON return.

    Example:
        @agent.skill("generate_report")
        async def generate_report(query: str) -> Artifact:
            return Artifact(
                name="report.pdf",
                parts=[
                    TextPart("Summary: ..."),
                    FilePart.from_path("report.pdf"),
                ],
            )
    """

    name: str | None = None
    description: str | None = None
    parts: list = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_text(self, text: str) -> Artifact:
        """Add text to artifact."""
        self.parts.append(TextPart(text=text))
        return self

    def add_file(self, file: FilePart) -> Artifact:
        """Add file to artifact."""
        self.parts.append(file)
        return self

    def add_data(self, data: dict[str, Any]) -> Artifact:
        """Add structured data to artifact."""
        self.parts.append(DataPart(data=data))
        return self

    def to_a2a(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parts": [p.to_a2a() for p in self.parts],
            "metadata": self.metadata,
        }


# Helper to parse incoming parts
def parse_part(data: dict) -> Union[TextPart, FilePart, DataPart]:
    """Parse an A2A v1.0 part dict into the appropriate Part type.

    Part content is detected by presence of the content key:
    ``text`` / ``data`` / ``raw`` or ``url`` (file parts).
    """
    if "text" in data:
        return TextPart.from_a2a(data)
    elif "data" in data:
        return DataPart.from_a2a(data)
    elif "raw" in data or "url" in data:
        return FilePart.from_a2a(data)
    else:
        # Default to text
        return TextPart(text=str(data))
