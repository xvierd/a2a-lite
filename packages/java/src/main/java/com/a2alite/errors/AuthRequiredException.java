package com.a2alite.errors;

import java.util.HashMap;
import java.util.Map;

public class AuthRequiredException extends A2ALiteException {
    private final String schemeInfo;
    private final String detail;

    public AuthRequiredException(String schemeInfo, String detail) {
        super(buildMessage(schemeInfo, detail));
        this.schemeInfo = schemeInfo != null ? schemeInfo : "authentication";
        this.detail = detail;
    }

    public AuthRequiredException() {
        this(null, null);
    }

    private static String buildMessage(String schemeInfo, String detail) {
        var scheme = schemeInfo != null ? schemeInfo : "authentication";
        var msg = "Authentication required. This agent uses " + scheme + ".";
        if (detail != null) msg += "\n" + detail;
        return msg;
    }

    public String getSchemeInfo() { return schemeInfo; }
    public String getDetail() { return detail; }

    @Override
    public Map<String, Object> toResponse() {
        var resp = new HashMap<String, Object>();
        resp.put("error", "Authentication required");
        resp.put("type", "AuthRequiredException");
        resp.put("scheme", schemeInfo);
        if (detail != null) resp.put("detail", detail);
        return resp;
    }
}
