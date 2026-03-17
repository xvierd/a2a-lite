package com.example.calculator;

import java.util.Map;

/**
 * Calculator Skill Implementations
 * 
 * Business logic for arithmetic operations.
 */
public class CalculatorSkill {
    
    public Map<String, Object> add(double a, double b) {
        return Map.of("result", a + b);
    }
    
    public Map<String, Object> subtract(double a, double b) {
        return Map.of("result", a - b);
    }
    
    public Map<String, Object> multiply(double a, double b) {
        return Map.of("result", a * b);
    }
    
    public Map<String, Object> divide(double a, double b) {
        if (b == 0) {
            throw new IllegalArgumentException("Division by zero");
        }
        return Map.of(
            "result", a / b,
            "remainder", a % b
        );
    }
    
    public Map<String, Object> power(double base, double exponent) {
        return Map.of("result", Math.pow(base, exponent));
    }
}
