"""
File Processing Skills - Google A2A SDK Implementation (A2A v1.0)

Demonstrates file handling with the official A2A SDK 1.x types.

v1.0: there is a single `Part` type whose content is a oneof:
  - text  (str)
  - raw   (bytes, e.g. file contents; base64 on the JSON wire)
  - url   (str, remote file reference)
  - data  (structured dict)
plus `filename` and `media_type` metadata fields.
"""

from typing import Any, Dict, Tuple

from a2a.types import Part


class FileProcessingError(Exception):
    """Error during file processing."""
    pass


def analyze_file(filename: str, mime_type: str, content_bytes: bytes) -> Dict[str, Any]:
    """
    Analyze a file and return statistics.

    Args:
        filename: Name of the file
        mime_type: MIME type of the file
        content_bytes: Raw file content

    Returns:
        File analysis statistics
    """
    try:
        # Try to decode as text
        content = content_bytes.decode('utf-8')
        lines = content.split('\n')
        words = content.split()

        return {
            "filename": filename,
            "mime_type": mime_type or "unknown",
            "size_bytes": len(content_bytes),
            "line_count": len(lines),
            "word_count": len(words),
            "character_count": len(content),
            "is_text": True,
            "preview": content[:200] + "..." if len(content) > 200 else content
        }
    except UnicodeDecodeError:
        # Binary file
        return {
            "filename": filename,
            "mime_type": mime_type or "application/octet-stream",
            "size_bytes": len(content_bytes),
            "line_count": None,
            "word_count": None,
            "character_count": None,
            "is_text": False,
            "preview": f"<Binary file: {len(content_bytes)} bytes>"
        }


def convert_to_upper(filename: str, content_bytes: bytes) -> Tuple[str, bytes]:
    """
    Convert file content to uppercase.

    Args:
        filename: Original filename
        content_bytes: File content

    Returns:
        Tuple of (new_filename, new_content)
    """
    try:
        content = content_bytes.decode('utf-8')
        upper_content = content.upper()

        # Generate output filename
        if '.' in filename:
            name, ext = filename.rsplit('.', 1)
            output_name = f"{name}_upper.{ext}"
        else:
            output_name = f"{filename}_upper"

        return output_name, upper_content.encode('utf-8')
    except UnicodeDecodeError:
        raise FileProcessingError("Cannot convert binary file to uppercase")


def generate_report(format: str) -> Tuple[str, str, bytes]:
    """
    Generate a sample report file.

    Args:
        format: File format (txt, csv, json)

    Returns:
        Tuple of (filename, mime_type, content)
    """
    if format == "csv":
        content = "name,value\nItem1,100\nItem2,200\nItem3,300"
        mime = "text/csv"
        filename = "report.csv"
    elif format == "json":
        content = '{"report": {"generated": "2024-01-01", "items": [{"name": "Item1", "value": 100}]}}'
        mime = "application/json"
        filename = "report.json"
    elif format == "txt":
        content = """REPORT
======
Generated: 2024-01-01

Summary:
- Item1: 100
- Item2: 200
- Item3: 300
"""
        mime = "text/plain"
        filename = "report.txt"
    else:
        raise FileProcessingError(f"Unknown format: {format}")

    return filename, mime, content.encode('utf-8')


def extract_file_from_part(part: Part) -> Tuple[str, str, bytes]:
    """
    Extract file information from a v1.0 Part.

    Files arrive either as raw bytes (Part.raw, base64 on the wire)
    or as a URL reference (Part.url, not supported by this example).

    Args:
        part: The Part from the A2A message

    Returns:
        Tuple of (filename, mime_type, content_bytes)
    """
    if part.HasField("raw"):
        filename = part.filename or "unknown"
        mime_type = part.media_type or "application/octet-stream"
        return filename, mime_type, bytes(part.raw)

    if part.HasField("url"):
        raise FileProcessingError(
            "File URL not supported, please send the file bytes (raw part)"
        )

    raise FileProcessingError("Part does not contain a file (raw or url)")


def create_file_part(filename: str, mime_type: str, content_bytes: bytes) -> Part:
    """
    Create a Part carrying a file for a response.

    Args:
        filename: Name of the file
        mime_type: MIME type
        content_bytes: Raw file content

    Returns:
        Part with raw content, ready to be added to a message or artifact
    """
    return Part(
        raw=content_bytes,
        filename=filename,
        media_type=mime_type,
    )


def create_text_part(text: str) -> Part:
    """Create a text Part."""
    return Part(text=text)


def create_data_part(data: Dict[str, Any]) -> Part:
    """Create a structured-data Part."""
    from a2a.helpers import new_data_part
    return new_data_part(data)
