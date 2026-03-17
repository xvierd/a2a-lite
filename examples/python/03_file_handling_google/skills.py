"""
File Processing Skills - Google A2A SDK Implementation

Demonstrates file handling using the official A2A SDK types.
"""

import base64
from typing import Any, Dict, Tuple

from a2a.types import FilePart, FileWithBytes, TextPart, DataPart


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


def extract_file_from_part(file_part: FilePart) -> Tuple[str, str, bytes]:
    """
    Extract file information from an A2A FilePart.
    
    Args:
        file_part: The FilePart from the A2A message
        
    Returns:
        Tuple of (filename, mime_type, content_bytes)
    """
    file_data = file_part.file
    
    if isinstance(file_data, FileWithBytes):
        filename = file_data.name or "unknown"
        mime_type = file_data.mime_type or "application/octet-stream"
        content_bytes = base64.b64decode(file_data.bytes)
        return filename, mime_type, content_bytes
    else:
        # FileWithUri - would need to fetch from URI
        raise FileProcessingError("File URI not supported, please send file bytes")


def create_file_part(filename: str, mime_type: str, content_bytes: bytes) -> FilePart:
    """
    Create a FilePart for response.
    
    Args:
        filename: Name of the file
        mime_type: MIME type
        content_bytes: Raw file content
        
    Returns:
        FilePart ready to be added to a message
    """
    file_with_bytes = FileWithBytes(
        name=filename,
        mime_type=mime_type,
        bytes=base64.b64encode(content_bytes).decode('utf-8')
    )
    return FilePart(file=file_with_bytes)


def create_text_part(text: str) -> TextPart:
    """
    Create a TextPart with the given text.
    
    Args:
        text: The text content
        
    Returns:
        TextPart ready to be added to a message
    """
    return TextPart(text=text)


def create_data_part(data: Dict[str, Any]) -> DataPart:
    """
    Create a DataPart with the given data.
    
    Args:
        data: The structured data
        
    Returns:
        DataPart ready to be added to a message
    """
    return DataPart(data=data)
