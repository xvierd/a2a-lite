package com.example.llm;

import java.util.*;

/**
 * Conversation Memory Manager for LLM Agents.
 * 
 * Manages multi-turn conversation history per session with:
 * - Automatic trimming to prevent token overflow
 * - Token estimation
 * - Metadata storage per message
 * 
 * COMPLEXITY: ~150 lines
 */
public class ConversationManager {
    
    private final int maxHistory;
    private final int maxTokens;
    private final Map<String, List<ConversationMessage>> sessions;
    private final Map<String, Long> lastAccess;
    
    public ConversationManager(int maxHistory) {
        this.maxHistory = maxHistory;
        this.maxTokens = 4000;
        this.sessions = new HashMap<>();
        this.lastAccess = new HashMap<>();
    }
    
    public int getMaxHistory() {
        return maxHistory;
    }
    
    /**
     * Get or create a session.
     */
    public List<ConversationMessage> getOrCreateSession(String sessionId) {
        cleanupExpired();
        lastAccess.put(sessionId, System.currentTimeMillis());
        return sessions.computeIfAbsent(sessionId, k -> new ArrayList<>());
    }
    
    /**
     * Add a message to a session.
     */
    public void addMessage(String sessionId, String role, String content) {
        addMessage(sessionId, role, content, null);
    }
    
    /**
     * Add a message with metadata.
     */
    public void addMessage(String sessionId, String role, String content, 
                          Map<String, Object> metadata) {
        List<ConversationMessage> session = getOrCreateSession(sessionId);
        
        ConversationMessage message = new ConversationMessage(
            role,
            content,
            System.currentTimeMillis(),
            metadata
        );
        
        session.add(message);
        lastAccess.put(sessionId, System.currentTimeMillis());
        
        // Trim if needed
        trimSession(sessionId);
    }
    
    /**
     * Get messages formatted for LLM API.
     */
    public List<Map<String, String>> getMessages(String sessionId) {
        List<Map<String, String>> result = new ArrayList<>();
        
        // Add system message if not present
        List<ConversationMessage> session = sessions.getOrDefault(sessionId, new ArrayList<>());
        boolean hasSystem = session.stream().anyMatch(m -> "system".equals(m.role()));
        
        if (!hasSystem) {
            Map<String, String> systemMsg = new LinkedHashMap<>();
            systemMsg.put("role", "system");
            systemMsg.put("content", 
                "You are a helpful AI assistant with access to tools. " +
                "You can perform calculations, check time, and get weather. " +
                "When you need to use a tool, respond with a tool call.");
            result.add(systemMsg);
        }
        
        for (ConversationMessage msg : session) {
            Map<String, String> formatted = new LinkedHashMap<>();
            formatted.put("role", msg.role());
            formatted.put("content", msg.content());
            result.add(formatted);
        }
        
        return result;
    }
    
    /**
     * Clear a session's history.
     */
    public void clearSession(String sessionId) {
        sessions.remove(sessionId);
        lastAccess.remove(sessionId);
    }
    
    /**
     * Get the history length for a session.
     */
    public int getHistoryLength(String sessionId) {
        return sessions.getOrDefault(sessionId, new ArrayList<>()).size();
    }
    
    /**
     * Trim session to max_history while preserving system messages.
     */
    private void trimSession(String sessionId) {
        List<ConversationMessage> session = sessions.get(sessionId);
        if (session == null || session.size() <= maxHistory) {
            return;
        }
        
        // Keep system messages
        List<ConversationMessage> systemMessages = new ArrayList<>();
        List<ConversationMessage> otherMessages = new ArrayList<>();
        
        for (ConversationMessage msg : session) {
            if ("system".equals(msg.role())) {
                systemMessages.add(msg);
            } else {
                otherMessages.add(msg);
            }
        }
        
        // Keep most recent messages
        int keepCount = maxHistory - systemMessages.size();
        if (keepCount > 0 && otherMessages.size() > keepCount) {
            List<ConversationMessage> keptMessages = otherMessages.subList(
                otherMessages.size() - keepCount, otherMessages.size());
            
            List<ConversationMessage> newSession = new ArrayList<>();
            newSession.addAll(systemMessages);
            newSession.addAll(keptMessages);
            sessions.put(sessionId, newSession);
        }
    }
    
    /**
     * Remove expired sessions.
     */
    private void cleanupExpired() {
        long now = System.currentTimeMillis();
        long timeout = 3600 * 1000; // 1 hour
        
        List<String> expired = new ArrayList<>();
        for (Map.Entry<String, Long> entry : lastAccess.entrySet()) {
            if (now - entry.getValue() > timeout) {
                expired.add(entry.getKey());
            }
        }
        
        for (String sessionId : expired) {
            clearSession(sessionId);
        }
    }
    
    /**
     * Estimate tokens for a session (rough: ~4 chars per token).
     */
    public int estimateTokens(String sessionId) {
        List<ConversationMessage> session = sessions.get(sessionId);
        if (session == null) return 0;
        
        int totalChars = session.stream()
            .mapToInt(m -> m.content().length())
            .sum();
        
        return totalChars / 4;
    }
}

// Record for conversation messages
record ConversationMessage(
    String role,
    String content,
    long timestamp,
    Map<String, Object> metadata
) {
    public ConversationMessage(String role, String content, long timestamp) {
        this(role, content, timestamp, null);
    }
}
