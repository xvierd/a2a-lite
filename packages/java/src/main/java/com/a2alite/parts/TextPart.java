package com.a2alite.parts;

import java.util.HashMap;
import java.util.Map;

/**
 * A text content part for multi-modal messages.
 */
public class TextPart {
    private final String text;

    public TextPart(String text) {
        this.text = text;
    }

    public String getText() { return text; }

    public Map<String, Object> toDict() {
        var map = new HashMap<String, Object>();
        map.put("text", text);
        return map;
    }

    @Override
    public String toString() { return "TextPart(text=" + text + ")"; }
}
