package com.example.llm;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * Tool Registry for LLM Agents.
 * 
 * Defines and executes tools that the LLM can call.
 * Tools: calculator, get_current_time, get_weather
 * 
 * COMPLEXITY: ~120 lines
 */
public class ToolRegistry {
    
    private final Map<String, ToolDefinition> tools;
    
    public ToolRegistry() {
        this.tools = new HashMap<>();
        registerTools();
    }
    
    private void registerTools() {
        // Calculator tool
        tools.put("calculator", new ToolDefinition(
            "calculator",
            "Calculate mathematical expressions",
            Map.of(
                "type", "object",
                "properties", Map.of(
                    "expression", Map.of(
                        "type", "string",
                        "description", "Mathematical expression to calculate"
                    )
                ),
                "required", List.of("expression")
            ),
            params -> {
                String expression = (String) params.get("expression");
                try {
                    // Simple calculator - for production use a proper expression parser
                    double result = evaluateExpression(expression);
                    return "Result: " + result;
                } catch (Exception e) {
                    return "Error: " + e.getMessage();
                }
            }
        ));
        
        // Get current time tool
        tools.put("get_current_time", new ToolDefinition(
            "get_current_time",
            "Get the current date and time",
            Map.of(
                "type", "object",
                "properties", new HashMap<>(),
                "required", List.of()
            ),
            params -> {
                LocalDateTime now = LocalDateTime.now();
                DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
                    "yyyy-MM-dd HH:mm:ss"
                );
                return "Current time: " + now.format(formatter);
            }
        ));
        
        // Get weather tool (mock)
        tools.put("get_weather", new ToolDefinition(
            "get_weather",
            "Get weather information for a location (mock data)",
            Map.of(
                "type", "object",
                "properties", Map.of(
                    "location", Map.of(
                        "type", "string",
                        "description", "City name"
                    )
                ),
                "required", List.of("location")
            ),
            params -> {
                String location = (String) params.get("location");
                // Mock weather data
                String[] conditions = {"sunny", "cloudy", "rainy", "partly cloudy"};
                int temp = 15 + (int) (Math.random() * 15); // 15-30°C
                String condition = conditions[(int) (Math.random() * conditions.length)];
                return String.format("Weather in %s: %s, %d°C", location, condition, temp);
            }
        ));
    }
    
    /**
     * Get tool schemas for LLM API.
     */
    public List<Map<String, Object>> getToolSchemas() {
        List<Map<String, Object>> schemas = new ArrayList<>();
        for (ToolDefinition tool : tools.values()) {
            Map<String, Object> schema = new HashMap<>();
            schema.put("name", tool.name());
            schema.put("description", tool.description());
            schema.put("parameters", tool.parameters());
            schemas.add(schema);
        }
        return schemas;
    }
    
    /**
     * Get list of tool names.
     */
    public List<String> getToolNames() {
        return new ArrayList<>(tools.keySet());
    }
    
    /**
     * Execute a tool by name.
     */
    public String execute(String toolName, Map<String, Object> arguments) {
        ToolDefinition tool = tools.get(toolName);
        if (tool == null) {
            return "Error: Unknown tool: " + toolName;
        }
        try {
            return tool.handler().execute(arguments);
        } catch (Exception e) {
            return "Error executing tool: " + e.getMessage();
        }
    }
    
    /**
     * Simple expression evaluator for calculator.
     * For production, use a proper expression parser library.
     */
    private double evaluateExpression(String expression) {
        // Remove whitespace
        String expr = expression.replaceAll("\\s+", "");
        
        // Very basic evaluator - handles +, -, *, /, ^, and parentheses
        // For production use a library like exp4j or Java's ScriptEngine
        return evaluateBasic(expr);
    }
    
    private double evaluateBasic(String expr) {
        // Handle parentheses
        while (expr.contains("(")) {
            int start = expr.lastIndexOf("(");
            int end = expr.indexOf(")", start);
            if (end == -1) throw new IllegalArgumentException("Mismatched parentheses");
            
            double inner = evaluateBasic(expr.substring(start + 1, end));
            expr = expr.substring(0, start) + inner + expr.substring(end + 1);
        }
        
        // Handle operators in order of precedence
        // First: ^ (exponentiation)
        expr = evaluateOperator(expr, "^", (a, b) -> Math.pow(a, b));
        
        // Then: *, /
        expr = evaluateOperator(expr, "*", (a, b) -> a * b);
        expr = evaluateOperator(expr, "/", (a, b) -> a / b);
        
        // Finally: +, -
        expr = evaluateOperator(expr, "+", (a, b) -> a + b);
        expr = evaluateOperator(expr, "-", (a, b) -> a - b);
        
        return Double.parseDouble(expr);
    }
    
    private String evaluateOperator(String expr, String op, BinaryOperator operation) {
        while (expr.contains(op)) {
            int idx = expr.indexOf(op);
            if (idx == -1) break;
            
            // Find left operand
            int leftStart = idx - 1;
            while (leftStart >= 0 && (Character.isDigit(expr.charAt(leftStart)) || 
                   expr.charAt(leftStart) == '.')) {
                leftStart--;
            }
            leftStart++;
            
            // Find right operand
            int rightEnd = idx + 1;
            while (rightEnd < expr.length() && (Character.isDigit(expr.charAt(rightEnd)) || 
                   expr.charAt(rightEnd) == '.')) {
                rightEnd++;
            }
            
            double left = Double.parseDouble(expr.substring(leftStart, idx));
            double right = Double.parseDouble(expr.substring(idx + 1, rightEnd));
            double result = operation.apply(left, right);
            
            expr = expr.substring(0, leftStart) + result + expr.substring(rightEnd);
        }
        return expr;
    }
    
    @FunctionalInterface
    interface BinaryOperator {
        double apply(double a, double b);
    }
}

// Record for tool definitions
record ToolDefinition(
    String name,
    String description,
    Map<String, Object> parameters,
    ToolHandler handler
) {}

// Functional interface for tool handlers
@FunctionalInterface
interface ToolHandler {
    String execute(Map<String, Object> params);
}
