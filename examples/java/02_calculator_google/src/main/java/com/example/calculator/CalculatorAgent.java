package com.example.calculator;

import io.javalin.Javalin;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;

/**
 * Calculator Agent - Google A2A SDK Implementation (Java)
 * 
 * Multi-skill calculator demonstrating the official A2A SDK approach.
 */
public class CalculatorAgent {
    
    private static final int PORT = 8788;
    private static final ObjectMapper mapper = new ObjectMapper();
    
    public static void main(String[] args) {
        System.out.println("=".repeat(60));
        System.out.println("Calculator Agent - Google A2A SDK (Java)");
        System.out.println("=".repeat(60));
        
        CalculatorSkill calculator = new CalculatorSkill();
        MessageHandler handler = new MessageHandler(calculator);
        ObjectNode agentCard = createAgentCard();
        
        Javalin app = Javalin.create(config -> {
            config.showJavalinBanner = false;
        });
        
        app.get("/.well-known/agent.json", ctx -> {
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(agentCard));
        });
        
        app.get("/", ctx -> {
            ObjectNode health = mapper.createObjectNode();
            health.put("status", "healthy");
            health.put("agent", "CalculatorAgent");
            ctx.json(health);
        });
        
        app.post("/", ctx -> {
            try {
                String body = ctx.body();
                ObjectNode request = (ObjectNode) mapper.readTree(body);
                ObjectNode response = handler.handle(request);
                ctx.contentType("application/json");
                ctx.result(mapper.writeValueAsString(response));
            } catch (Exception e) {
                ctx.status(400);
                ctx.json(createError(null, -32603, e.getMessage()));
            }
        });
        
        System.out.println("Agent: CalculatorAgent");
        System.out.println("Skills: add, subtract, multiply, divide, power");
        System.out.println("-".repeat(60));
        System.out.println("Starting server on http://localhost:" + PORT);
        System.out.println("=".repeat(60));
        
        app.start(PORT);
    }
    
    private static ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "CalculatorAgent");
        card.put("description", "A calculator agent with arithmetic operations");
        card.put("version", "1.0.0");
        card.put("url", "http://localhost:" + PORT + "/");
        
        ArrayNode skills = mapper.createArrayNode();
        String[] skillNames = {"add", "subtract", "multiply", "divide", "power"};
        
        for (String skillName : skillNames) {
            ObjectNode skill = mapper.createObjectNode();
            skill.put("name", skillName);
            skill.put("description", skillName + " operation");
            
            ObjectNode inputSchema = mapper.createObjectNode();
            inputSchema.put("type", "object");
            ObjectNode properties = mapper.createObjectNode();
            
            if ("power".equals(skillName)) {
                ObjectNode baseProp = mapper.createObjectNode();
                baseProp.put("type", "number");
                properties.set("base", baseProp);
                ObjectNode expProp = mapper.createObjectNode();
                expProp.put("type", "number");
                properties.set("exponent", expProp);
            } else {
                ObjectNode aProp = mapper.createObjectNode();
                aProp.put("type", "number");
                properties.set("a", aProp);
                ObjectNode bProp = mapper.createObjectNode();
                bProp.put("type", "number");
                properties.set("b", bProp);
            }
            
            inputSchema.set("properties", properties);
            ArrayNode required = mapper.createArrayNode();
            if ("power".equals(skillName)) {
                required.add("base");
                required.add("exponent");
            } else {
                required.add("a");
                required.add("b");
            }
            inputSchema.set("required", required);
            skill.set("inputSchema", inputSchema);
            skills.add(skill);
        }
        
        card.set("skills", skills);
        return card;
    }
    
    private static ObjectNode createError(String id, int code, String message) {
        ObjectNode error = mapper.createObjectNode();
        error.put("jsonrpc", "2.0");
        error.put("id", id);
        ObjectNode errorObj = mapper.createObjectNode();
        errorObj.put("code", code);
        errorObj.put("message", message);
        error.set("error", errorObj);
        return error;
    }
}
