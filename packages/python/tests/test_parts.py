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

    def test_parse_unknown_type_fallback(self):
        """Unknown part types should fall back to TextPart."""
        part = parse_part({"type": "unknown", "data": "test"})
        assert isinstance(part, TextPart)

    def test_parse_no_type(self):
        """Parts without type or kind should fall back to TextPart."""
        part = parse_part({"data": "some data"})
        assert isinstance(part, TextPart)


class TestFilePartFromPath:
    def test_from_path(self, tmp_path):
        """Test creating FilePart from a file path."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("Hello, world!")

        part = FilePart.from_path(file_path)
        assert part.name == "test.txt"
        assert part.data == b"Hello, world!"
        assert "text" in part.mime_type

    def test_from_path_custom_mime(self, tmp_path):
        """Test creating FilePart with custom mime type."""
        file_path = tmp_path / "data.bin"
        file_path.write_bytes(b"\x00\x01\x02")

        part = FilePart.from_path(file_path, mime_type="application/custom")
        assert part.mime_type == "application/custom"
        assert part.data == b"\x00\x01\x02"

    def test_from_path_string(self, tmp_path):
        """Test creating FilePart from a string path."""
        file_path = tmp_path / "test.json"
        file_path.write_text('{"key": "value"}')

        part = FilePart.from_path(str(file_path))
        assert part.name == "test.json"
        assert part.data == b'{"key": "value"}'


class TestFilePartEdgeCases:
    @pytest.mark.asyncio
    async def test_read_bytes_no_data_no_uri(self):
        """FilePart with no data and no URI should raise ValueError."""
        part = FilePart(name="empty.txt")
        with pytest.raises(ValueError, match="no data or URI"):
            await part.read_bytes()

    @pytest.mark.asyncio
    async def test_read_text_encoding(self):
        """Test reading with different encoding."""
        text = "Hello, world!"
        part = FilePart(name="test.txt", data=text.encode("utf-8"))
        content = await part.read_text(encoding="utf-8")
        assert content == text

    def test_to_a2a_empty_data(self):
        """Test to_a2a with no data (defaults to empty bytes)."""
        part = FilePart(name="empty.txt", mime_type="text/plain")
        result = part.to_a2a()
        assert result["file"]["bytes"] == base64.b64encode(b"").decode()

    def test_is_bytes_and_is_uri_both_none(self):
        """Test that both is_bytes and is_uri return False when no data."""
        part = FilePart(name="empty.txt")
        assert part.is_bytes is False
        assert part.is_uri is False


class TestDataPartEdgeCases:
    def test_empty_data(self):
        """Test DataPart with empty data."""
        part = DataPart(data={})
        assert part.data == {}
        result = part.to_a2a()
        assert result["data"] == {}

    def test_custom_mime_type(self):
        """Test DataPart with custom mime type."""
        part = DataPart(data={"key": "value"}, mime_type="application/xml")
        assert part.mime_type == "application/xml"


class TestArtifactEdgeCases:
    def test_artifact_metadata(self):
        """Test artifact with metadata."""
        artifact = Artifact(name="test", metadata={"version": "1.0"})
        result = artifact.to_a2a()
        assert result["metadata"] == {"version": "1.0"}

    def test_artifact_no_name(self):
        """Test artifact without name."""
        artifact = Artifact()
        assert artifact.name is None
        result = artifact.to_a2a()
        assert result["name"] is None

    def test_artifact_multiple_parts(self):
        """Test artifact with multiple different part types."""
        artifact = Artifact(name="mixed")
        artifact.add_text("Summary")
        artifact.add_data({"count": 42})
        artifact.add_file(FilePart(name="f.txt", data=b"data"))

        result = artifact.to_a2a()
        assert len(result["parts"]) == 3
        assert result["parts"][0]["type"] == "text"
        assert result["parts"][1]["type"] == "data"
        assert result["parts"][2]["type"] == "file"
