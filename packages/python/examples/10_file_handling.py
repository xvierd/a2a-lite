"""
Example: Multi-modal file handling.

Handle files, images, documents - not just text!

Run: python examples/10_file_handling.py
"""
from a2a_lite import Agent, FilePart, DataPart, Artifact

agent = Agent(name="FileProcessor", description="Processes files")


@agent.skill("summarize_doc")
async def summarize_doc(document: FilePart) -> str:
    """
    Summarize a document.
    FilePart is auto-converted from the A2A file format.
    """
    # Read file content
    content = await document.read_text()

    # Simple summary (in real use, call an LLM)
    words = content.split()
    summary = " ".join(words[:50]) + "..."

    return f"Summary of {document.name}: {summary}"


@agent.skill("process_data")
async def process_data(data: DataPart) -> dict:
    """Process structured JSON data."""
    # DataPart.data is already a dict
    items = data.data.get("items", [])

    return {
        "processed": len(items),
        "total": sum(item.get("value", 0) for item in items),
    }


@agent.skill("generate_report")
async def generate_report(title: str) -> Artifact:
    """
    Generate a rich artifact with multiple parts.
    """
    # Create artifact with multiple parts
    artifact = Artifact(
        name="report.json",
        description=f"Report: {title}",
    )

    # Add text summary
    artifact.add_text(f"# Report: {title}\n\nThis is the summary...")

    # Add structured data
    artifact.add_data({
        "title": title,
        "generated": "2024-01-15",
        "metrics": {"users": 100, "revenue": 5000},
    })

    return artifact


@agent.skill("analyze_image")
async def analyze_image(image: FilePart) -> dict:
    """Analyze an image file."""
    # Check mime type
    if not image.mime_type.startswith("image/"):
        return {"error": f"Expected image, got {image.mime_type}"}

    # Get image bytes
    data = await image.read_bytes()

    return {
        "filename": image.name,
        "mime_type": image.mime_type,
        "size_bytes": len(data),
        "analysis": "Image analysis would go here (call vision API)",
    }


if __name__ == "__main__":
    agent.run(port=8787)
