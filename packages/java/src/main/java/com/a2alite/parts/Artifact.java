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

    public String getName() { return name; }
    public String getDescription() { return description; }
    public List<Object> getParts() { return parts; }
    public Map<String, Object> getMetadata() { return metadata; }

    public Artifact setMetadata(Map<String, Object> metadata) {
        this.metadata = metadata;
        return this;
    }

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
        result.put("name", name);
        result.put("description", description);

        var a2aParts = new ArrayList<>();
        for (var part : parts) {
            if (part instanceof FilePart fp) {
                a2aParts.add(fp.toA2A());
            } else if (part instanceof DataPart dp) {
                a2aParts.add(dp.toA2A());
            } else {
                a2aParts.add(part);
            }
        }
        result.put("parts", a2aParts);
        result.put("metadata", metadata);
        return result;
    }
}
