package com.example.fileagent;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * File Agent - A2A Lite Example (Java)
 * 
 * Multi-skill file handling agent demonstrating A2A Lite with file operations.
 */
public class FileAgent {
    
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("FileAgent")
            .description("A file handling agent with text analysis and conversion")
            .version("1.0.0")
            .build();
        
        // Analyze text content
        agent.skill("analyze", SkillConfig.of("Analyze text content and return statistics"), params -> {
            String content = extractText(params);
            
            int charCount = content.length();
            int lineCount = content.split("\r?\n").length;
            String[] words = content.trim().split("\\s+");
            int wordCount = content.trim().isEmpty() ? 0 : words.length;
            
            double avgWordLength = 0;
            if (wordCount > 0) {
                int total = Arrays.stream(words).mapToInt(String::length).sum();
                avgWordLength = (double) total / wordCount;
            }
            
            return Map.of(
                "word_count", wordCount,
                "line_count", lineCount,
                "character_count", charCount,
                "average_word_length", Math.round(avgWordLength * 100.0) / 100.0,
                "analyzed_at", LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)
            );
        });
        
        // Convert text to uppercase
        agent.skill("convert_to_upper", SkillConfig.of("Convert text content to uppercase"), params -> {
            String text = extractText(params);
            String converted = text.toUpperCase();
            
            return Map.of(
                "original_length", text.length(),
                "converted_length", converted.length(),
                "converted_text", converted,
                "changes_made", !text.equals(converted)
            );
        });
        
        // Generate report
        agent.skill("generate_report", SkillConfig.of("Generate a formatted report"), params -> {
            String title = (String) params.getOrDefault("title", "Report");
            String format = (String) params.getOrDefault("format", "json");
            @SuppressWarnings("unchecked")
            Map<String, Object> reportData = (Map<String, Object>) params.getOrDefault("data", Map.of());
            
            String reportContent = generateReportContent(title, reportData, format);
            String base64Content = Base64.getEncoder()
                .encodeToString(reportContent.getBytes(StandardCharsets.UTF_8));
            
            String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
            String filename = title.toLowerCase().replaceAll("\\s+", "_").replaceAll("[^a-z0-9_]", "") 
                + "_" + timestamp + getExtension(format);
            
            return Map.of(
                "filename", filename,
                "title", title,
                "format", format,
                "size_bytes", reportContent.length(),
                "data_points", reportData.size(),
                "file", Map.of(
                    "name", filename,
                    "mimeType", getMimeType(format),
                    "data", base64Content
                )
            );
        });
        
        agent.run(8789);
    }
    
    private static String extractText(Map<String, Object> params) {
        // Check for inline file
        if (params.containsKey("file")) {
            @SuppressWarnings("unchecked")
            Map<String, Object> file = (Map<String, Object>) params.get("file");
            if (file != null && file.containsKey("data")) {
                String data = (String) file.get("data");
                byte[] decoded = Base64.getDecoder().decode(data);
                return new String(decoded, StandardCharsets.UTF_8);
            }
        }
        
        // Return direct content
        if (params.containsKey("content")) {
            return (String) params.get("content");
        }
        
        throw new IllegalArgumentException("No content or file provided");
    }
    
    private static String generateReportContent(String title, Map<String, Object> data, String format) {
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ISO_LOCAL_DATE_TIME);
        
        return switch (format.toLowerCase()) {
            case "markdown" -> generateMarkdown(title, data, timestamp);
            case "text" -> generateText(title, data, timestamp);
            default -> generateJson(title, data, timestamp);
        };
    }
    
    private static String generateMarkdown(String title, Map<String, Object> data, String timestamp) {
        StringBuilder sb = new StringBuilder();
        sb.append("# ").append(title).append("\n\n");
        sb.append("Generated: ").append(timestamp).append("\n\n");
        sb.append("## Data\n\n");
        data.forEach((k, v) -> sb.append("- **").append(k).append("**: ").append(v).append("\n"));
        sb.append("\n---\n*Generated by FileAgent*");
        return sb.toString();
    }
    
    private static String generateText(String title, Map<String, Object> data, String timestamp) {
        StringBuilder sb = new StringBuilder();
        sb.append("=".repeat(60)).append("\n");
        sb.append(title.toUpperCase()).append("\n");
        sb.append("=".repeat(60)).append("\n\n");
        sb.append("Generated: ").append(timestamp).append("\n\n");
        data.forEach((k, v) -> sb.append(k).append(": ").append(v).append("\n"));
        sb.append("\n").append("-".repeat(60)).append("\nGenerated by FileAgent");
        return sb.toString();
    }
    
    private static String generateJson(String title, Map<String, Object> data, String timestamp) {
        StringBuilder sb = new StringBuilder();
        sb.append("{\n");
        sb.append("  \"title\": \"").append(title).append("\",\n");
        sb.append("  \"generated_at\": \"").append(timestamp).append("\",\n");
        sb.append("  \"data\": {\n");
        boolean first = true;
        for (Map.Entry<String, Object> entry : data.entrySet()) {
            if (!first) sb.append(",\n");
            sb.append("    \"").append(entry.getKey()).append("\": ");
            if (entry.getValue() instanceof String) {
                sb.append("\"").append(entry.getValue()).append("\"");
            } else {
                sb.append(entry.getValue());
            }
            first = false;
        }
        sb.append("\n  }\n");
        sb.append("}");
        return sb.toString();
    }
    
    private static String getExtension(String format) {
        return switch (format.toLowerCase()) {
            case "markdown" -> ".md";
            case "text" -> ".txt";
            default -> ".json";
        };
    }
    
    private static String getMimeType(String format) {
        return switch (format.toLowerCase()) {
            case "markdown" -> "text/markdown";
            case "text" -> "text/plain";
            default -> "application/json";
        };
    }
}
