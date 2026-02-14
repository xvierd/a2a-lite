package com.a2alite.parts;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * File content part - can be bytes or a URI reference.
 *
 * <pre>{@code
 * // From bytes
 * var file = new FilePart("data.csv", "text/csv", csvBytes);
 *
 * // From local file
 * var file = FilePart.fromPath(Path.of("report.pdf"));
 *
 * // From URI
 * var file = FilePart.fromUri("https://example.com/data.csv", "data.csv");
 * }</pre>
 */
public class FilePart {
    private final String name;
    private final String mimeType;
    private final byte[] data;
    private final String uri;

    public FilePart(String name, String mimeType, byte[] data) {
        this.name = Objects.requireNonNull(name, "name is required");
        this.mimeType = mimeType != null ? mimeType : "application/octet-stream";
        this.data = data;
        this.uri = null;
    }

    public FilePart(String name, String mimeType, byte[] data, String uri) {
        this.name = Objects.requireNonNull(name, "name is required");
        this.mimeType = mimeType != null ? mimeType : "application/octet-stream";
        this.data = data;
        this.uri = uri;
    }

    /**
     * Create a FilePart from a local file path.
     */
    public static FilePart fromPath(Path path) throws IOException {
        return fromPath(path, null);
    }

    /**
     * Create a FilePart from a local file path with explicit MIME type.
     */
    public static FilePart fromPath(Path path, String mimeType) throws IOException {
        byte[] bytes = Files.readAllBytes(path);
        String name = path.getFileName().toString();
        String mime = mimeType != null ? mimeType : guessMimeType(name);
        return new FilePart(name, mime, bytes);
    }

    /**
     * Create a FilePart from a URI.
     */
    public static FilePart fromUri(String uri, String name) {
        return new FilePart(name, null, null, uri);
    }

    /**
     * Create a FilePart from A2A protocol format.
     */
    public static FilePart fromA2A(Map<String, Object> data) {
        @SuppressWarnings("unchecked")
        var file = (Map<String, Object>) data.getOrDefault("file", Map.of());
        String name = (String) file.getOrDefault("name", "unknown");
        String mimeType = (String) file.getOrDefault("mimeType", "application/octet-stream");
        String bytesStr = (String) file.get("bytes");
        String uri = (String) file.get("uri");

        byte[] bytes = bytesStr != null ? Base64.getDecoder().decode(bytesStr) : null;
        return new FilePart(name, mimeType, bytes, uri);
    }

    public String getName() { return name; }
    public String getMimeType() { return mimeType; }
    public boolean isUri() { return uri != null; }
    public boolean isBytes() { return data != null; }
    public String getUri() { return uri; }

    /**
     * Read file content as bytes.
     */
    public byte[] readBytes() throws IOException, InterruptedException {
        if (data != null) {
            return data;
        }
        if (uri != null) {
            var client = HttpClient.newHttpClient();
            var request = HttpRequest.newBuilder(URI.create(uri)).GET().build();
            var response = client.send(request, HttpResponse.BodyHandlers.ofByteArray());
            return response.body();
        }
        throw new IllegalStateException("FilePart has no data or URI");
    }

    /**
     * Read file content as text.
     */
    public String readText() throws IOException, InterruptedException {
        return new String(readBytes());
    }

    /**
     * Read file content as text with specific charset.
     */
    public String readText(String charset) throws IOException, InterruptedException {
        return new String(readBytes(), charset);
    }

    /**
     * Convert to A2A protocol format.
     */
    public Map<String, Object> toA2A() {
        var result = new LinkedHashMap<String, Object>();
        result.put("type", "file");
        result.put("kind", "file");

        var file = new LinkedHashMap<String, Object>();
        file.put("name", name);
        file.put("mimeType", mimeType);

        if (uri != null) {
            file.put("uri", uri);
        } else {
            file.put("bytes", data != null ? Base64.getEncoder().encodeToString(data) : "");
        }

        result.put("file", file);
        return result;
    }

    /**
     * Guess MIME type from filename extension.
     */
    static String guessMimeType(String filename) {
        String ext = filename.contains(".")
            ? filename.substring(filename.lastIndexOf('.') + 1).toLowerCase()
            : "";

        return switch (ext) {
            case "txt" -> "text/plain";
            case "html", "htm" -> "text/html";
            case "css" -> "text/css";
            case "js" -> "application/javascript";
            case "json" -> "application/json";
            case "xml" -> "application/xml";
            case "pdf" -> "application/pdf";
            case "png" -> "image/png";
            case "jpg", "jpeg" -> "image/jpeg";
            case "gif" -> "image/gif";
            case "svg" -> "image/svg+xml";
            case "csv" -> "text/csv";
            case "md" -> "text/markdown";
            case "zip" -> "application/zip";
            default -> "application/octet-stream";
        };
    }
}
