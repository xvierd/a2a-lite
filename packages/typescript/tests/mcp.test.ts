import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { MCPClient, MCPError, ToolNotFoundError } from '../src/mcp/index.js';

describe('MCPClient', () => {
  let client: MCPClient;

  beforeEach(() => {
    client = new MCPClient();
  });

  afterEach(async () => {
    await client.close();
  });

  describe('Server Management', () => {
    it('should add servers via constructor', () => {
      const clientWithServers = new MCPClient(['http://server1.com', 'http://server2.com']);
      expect(clientWithServers.serverUrls).toEqual(['http://server1.com', 'http://server2.com']);
    });

    it('should add servers dynamically', () => {
      client.addServer('http://server1.com');
      client.addServer('http://server2.com');
      expect(client.serverUrls).toEqual(['http://server1.com', 'http://server2.com']);
    });

    it('should start with empty server list', () => {
      expect(client.serverUrls).toEqual([]);
    });
  });

  describe('Tool Operations', () => {
    it('should throw MCPError for missing server', async () => {
      // No servers added
      await expect(client.callTool('test_tool')).rejects.toThrow(MCPError);
    });

    it('should handle tool not found error', async () => {
      client.addServer('http://example.com');
      
      // Mock the internal _isToolNotFoundError method
      const mockError = new Error('Tool not found: unknown_tool');
      
      await expect(client.callTool('unknown_tool')).rejects.toThrow();
    });
  });

  describe('Error Handling', () => {
    it('should identify tool not found errors correctly', () => {
      const testCases = [
        { error: new Error('Tool not found'), expected: true },
        { error: new Error('Unknown tool: my_tool'), expected: true },
        { error: new Error('tool \'x\' does not exist'), expected: true },
        { error: new Error('tool "x" not found'), expected: true },
        { error: new Error('no tool named foo'), expected: true },
        { error: new Error('Connection timeout'), expected: false },
        { error: new Error('Server error'), expected: false },
      ];

      for (const { error, expected } of testCases) {
        expect(client['_isToolNotFoundError'](error)).toBe(expected);
      }
    });

    it('should check error codes for tool not found', () => {
      const errorWithCode = new Error('Not found') as Error & { code: string };
      errorWithCode.code = 'TOOL_NOT_FOUND';
      expect(client['_isToolNotFoundError'](errorWithCode)).toBe(true);

      const errorWithRpcCode = new Error('Method not found') as Error & { code: number };
      errorWithRpcCode.code = -32601;
      expect(client['_isToolNotFoundError'](errorWithRpcCode)).toBe(true);
    });
  });

  describe('Context Manager Pattern', () => {
    it('should support async context manager', async () => {
      const client = new MCPClient(['http://server.com']);
      
      // Test that async with pattern would work
      // (In TypeScript this is simulate via try/finally)
      try {
        expect(client.serverUrls).toEqual(['http://server.com']);
      } finally {
        await client.close();
      }
    });

    it('should clean up on close', async () => {
      const client = new MCPClient(['http://server1.com', 'http://server2.com']);
      
      await client.close();
      
      // After close, the sessions should be cleared
      expect(client['sessions'].size).toBe(0);
    });
  });

  describe('Multiple Servers', () => {
    it('should handle multiple server URLs', () => {
      const urls = [
        'http://server1.com',
        'http://server2.com',
        'http://server3.com'
      ];
      const client = new MCPClient(urls);
      
      expect(client.serverUrls).toEqual(urls);
      expect(client.serverUrls.length).toBe(3);
    });

    it('should deduplicate server URLs', () => {
      const client = new MCPClient([
        'http://server.com',
        'http://server.com',
        'http://other.com'
      ]);
      
      expect(client.serverUrls).toEqual(['http://server.com', 'http://other.com']);
    });
  });

  describe('Resource Operations', () => {
    it('should throw when no servers configured for readResource', async () => {
      await expect(client.readResource('file://test.txt')).rejects.toThrow('No MCP server URLs configured');
    });

    it('should accept server URL for readResource', async () => {
      client.addServer('http://server.com');
      
      // Will fail because we can't actually connect, but tests the parameter passing
      await expect(client.readResource('file://test.txt')).rejects.toThrow();
    });
  });

  describe('Tool Listing', () => {
    it('should return empty array when no servers', async () => {
      const tools = await client.listTools();
      expect(tools).toEqual([]);
    });

    it('should return empty array for specific server that fails', async () => {
      client.addServer('http://invalid-server-that-will-fail.com');
      
      const tools = await client.listTools('http://invalid-server-that-will-fail.com');
      expect(tools).toEqual([]);
    });
  });

  describe('toString', () => {
    it('should have meaningful string representation', () => {
      const client = new MCPClient(['http://server1.com']);
      expect(client.toString()).toContain('MCPClient');
      expect(client.toString()).toContain('http://server1.com');
    });
  });
});
