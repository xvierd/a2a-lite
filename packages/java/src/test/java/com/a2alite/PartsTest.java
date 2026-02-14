package com.a2alite;

import com.a2alite.parts.Artifact;
import com.a2alite.parts.DataPart;
import com.a2alite.parts.FilePart;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PartsTest {

    // === FilePart Tests ===

    @Test
    void shouldCreateFilePartFromBytes() {
        var data = "hello world".getBytes();
        var file = new FilePart("test.txt", "text/plain", data);

        assertThat(file.getName()).isEqualTo("test.txt");
        assertThat(file.getMimeType()).isEqualTo("text/plain");
        assertThat(file.isBytes()).isTrue();
        assertThat(file.isUri()).isFalse();
    }

    @Test
    void shouldCreateFilePartFromPath(@TempDir Path tempDir) throws IOException {
        var path = tempDir.resolve("test.txt");
        Files.writeString(path, "file content");

        var file = FilePart.fromPath(path);
        assertThat(file.getName()).isEqualTo("test.txt");
        assertThat(file.getMimeType()).isEqualTo("text/plain");
        assertThat(file.isBytes()).isTrue();
    }

    @Test
    void shouldCreateFilePartFromPathWithMimeType(@TempDir Path tempDir) throws IOException {
        var path = tempDir.resolve("data.bin");
        Files.write(path, new byte[]{1, 2, 3});

        var file = FilePart.fromPath(path, "application/custom");
        assertThat(file.getMimeType()).isEqualTo("application/custom");
    }

    @Test
    void shouldCreateFilePartFromUri() {
        var file = FilePart.fromUri("https://example.com/file.pdf", "file.pdf");
        assertThat(file.isUri()).isTrue();
        assertThat(file.isBytes()).isFalse();
        assertThat(file.getUri()).isEqualTo("https://example.com/file.pdf");
    }

    @Test
    void shouldReadBytesFromData() throws Exception {
        var data = "hello".getBytes();
        var file = new FilePart("test.txt", "text/plain", data);
        assertThat(file.readBytes()).isEqualTo(data);
    }

    @Test
    void shouldReadTextFromData() throws Exception {
        var file = new FilePart("test.txt", "text/plain", "hello world".getBytes());
        assertThat(file.readText()).isEqualTo("hello world");
    }

    @Test
    void shouldThrowWhenNoDataOrUri() {
        var file = new FilePart("empty.txt", "text/plain", null, null);
        assertThatThrownBy(file::readBytes)
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("no data or URI");
    }

    @Test
    void shouldConvertBytesToA2A() {
        var data = "hello".getBytes();
        var file = new FilePart("test.txt", "text/plain", data);
        var a2a = file.toA2A();

        assertThat(a2a.get("type")).isEqualTo("file");
        assertThat(a2a.get("kind")).isEqualTo("file");

        @SuppressWarnings("unchecked")
        var fileMap = (Map<String, Object>) a2a.get("file");
        assertThat(fileMap.get("name")).isEqualTo("test.txt");
        assertThat(fileMap.get("mimeType")).isEqualTo("text/plain");
        assertThat(fileMap.get("bytes")).isEqualTo(Base64.getEncoder().encodeToString(data));
    }

    @Test
    void shouldConvertUriToA2A() {
        var file = FilePart.fromUri("https://example.com/f.pdf", "f.pdf");
        var a2a = file.toA2A();

        @SuppressWarnings("unchecked")
        var fileMap = (Map<String, Object>) a2a.get("file");
        assertThat(fileMap.get("uri")).isEqualTo("https://example.com/f.pdf");
        assertThat(fileMap).doesNotContainKey("bytes");
    }

    @Test
    void shouldParseFromA2AWithBytes() throws Exception {
        var encoded = Base64.getEncoder().encodeToString("hello".getBytes());
        var a2a = Map.<String, Object>of(
            "file", Map.of(
                "name", "test.txt",
                "mimeType", "text/plain",
                "bytes", encoded
            )
        );

        var file = FilePart.fromA2A(a2a);
        assertThat(file.getName()).isEqualTo("test.txt");
        assertThat(file.getMimeType()).isEqualTo("text/plain");
        assertThat(file.isBytes()).isTrue();
        assertThat(new String(file.readBytes())).isEqualTo("hello");
    }

    @Test
    void shouldParseFromA2AWithUri() {
        var a2a = Map.<String, Object>of(
            "file", Map.of(
                "name", "doc.pdf",
                "uri", "https://example.com/doc.pdf"
            )
        );

        var file = FilePart.fromA2A(a2a);
        assertThat(file.isUri()).isTrue();
        assertThat(file.getUri()).isEqualTo("https://example.com/doc.pdf");
    }

    @Test
    void shouldGuessMimeTypes() throws IOException {
        assertThat(FilePart.fromPath(createTempFile("test.json", "{}")).getMimeType())
            .isEqualTo("application/json");
        assertThat(FilePart.fromPath(createTempFile("img.png", "x")).getMimeType())
            .isEqualTo("image/png");
        assertThat(FilePart.fromPath(createTempFile("doc.pdf", "x")).getMimeType())
            .isEqualTo("application/pdf");
        assertThat(FilePart.fromPath(createTempFile("style.css", "x")).getMimeType())
            .isEqualTo("text/css");
    }

    @Test
    void shouldDefaultMimeType() {
        var file = new FilePart("unknown.xyz", null, new byte[0]);
        assertThat(file.getMimeType()).isEqualTo("application/octet-stream");
    }

    // === DataPart Tests ===

    @Test
    void shouldCreateDataPart() {
        var data = new DataPart(Map.of("count", 42, "name", "test"));
        assertThat(data.getData()).containsEntry("count", 42);
        assertThat(data.getData()).containsEntry("name", "test");
    }

    @Test
    void shouldGetByKey() {
        var data = new DataPart(Map.of("count", 42));
        Integer count = data.get("count");
        assertThat(count).isEqualTo(42);
    }

    @Test
    void shouldConvertDataPartToA2A() {
        var data = new DataPart(Map.of("key", "value"));
        var a2a = data.toA2A();
        assertThat(a2a.get("type")).isEqualTo("data");
        assertThat(a2a.get("kind")).isEqualTo("data");
        assertThat(a2a.get("data")).isEqualTo(Map.of("key", "value"));
    }

    @Test
    void shouldParseDataPartFromA2A() {
        var a2a = Map.<String, Object>of("data", Map.of("key", "value"));
        var data = DataPart.fromA2A(a2a);
        assertThat(data.getData()).containsEntry("key", "value");
    }

    @Test
    void shouldHandleEmptyDataPart() {
        var a2a = Map.<String, Object>of();
        var data = DataPart.fromA2A(a2a);
        assertThat(data.getData()).isEmpty();
    }

    // === Artifact Tests ===

    @Test
    void shouldBuildArtifact() {
        var artifact = new Artifact("report", "A report")
            .addText("Summary here")
            .addData(Map.of("count", 42));

        assertThat(artifact.getName()).isEqualTo("report");
        assertThat(artifact.getDescription()).isEqualTo("A report");
        assertThat(artifact.getParts()).hasSize(2);
    }

    @Test
    void shouldAddFilePart() {
        var file = new FilePart("data.csv", "text/csv", "a,b,c".getBytes());
        var artifact = new Artifact("export").addFile(file);
        assertThat(artifact.getParts()).hasSize(1);
    }

    @Test
    void shouldConvertArtifactToA2A() {
        var artifact = new Artifact("test")
            .addText("hello")
            .addData(Map.of("x", 1));

        var a2a = artifact.toA2A();
        assertThat(a2a.get("name")).isEqualTo("test");
        assertThat(a2a.get("parts")).isNotNull();
    }

    @Test
    void shouldSetMetadata() {
        var artifact = new Artifact("test")
            .setMetadata(Map.of("version", "1.0"));
        assertThat(artifact.getMetadata()).containsEntry("version", "1.0");
    }

    // Helper
    private Path createTempFile(String name, String content) throws IOException {
        var dir = Files.createTempDirectory("a2a-test");
        var file = dir.resolve(name);
        Files.writeString(file, content);
        return file;
    }
}
