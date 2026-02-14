import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Agent, TaskContext, InMemoryTaskStore } from '../src/index.js';
import { AgentTestClient } from '../src/testing.js';

describe('TaskContext Auto-Injection', () => {
  describe('TaskContext Detection', () => {
    it('should auto-detect TaskContext parameter by type', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      const updates: Array<{ status: string; message?: string; progress?: number }> = [];

      agent.skill('process', async ({ data, task }: { data: string; task: TaskContext }) => {
        task.onStatusChange((status) => {
          updates.push({
            status: status.state,
            message: status.message,
            progress: status.progress,
          });
        });
        
        await task.update('working', 'Starting...', 0.0);
        await task.update('working', 'Processing...', 0.5);
        await task.update('completed', 'Done!', 1.0);
        
        return { result: `Processed: ${data}` };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('process', { data: 'test-data' });

      expect(result.data).toEqual({ result: 'Processed: test-data' });
      expect(updates).toHaveLength(3);
      expect(updates[0]).toMatchObject({ status: 'working', message: 'Starting...', progress: 0 });
      expect(updates[1]).toMatchObject({ status: 'working', message: 'Processing...', progress: 0.5 });
      expect(updates[2]).toMatchObject({ status: 'completed', message: 'Done!', progress: 1 });
    });

    it('should work with different parameter names', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      let capturedContext: TaskContext | null = null;

      // Using 'ctx' as parameter name instead of 'task'
      agent.skill('process', async ({ data, ctx }: { data: string; ctx: TaskContext }) => {
        capturedContext = ctx;
        await ctx.update('working', 'Processing...', 0.5);
        return { data };
      });

      const client = new AgentTestClient(agent);
      await client.call('process', { data: 'test' });

      expect(capturedContext).not.toBeNull();
      expect(capturedContext?.state).toBe('working');
    });

    it('should not inject TaskContext if taskStore is not configured', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test'
        // No taskStore configured
      });

      agent.skill('process', async ({ data }: { data: string }) => {
        return { result: data };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('process', { data: 'test' });

      expect(result.data).toEqual({ result: 'test' });
    });

    it('should work without TaskContext parameter', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      agent.skill('greet', async ({ name }: { name: string }) => {
        return `Hello, ${name}!`;
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('greet', { name: 'World' });

      expect(result.data).toBe('Hello, World!');
    });
  });

  describe('Task States', () => {
    it('should support all task states', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      const stateHistory: string[] = [];

      agent.skill('stateTest', async ({ task }: { task: TaskContext }) => {
        await task.update('submitted');
        stateHistory.push(task.state);
        
        await task.update('working');
        stateHistory.push(task.state);
        
        await task.update('input-required');
        stateHistory.push(task.state);
        
        await task.update('completed');
        stateHistory.push(task.state);
        
        return { states: stateHistory };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('stateTest', {});

      expect(result.data.states).toEqual([
        'submitted',
        'working', 
        'input-required',
        'completed'
      ]);
    });

    it('should handle failed state', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      agent.skill('failTask', async ({ task }: { task: TaskContext }) => {
        await task.fail('Something went wrong');
        expect(task.state).toBe('failed');
        return { status: 'failed' };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('failTask', {});
      expect(result.data.status).toBe('failed');
    });

    it('should support complete() convenience method', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      agent.skill('completeTask', async ({ task }: { task: TaskContext }) => {
        await task.complete('Task finished successfully');
        expect(task.state).toBe('completed');
        return { done: true };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('completeTask', {});
      expect(result.data.done).toBe(true);
    });
  });

  describe('TaskContext Properties', () => {
    it('should expose taskId property', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      let capturedId: string | null = null;

      agent.skill('getId', async ({ task }: { task: TaskContext }) => {
        capturedId = task.taskId;
        expect(typeof task.taskId).toBe('string');
        expect(task.taskId.length).toBeGreaterThan(0);
        return { id: task.taskId };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('getId', {});
      
      expect(result.data.id).toBe(capturedId);
    });

    it('should expose params property', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      agent.skill('getParams', async ({ name, value, task }: { name: string; value: number; task: TaskContext }) => {
        expect(task.params).toEqual({ name: 'test', value: 42 });
        return task.params;
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('getParams', { name: 'test', value: 42 });
      
      expect(result.data).toEqual({ name: 'test', value: 42 });
    });

    it('should track status history', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      agent.skill('trackHistory', async ({ task }: { task: TaskContext }) => {
        // Task starts in 'submitted' state
        await task.update('working');
        await task.update('working', 'Still working', 0.5);
        await task.update('completed');
        
        return { finalState: task.state };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('trackHistory', {});
      
      expect(result.data.finalState).toBe('completed');
    });
  });

  describe('Multiple Callbacks', () => {
    it('should support multiple status change callbacks', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      const callback1Calls: string[] = [];
      const callback2Calls: string[] = [];

      agent.skill('multiCallback', async ({ task }: { task: TaskContext }) => {
        task.onStatusChange((status) => {
          callback1Calls.push(status.state);
        });
        
        task.onStatusChange((status) => {
          callback2Calls.push(status.state);
        });
        
        await task.update('working');
        await task.update('completed');
        
        return { done: true };
      });

      const client = new AgentTestClient(agent);
      await client.call('multiCallback', {});

      expect(callback1Calls).toEqual(['working', 'completed']);
      expect(callback2Calls).toEqual(['working', 'completed']);
    });
  });

  describe('Error Handling', () => {
    it('should continue if a callback throws', async () => {
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: 'memory'
      });

      const goodCallbackCalls: string[] = [];
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      agent.skill('errorCallback', async ({ task }: { task: TaskContext }) => {
        task.onStatusChange(() => {
          throw new Error('Callback error');
        });
        
        task.onStatusChange((status) => {
          goodCallbackCalls.push(status.state);
        });
        
        await task.update('working');
        
        return { done: true };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('errorCallback', {});

      expect(result.data.done).toBe(true);
      expect(goodCallbackCalls).toEqual(['working']);
      expect(consoleWarnSpy).toHaveBeenCalled();

      consoleWarnSpy.mockRestore();
    });
  });

  describe('TaskStore Persistence', () => {
    it('should persist task state in store', async () => {
      const store = new InMemoryTaskStore();
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: store
      });

      agent.skill('persistTest', async ({ task }: { task: TaskContext }) => {
        await task.update('working', 'In progress');
        return { taskId: task.taskId };
      });

      const client = new AgentTestClient(agent);
      const result = await client.call('persistTest', { data: 'test' });

      // Verify task was stored
      const storedTask = store.get(result.data.taskId);
      expect(storedTask).toBeDefined();
      expect(storedTask?.status.state).toBe('working');
      expect(storedTask?.status.message).toBe('In progress');
    });

    it('should support listing tasks', async () => {
      const store = new InMemoryTaskStore();
      const agent = new Agent({ 
        name: 'Bot', 
        description: 'Test',
        taskStore: store
      });

      agent.skill('listTest', async ({ task }: { task: TaskContext }) => {
        return { taskId: task.taskId };
      });

      const client = new AgentTestClient(agent);
      
      // Create multiple tasks
      await client.call('listTest', { n: 1 });
      await client.call('listTest', { n: 2 });
      await client.call('listTest', { n: 3 });

      const tasks = store.list();
      expect(tasks.length).toBeGreaterThanOrEqual(3);
    });
  });
});
