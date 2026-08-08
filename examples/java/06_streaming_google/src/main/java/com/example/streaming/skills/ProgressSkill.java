package com.example.streaming.skills;

import com.example.streaming.sse.StreamEmitter;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Progress Skill - Streaming Implementation
 * 
 * Demonstrates long-running task simulation with detailed progress updates.
 */
public class ProgressSkill {
    
    public void stream(ObjectNode params, StreamEmitter emitter) {
        try {
            int steps = params.has("steps") ? params.get("steps").asInt() : 5;
            steps = Math.min(steps, 20); // Cap at 20
            
            emitter.sendStatus("Starting long-running task with " + steps + " steps");
            
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
                emitter.sendStatus("Step " + (i + 1) + "/" + steps + ": " + taskName);
                
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
                emitter.sendStatus("Step " + (i + 1) + "/" + steps + " complete: " + taskName);
            }
            
            emitter.complete("All " + steps + " steps completed successfully!");
            
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            emitter.sendError("Task interrupted");
        } catch (Exception e) {
            emitter.sendError("Error: " + e.getMessage());
        }
    }
}
