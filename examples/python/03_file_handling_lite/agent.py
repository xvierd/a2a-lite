"""
File Handling Agent - A2A Lite Implementation

Demonstrates file upload processing using A2A Lite's FilePart abstraction.
"""

import base64
from a2a_lite import Agent, FilePart

agent = Agent(
    name="FileAgent",
    description="Agent that processes file uploads",
    version="1.0.0"
)


@agent.skill("analyze")
async def analyze(file: FilePart) -> dict:
    """
    Analyze an uploaded file and return statistics.
    
    Args:
        file: Uploaded file as FilePart
        
    Returns:
        File statistics (size, word count, line count)
    """
    # Read file content
    content = await file.read_text()
    data = await file.read_bytes()
    
    # Calculate statistics
    lines = content.split('\n')
    words = content.split()
    
    return {
        "filename": file.name,
        "mime_type": file.mime_type or "unknown",
        "size_bytes": len(data),
        "line_count": len(lines),
        "word_count": len(words),
        "character_count": len(content),
        "preview": content[:200] + "..." if len(content) > 200 else content
    }


@agent.skill("convert_to_upper")
async def convert_to_upper(file: FilePart) -> FilePart:
    """
    Convert file content to uppercase and return as new file.
    
    Args:
        file: Input file
        
    Returns:
        New file with uppercase content
    """
    content = await file.read_text()
    upper_content = content.upper()
    
    # Create output filename
    name_parts = file.name.rsplit('.', 1)
    output_name = f"{name_parts[0]}_upper.{name_parts[1]}" if len(name_parts) > 1 else f"{file.name}_upper"
    
    # Return as FilePart
    return FilePart(
        name=output_name,
        data=upper_content.encode('utf-8'),
        mime_type=file.mime_type
    )


@agent.skill("generate_report")
async def generate_report(format: str = "txt") -> FilePart:
    """
    Generate a sample report file.
    
    Args:
        format: File format (txt, csv, json)
        
    Returns:
        Generated file as FilePart
    """
    if format == "csv":
        content = "name,value\nItem1,100\nItem2,200\nItem3,300"
        mime = "text/csv"
        filename = "report.csv"
    elif format == "json":
        content = '{"report": {"generated": "2024-01-01", "items": [{"name": "Item1", "value": 100}]}}'
        mime = "application/json"
        filename = "report.json"
    else:
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
    
    return FilePart(name=filename, data=content.encode('utf-8'), mime_type=mime)


if __name__ == "__main__":
    print("=" * 60)
    print("File Handling Agent - A2A Lite")
    print("=" * 60)
    print("Skills: analyze, convert_to_upper, generate_report")
    print("Port: 8789")
    print("=" * 60)
    
    agent.run(port=8789)
