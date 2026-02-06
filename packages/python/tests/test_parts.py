"""
Tests for multi-modal parts (FilePart, DataPart, Artifact).
"""
import pytest
import base64
from a2a_lite.parts import TextPart, FilePart, DataPart, Artifact, parse_part


class TestTextPart:
    def test_creation(self):
        part = TextPart(text="Hello, world!")
        assert part.text == "Hello, world!"

    def test_to_a2a(self):
        part = TextPart(text="Hello")
        assert part.to_a2a() == {"type": "text", "text": "Hello"}

    def test_from_a2a(self):
        part = TextPart.from_a2a({"type": "text", "text": "Hello"})
        assert part.text == "Hello"


class TestFilePart:
    def test_creation_with_bytes(self):
        part = FilePart(
            name="test.txt",
            mime_type="text/plain",
            data=b"Hello, world!",
        )
        assert part.name == "test.txt"
        assert part.is_bytes
        assert not part.is_uri

    def test_creation_with_uri(self):
        part = FilePart(
            name="remote.txt",
            mime_type="text/plain",
            uri="https://example.com/file.txt",
        )
        assert part.is_uri
        assert not part.is_bytes

    def test_to_a2a_bytes(self):
        data = b"Hello"
        part = FilePart(name="test.txt", data=data)
        result = part.to_a2a()

        assert result["type"] == "file"
        assert result["file"]["name"] == "test.txt"
        assert result["file"]["bytes"] == base64.b64encode(data).decode()

    def test_to_a2a_uri(self):
        part = FilePart(name="test.txt", uri="https://example.com/file.txt")
        result = part.to_a2a()

        assert result["type"] == "file"
        assert result["file"]["uri"] == "https://example.com/file.txt"

    def test_from_a2a_bytes(self):
        data = b"Hello"
        a2a_data = {
            "type": "file",
            "file": {
                "name": "test.txt",
                "mimeType": "text/plain",
                "bytes": base64.b64encode(data).decode(),
            }
        }
        part = FilePart.from_a2a(a2a_data)

        assert part.name == "test.txt"
        assert part.data == data

    def test_from_a2a_uri(self):
        a2a_data = {
            "type": "file",
            "file": {
                "name": "remote.txt",
                "uri": "https://example.com/file.txt",
            }
        }
        part = FilePart.from_a2a(a2a_data)

        assert part.name == "remote.txt"
        assert part.uri == "https://example.com/file.txt"

    @pytest.mark.asyncio
    async def test_read_bytes(self):
        part = FilePart(name="test.txt", data=b"Hello")
        content = await part.read_bytes()
        assert content == b"Hello"

    @pytest.mark.asyncio
    async def test_read_text(self):
        part = FilePart(name="test.txt", data=b"Hello, world!")
        content = await part.read_text()
        assert content == "Hello, world!"


class TestDataPart:
    def test_creation(self):
        part = DataPart(data={"key": "value", "count": 42})
        assert part.data == {"key": "value", "count": 42}

    def test_to_a2a(self):
        part = DataPart(data={"key": "value"})
        result = part.to_a2a()

        assert result["type"] == "data"
        assert result["data"] == {"key": "value"}

    def test_from_a2a(self):
        part = DataPart.from_a2a({"type": "data", "data": {"key": "value"}})
        assert part.data == {"key": "value"}


class TestArtifact:
    def test_creation(self):
        artifact = Artifact(name="report.json", description="A report")
        assert artifact.name == "report.json"
        assert artifact.parts == []

    def test_add_text(self):
        artifact = Artifact()
        artifact.add_text("Hello")

        assert len(artifact.parts) == 1
        assert artifact.parts[0].text == "Hello"

    def test_add_file(self):
        artifact = Artifact()
        file_part = FilePart(name="test.txt", data=b"content")
        artifact.add_file(file_part)

        assert len(artifact.parts) == 1
        assert artifact.parts[0].name == "test.txt"

    def test_add_data(self):
        artifact = Artifact()
        artifact.add_data({"key": "value"})

        assert len(artifact.parts) == 1
        assert artifact.parts[0].data == {"key": "value"}

    def test_chaining(self):
        artifact = (
            Artifact(name="combined")
            .add_text("Summary")
            .add_data({"count": 10})
        )

        assert len(artifact.parts) == 2

    def test_to_a2a(self):
        artifact = Artifact(name="report", description="Test")
        artifact.add_text("Hello")

        result = artifact.to_a2a()

        assert result["name"] == "report"
        assert result["description"] == "Test"
        assert len(result["parts"]) == 1


class TestParsePart:
    def test_parse_text(self):
        part = parse_part({"type": "text", "text": "Hello"})
        assert isinstance(part, TextPart)
        assert part.text == "Hello"

    def test_parse_file(self):
        part = parse_part({
            "type": "file",
            "file": {"name": "test.txt", "bytes": base64.b64encode(b"data").decode()}
        })
        assert isinstance(part, FilePart)

    def test_parse_data(self):
        part = parse_part({"type": "data", "data": {"key": "value"}})
        assert isinstance(part, DataPart)

    def test_parse_kind_alias(self):
        # A2A sometimes uses 'kind' instead of 'type'
        part = parse_part({"kind": "text", "text": "Hello"})
        assert isinstance(part, TextPart)
