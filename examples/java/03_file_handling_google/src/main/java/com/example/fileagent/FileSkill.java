package com.example.fileagent;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * File Skill Implementations
 * 
 * Business logic for file handling operations including:
 * - analyze: Get text statistics (word/line/char counts)
 * - convert_to_upper: Convert text to uppercase
 * - generate_report: Generate formatted reports
 */
public class FileSkill {
    
    /**
     * Analyze text content and return statistics.
     * 
     * @param content Text content (optional if file is provided)
     * @param file File data with name, mimeType, and base64 encoded data (optional)
     * @return Analysis results with word count, line count, char count
     */
    public Map<String, Object> analyze(String content, Map<String, Object> file) {
        String textToAnalyze = null;
        String sourceName = "content";
        
        // Extract text from file if provided
        if (file != null && !file.isEmpty()) {
            String fileName = (String) file.getOrDefault("name", "unknown");
            String mimeType = (String) file.getOrDefault("mimeType", "text/plain");
            String base64Data = (String) file.get("data");
            
            if (base64Data != null && !base64Data.isEmpty()) {
                try {
                    byte[] decodedBytes = Base64.getDecoder().decode(base64Data);
                    textToAnalyze = new String(decodedBytes, StandardCharsets.UTF_8);
                    sourceName = fileName;
                } catch (IllegalArgumentException e) {
                    throw new IllegalArgumentException("Invalid base64 file data: " + e.getMessage());
                }
            }
        }
        
        // Use direct content if no file or file parsing failed
        if (textToAnalyze == null && content != null) {
            textToAnalyze = content;
        }
        
        if (textToAnalyze == null || textToAnalyze.isEmpty()) {
            throw new IllegalArgumentException("No content or file provided for analysis");
        }
        
        // Calculate statistics
        int charCount = textToAnalyze.length();
        int lineCount = textToAnalyze.split("\r?\n").length;
        String[] words = textToAnalyze.trim().split("\\s+");
        int wordCount = textToAnalyze.trim().isEmpty() ? 0 : words.length;
        
        // Calculate average word length
        double avgWordLength = 0;
        if (wordCount > 0) {
            int totalLength = 0;
            for (String word : words) {
                totalLength += word.length();
            }
            avgWordLength = (double) totalLength / wordCount;
        }
        
        return Map.of(
            "source", sourceName,
            "character_count", charCount,
            "word_count", wordCount,
            "line_count", lineCount,
            "average_word_length", Math.round(avgWordLength * 100.0) / 100.0,
            "analyzed_at", LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)
        );
    }
    
    /**
     * Convert text content to uppercase.
     * 
     * @param content Text content (optional if file is provided)
     * @param file File data with name, mimeType, and base64 encoded data (optional)
     * @return Converted text and metadata
     */
    public Map<String, Object> convertToUpper(String content, Map<String, Object> file) {
        String textToConvert = null;
        String sourceName = "content";
        
        // Extract text from file if provided
        if (file != null && !file.isEmpty()) {
            String fileName = (String) file.getOrDefault("name", "unknown");
            String base64Data = (String) file.get("data");
            
            if (base64Data != null && !base64Data.isEmpty()) {
                try {
                    byte[] decodedBytes = Base64.getDecoder().decode(base64Data);
                    textToConvert = new String(decodedBytes, StandardCharsets.UTF_8);
                    sourceName = fileName;
                } catch (IllegalArgumentException e) {
                    throw new IllegalArgumentException("Invalid base64 file data: " + e.getMessage());
                }
            }
        }
        
        // Use direct content if no file
        if (textToConvert == null && content != null) {
            textToConvert = content;
        }
        
        if (textToConvert == null || textToConvert.isEmpty()) {
            throw new IllegalArgumentException("No content or file provided for conversion");
        }
        
        String converted = textToConvert.toUpperCase();
        
        return Map.of(
            "source", sourceName,
            "original_length", textToConvert.length(),
            "converted_length", converted.length(),
            "converted_text", converted,
            "changes_made", !textToConvert.equals(converted)
        );
    }
    
    /**
     * Generate a formatted report from provided data.
     * 
     * @param title Report title
     * @param data Report data as key-value pairs
     * @param format Output format (json, markdown, text)
     * @return Generated report content and metadata
     */
    public Map<String, Object> generateReport(String title, Map<String, Object> data, String format) {
        if (title == null || title.isEmpty()) {
            throw new IllegalArgumentException("Report title is required");
        }
        if (data == null || data.isEmpty()) {
            throw new IllegalArgumentException("Report data is required");
        }
        
        // Default format
        String outputFormat = (format != null && !format.isEmpty()) ? format.toLowerCase() : "json";
        
        String reportContent;
        String mimeType;
        
        switch (outputFormat) {
            case "markdown":
                reportContent = generateMarkdownReport(title, data);
                mimeType = "text/markdown";
                break;
            case "text":
                reportContent = generateTextReport(title, data);
                mimeType = "text/plain";
                break;
            case "json":
            default:
                reportContent = generateJsonReport(title, data);
                mimeType = "application/json";
                break;
        }
        
        // Encode content as base64 for file transfer
        String base64Content = Base64.getEncoder().encodeToString(reportContent.getBytes(StandardCharsets.UTF_8));
        
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
        String filename = title.toLowerCase().replaceAll("\\s+", "_").replaceAll("[^a-z0-9_]", "") + "_" + timestamp;
        
        switch (outputFormat) {
            case "markdown":
                filename += ".md";
                break;
            case "text":
                filename += ".txt";
                break;
            default:
                filename += ".json";
        }
        
        return Map.of(
            "filename", filename,
            "title", title,
            "format", outputFormat,
            "mime_type", mimeType,
            "size_bytes", reportContent.length(),
            "generated_at", LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME),
            "data_points", data.size(),
            "content", reportContent,
            "file", Map.of(
                "name", filename,
                "mimeType", mimeType,
                "data", base64Content
            )
        );
    }
    
    private String generateMarkdownReport(String title, Map<String, Object> data) {
        StringBuilder sb = new StringBuilder();
        sb.append("# ").append(title).append("\n\n");
        sb.append("Generated: ").append(LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)).append("\n\n");
        sb.append("## Report Data\n\n");
        
        for (Map.Entry<String, Object> entry : data.entrySet()) {
            sb.append("- **").append(entry.getKey()).append("**: ");
            sb.append(entry.getValue()).append("\n");
        }
        
        sb.append("\n---\n\n");
        sb.append("*Generated by FileAgent*\n");
        
        return sb.toString();
    }
    
    private String generateTextReport(String title, Map<String, Object> data) {
        StringBuilder sb = new StringBuilder();
        sb.append("=".repeat(60)).append("\n");
        sb.append(title.toUpperCase()).append("\n");
        sb.append("=".repeat(60)).append("\n\n");
        sb.append("Generated: ").append(LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)).append("\n\n");
        
        for (Map.Entry<String, Object> entry : data.entrySet()) {
            sb.append(entry.getKey()).append(": ").append(entry.getValue()).append("\n");
        }
        
        sb.append("\n").append("-".repeat(60)).append("\n");
        sb.append("Generated by FileAgent\n");
        
        return sb.toString();
    }
    
    private String generateJsonReport(String title, Map<String, Object> data) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\n");
        sb.append("  \"title\": \"").append(escapeJson(title)).append("\",\n");
        sb.append("  \"generated_at\": \"").append(LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)).append("\",\n");
        sb.append("  \"data\": {\n");
        
        boolean first = true;
        for (Map.Entry<String, Object> entry : data.entrySet()) {
            if (!first) sb.append(",\n");
            sb.append("    \"").append(entry.getKey()).append("\": ");
            Object value = entry.getValue();
            if (value instanceof String) {
                sb.append("\"").append(escapeJson((String) value)).append("\"");
            } else if (value instanceof Number) {
                sb.append(value);
            } else if (value instanceof Boolean) {
                sb.append(value);
            } else {
                sb.append("\"").append(escapeJson(value.toString())).append("\"");
            }
            first = false;
        }
        
        sb.append("\n  }\n");
        sb.append("}");
        
        return sb.toString();
    }
    
    private String escapeJson(String input) {
        return input.replace("\\", "\\\\")
                    .replace("\"", "\\\"")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    .replace("\t", "\\t");
    }
}
