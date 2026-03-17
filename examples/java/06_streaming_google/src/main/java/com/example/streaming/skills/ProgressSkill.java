package com.example.streaming.skills;

import com.example.streaming.sse.SseEventEmitter;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Progress Skill - Streaming Implementation
 * 
 * Demonstrates long-running task simulation with detailed progress updates.
 */
public class ProgressSkill {
    
    private static final ObjectMapper mapper = new ObjectMapper();
    
    public void stream(ObjectNode params, SseEventEmitter emitter) {
        try {
            int steps = params.has("steps") ? params.get("steps").asInt() : 5;
            steps = Math.min(steps, 20); // Cap at 20
            
            emitter.sendEvent("status", createStatus("started", 
                "Starting long-running task with " + steps + " steps"));
            
            String[] tasks = {
                "Initializing resources",
                "Loading configuration",
                "Processing data batch 1",
                "Processing data batch 2",
                "Validating results",
                "Generating report",
                "Cleaning up",
                "Optimizing performance",
                "Checking consistency",
                "Finalizing output"
            };
            
            for (int i = 0; i < steps; i++) {
                String taskName = i < tasks.length ? tasks[i] : "Processing step " + (i + 1);
                
                // Start step
                emitter.sendEvent("step_started", createStep(i + 1, steps, taskName, "running"));
                
                // Simulate work (variable time)
                int workTime = 300 + (int) (Math.random() * 500);
                Thread.sleep(workTime);
                
                // Progress within step (0-100%)
                for (int progress = 0; progress <= 100; progress += 25) {
                    emitter.sendProgress(
                        (i * 100 + progress) / steps, 
                        100,
                        taskName + " (" + progress + "%)"
                    );
                    Thread.sleep(100);
                }
                
                // Step complete
                emitter.sendEvent("step_complete", createStep(i + 1, steps, taskName, "complete"));
            }
            
            emitter.sendEvent("status", createStatus("completed", 
                "All " + steps + " steps completed successfully!"));
            
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            emitter.sendError("Task interrupted");
        } catch (Exception e) {
            emitter.sendError("Error: " + e.getMessage());
        }
    }
    
    private ObjectNode createStep(int current, int total, String name, String status) {
        ObjectNode node = mapper.createObjectNode();
        node.put("step", current);
        node.put("totalSteps", total);
        node.put("name", name);
        node.put("status", status);
        node.put("percent", (int) ((current * 100.0) / total));
        return node;
    }
    
    private ObjectNode createStatus(String status, String message) {
        ObjectNode node = mapper.createObjectNode();
        node.put("status", status);
        node.put("message", message);
        return node;
    }
}
