package com.example.auth.model;

public class AdminResponse {
    private final String message;
    private final String adminAction;
    private final String performedBy;

    public AdminResponse(String message, String adminAction, String performedBy) {
        this.message = message;
        this.adminAction = adminAction;
        this.performedBy = performedBy;
    }

    public String getMessage() { return message; }
    public String getAdminAction() { return adminAction; }
    public String getPerformedBy() { return performedBy; }
}
