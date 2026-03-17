package com.example.calculator;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;

import java.util.Map;

/**
 * Calculator Agent - A2A Lite Example (Java)
 * 
 * Multi-skill calculator demonstrating the A2A Lite library.
 */
public class CalculatorAgent {
    
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("CalculatorAgent")
            .description("A calculator agent with arithmetic operations")
            .version("1.0.0")
            .build();
        
        // Add skill with description
        agent.skill("add", SkillConfig.of("Add two numbers"), params -> {
            double a = ((Number) params.getOrDefault("a", 0)).doubleValue();
            double b = ((Number) params.getOrDefault("b", 0)).doubleValue();
            return Map.of(
                "operation", "add",
                "a", a,
                "b", b,
                "result", a + b
            );
        });
        
        agent.skill("subtract", SkillConfig.of("Subtract two numbers"), params -> {
            double a = ((Number) params.getOrDefault("a", 0)).doubleValue();
            double b = ((Number) params.getOrDefault("b", 0)).doubleValue();
            return Map.of("result", a - b);
        });
        
        agent.skill("multiply", SkillConfig.of("Multiply two numbers"), params -> {
            double a = ((Number) params.getOrDefault("a", 0)).doubleValue();
            double b = ((Number) params.getOrDefault("b", 0)).doubleValue();
            return Map.of("result", a * b);
        });
        
        agent.skill("divide", SkillConfig.of("Divide two numbers"), params -> {
            double a = ((Number) params.getOrDefault("a", 0)).doubleValue();
            double b = ((Number) params.getOrDefault("b", 0)).doubleValue();
            if (b == 0) {
                throw new IllegalArgumentException("Division by zero is not allowed");
            }
            return Map.of(
                "result", a / b,
                "remainder", a % b
            );
        });
        
        agent.skill("power", SkillConfig.of("Calculate power of a number"), params -> {
            double base = ((Number) params.getOrDefault("base", 0)).doubleValue();
            double exponent = ((Number) params.getOrDefault("exponent", 0)).doubleValue();
            return Map.of("result", Math.pow(base, exponent));
        });
        
        // Start the server
        agent.run(8788);
    }
}
