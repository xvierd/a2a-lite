package com.example.hitl;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Human-in-the-Loop Agent - A2A Lite Example (Java)
 * 
 * Demonstrates HITL workflows with the A2A Lite library:
 * - Purchase confirmation
 * - Data deletion with reason
 * - Document approval
 */
public class HumanInLoopAgent {
    
    // State storage for multi-step interactions
    private static final Map<String, InteractionState> states = new ConcurrentHashMap<>();
    
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("HumanInTheLoopAgent")
            .description("A2A agent with human confirmation for sensitive operations")
            .version("1.0.0")
            .build();
        
        // Purchase skill with confirmation flow
        agent.skill("purchase", SkillConfig.of("Purchase an item with confirmation"), params -> {
            // Check if this is a confirmation response
            String taskId = (String) params.get("task_id");
            String confirmation = (String) params.get("confirmation");
            
            if (taskId != null && states.containsKey(taskId)) {
                // Process confirmation
                InteractionState state = states.remove(taskId);
                boolean approved = "true".equalsIgnoreCase(confirmation) || "yes".equalsIgnoreCase(confirmation);
                
                if (approved) {
                    return Map.of(
                        "status", "completed",
                        "order_id", generateOrderId(),
                        "item", state.item,
                        "amount", state.amount,
                        "message", "Purchase approved and processed"
                    );
                } else {
                    return Map.of(
                        "status", "cancelled",
                        "item", state.item,
                        "message", "Purchase was declined by user"
                    );
                }
            }
            
            // Initial request - ask for confirmation
            String item = (String) params.getOrDefault("item", "Unknown item");
            double amount = ((Number) params.getOrDefault("amount", 0.0)).doubleValue();
            
            String newTaskId = generateTaskId();
            states.put(newTaskId, new InteractionState(item, amount));
            
            return Map.of(
                "status", "awaiting_confirmation",
                "task_id", newTaskId,
                "question", String.format("Approve purchase of '%s' for $%.2f?", item, amount),
                "type", "confirm",
                "reply_to_confirm", Map.of(
                    "skill", "purchase",
                    "params", Map.of("task_id", newTaskId, "confirmation", "true")
                ),
                "reply_to_cancel", Map.of(
                    "skill", "purchase", 
                    "params", Map.of("task_id", newTaskId, "confirmation", "false")
                )
            );
        });
        
        // Delete data skill with reason
        agent.skill("delete_data", SkillConfig.of("Delete data with confirmation and reason"), params -> {
            String taskId = (String) params.get("task_id");
            String step = (String) params.get("step");
            
            if (taskId != null && states.containsKey(taskId)) {
                InteractionState state = states.get(taskId);
                
                if ("confirm".equals(step)) {
                    String confirmation = (String) params.get("confirmation");
                    if (!"true".equalsIgnoreCase(confirmation)) {
                        states.remove(taskId);
                        return Map.of("status", "cancelled", "message", "Deletion cancelled");
                    }
                    // Move to reason step
                    state.step = "reason";
                    return Map.of(
                        "status", "awaiting_input",
                        "task_id", taskId,
                        "step", "reason",
                        "question", "Please provide a reason for deletion:",
                        "type", "text_input"
                    );
                } else if ("reason".equals(step)) {
                    String reason = (String) params.get("reason");
                    states.remove(taskId);
                    
                    return Map.of(
                        "status", "deleted",
                        "deletion_id", generateOrderId(),
                        "data_id", state.dataId,
                        "data_type", state.dataType,
                        "reason", reason,
                        "deleted_at", java.time.Instant.now().toString(),
                        "message", "Data deleted successfully"
                    );
                }
            }
            
            // Initial request
            String dataId = (String) params.getOrDefault("data_id", "unknown");
            String dataType = (String) params.getOrDefault("data_type", "data");
            
            String newTaskId = generateTaskId();
            states.put(newTaskId, new InteractionState(dataId, dataType));
            
            return Map.of(
                "status", "awaiting_confirmation",
                "task_id", newTaskId,
                "step", "confirm",
                "question", String.format("Are you sure you want to delete %s '%s'? This cannot be undone.", dataType, dataId),
                "type", "confirm"
            );
        });
        
        // Document approval skill
        agent.skill("approve_document", SkillConfig.of("Approve or reject a document"), params -> {
            String taskId = (String) params.get("task_id");
            
            if (taskId != null && states.containsKey(taskId)) {
                String decision = (String) params.get("decision");
                InteractionState state = states.remove(taskId);
                
                return switch (decision != null ? decision : "") {
                    case "approve" -> Map.of(
                        "status", "approved",
                        "doc_id", state.docId,
                        "decision", "approved",
                        "approver", "user@example.com",
                        "message", "Document approved"
                    );
                    case "reject" -> Map.of(
                        "status", "rejected",
                        "doc_id", state.docId,
                        "decision", "rejected",
                        "message", "Document rejected"
                    );
                    case "request_changes" -> Map.of(
                        "status", "changes_requested",
                        "doc_id", state.docId,
                        "message", "Changes requested"
                    );
                    default -> Map.of("error", "Unknown decision: " + decision);
                };
            }
            
            // Initial request
            String docId = (String) params.getOrDefault("doc_id", "DOC-UNKNOWN");
            String docType = (String) params.getOrDefault("doc_type", "document");
            
            String newTaskId = generateTaskId();
            states.put(newTaskId, new InteractionState(docId, docType, "document"));
            
            return Map.of(
                "status", "awaiting_input",
                "task_id", newTaskId,
                "question", String.format("Document '%s' (%s) is pending your review. Please select an action:", docId, docType),
                "type", "choice",
                "options", java.util.List.of("approve", "reject", "request_changes")
            );
        });
        
        System.out.println("Human-in-the-Loop Agent (A2A Lite)");
        System.out.println("Skills: purchase, delete_data, approve_document");
        System.out.println();
        
        agent.run(8795);
    }
    
    private static String generateOrderId() {
        return "ORD-" + UUID.randomUUID().toString().substring(0, 8).toUpperCase();
    }
    
    private static String generateTaskId() {
        return "task-" + UUID.randomUUID().toString().substring(0, 6);
    }
    
    /**
     * Simple state holder for multi-step interactions
     */
    static class InteractionState {
        String item;
        double amount;
        String dataId;
        String dataType;
        String docId;
        String docType;
        String step;
        
        // For purchase
        InteractionState(String item, double amount) {
            this.item = item;
            this.amount = amount;
        }
        
        // For delete
        InteractionState(String dataId, String dataType) {
            this.dataId = dataId;
            this.dataType = dataType;
            this.step = "confirm";
        }
        
        // For document
        InteractionState(String docId, String docType, String type) {
            this.docId = docId;
            this.docType = docType;
        }
    }
}
