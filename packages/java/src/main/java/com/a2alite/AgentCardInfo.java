package com.a2alite;

import java.util.List;
import java.util.Map;

/**
 * Cached representation of a remote agent's card fetched from
 * {@code /.well-known/agent.json}.
 *
 * <p>The {@link #raw} map holds the full JSON payload so callers can
 * access any vendor-specific fields not surfaced by the typed getters.
 */
public class AgentCardInfo {
    private final String name;
    private final String description;
    private final String url;
    private final String version;
    private final List<Map<String, Object>> skills;
    private final boolean supportsStreaming;
    private final boolean supportsPush;
    private final Map<String, Object> raw;

    public AgentCardInfo(String name, String description, String url, String version,
                         List<Map<String, Object>> skills, boolean supportsStreaming,
                         boolean supportsPush, Map<String, Object> raw) {
        this.name = name;
        this.description = description;
        this.url = url;
        this.version = version;
        this.skills = skills != null ? List.copyOf(skills) : List.of();
        this.supportsStreaming = supportsStreaming;
        this.supportsPush = supportsPush;
        this.raw = raw != null ? Map.copyOf(raw) : Map.of();
    }

    public String getName() { return name; }
    public String getDescription() { return description; }
    public String getUrl() { return url; }
    public String getVersion() { return version; }
    public List<Map<String, Object>> getSkills() { return skills; }
    public boolean isSupportsStreaming() { return supportsStreaming; }
    public boolean isSupportsPush() { return supportsPush; }
    public Map<String, Object> getRaw() { return raw; }

    @Override
    public String toString() {
        return "AgentCardInfo{name='" + name + "', url='" + url + "', skills=" + skills.size() + "}";
    }
}
