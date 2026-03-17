package com.a2alite.parts;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Rich output artifact with multiple parts.
 *
 * <pre>{@code
 * var artifact = new Artifact("report")
 *     .addText("Summary here")
 *     .addData(Map.of("count", 42))
 *     .addFile(FilePart.fromPath(Path.of("data.csv")));
 * }</pre>
 */
public class Artifact {
    private String name;
    private String description;
    private final List<Object> parts = new ArrayList<>();
    private Map<String, Object> metadata;

    public Artifact() {}

    public Artifact(String name) {
        this.name = name;
    }

    public Artifact(String name, String description) {
        this.name = name;
        this.description = description;
    }

    public Artifact(List<Object> parts) {
        this.parts.addAll(parts);
    }

    public Artifact setName(String name) { this.name = name; return this; }
    public Artifact setDescription(String description) { this.description = description; return this; }
    public Artifact setMetadata(Map<String, Object> metadata) { this.metadata = metadata; return this; }

    public Artifact addPart(TextPart part) { parts.add(part); return this; }
    public Artifact addPart(FilePart part) { parts.add(part); return this; }
    public Artifact addPart(DataPart part) { parts.add(part); return this; }

    public String getName() { return name; }
    public String getDescription() { return description; }
    public List<Object> getParts() { return parts; }
    public Map<String, Object> getMetadata() { return metadata; }

    /**
     * Add a text part.
     */
    public Artifact addText(String text) {
        parts.add(Map.of("type", "text", "text", text));
        return this;
    }

    /**
     * Add a file part.
     */
    public Artifact addFile(FilePart file) {
        parts.add(file);
        return this;
    }

    /**
     * Add a data part.
     */
    public Artifact addData(Map<String, Object> data) {
        parts.add(new DataPart(data));
        return this;
    }

    /**
     * Convert to A2A protocol format.
     */
    public Map<String, Object> toA2A() {
        var result = new LinkedHashMap<String, Object>();
        if (name != null) result.put("name", name);
        if (description != null) result.put("description", description);

        var a2aParts = new ArrayList<>();
        for (var part : parts) {
            if (part instanceof TextPart tp) {
                a2aParts.add(tp.toDict());
            } else if (part instanceof FilePart fp) {
                a2aParts.add(fp.toA2A());
            } else if (part instanceof DataPart dp) {
                a2aParts.add(dp.toA2A());
            } else {
                a2aParts.add(part);
            }
        }
        result.put("parts", a2aParts);
        if (metadata != null) result.put("metadata", metadata);
        return result;
    }

    /**
     * Convert to dictionary format (alias for toA2A).
     */
    public Map<String, Object> toDict() {
        return toA2A();
    }
}
