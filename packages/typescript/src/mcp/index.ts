/**
 * MCP (Model Context Protocol) tool integration for A2A Lite.
 * 
 * Wraps the MCP SDK to let skills call MCP tools.
 * 
 * Example:
 *   const agent = new Agent({ name: "Bot", mcpServers: ["http://localhost:5001"] });
 * 
 *   agent.skill("research", async ({ query, mcp }: { query: string; mcp: MCPClient }) => {
 *     const result = await mcp.callTool("web_search", { query });
 *     return result;
 *   });
 * 
 * Note: This is a stub implementation. Full MCP integration requires the MCP SDK.
 * Install with: npm install @modelcontextprotocol/sdk
 */

/**
 * Base exception for MCP-related errors.
 */
export class MCPError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MCPError';
  }
}

/**
 * Raised when a tool is not found on any MCP server.
 */
export class ToolNotFoundError extends MCPError {
  constructor(toolName: string) {
    super(`Tool '${toolName}' not found on any MCP server`);
    this.name = 'ToolNotFoundError';
  }
}

/**
 * Result from calling an MCP tool.
 */
export interface MCPToolResult {
  content: Array<
    | { type: 'text'; text: string }
    | { type: 'image'; data: string; mimeType: string }
    | { type: 'resource'; resource: unknown }
  >;
  isError?: boolean;
}

/**
 * Tool descriptor from MCP server.
 */
export interface MCPToolDescriptor {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
  serverUrl?: string;
}

/**
 * Client for interacting with MCP servers.
 * 
 * Provides a simplified interface to call tools, list tools, and
 * read resources from one or more MCP servers.
 * 
 * Example:
 *   const mcp = new MCPClient(["http://localhost:5001"]);
 *   const result = await mcp.callTool("web_search", { query: "A2A protocol" });
 *   const tools = await mcp.listTools();
 */
export class MCPClient {
  private _serverUrls: string[];
  private _sessions: Map<string, unknown> = new Map();

  /**
   * Create a new MCP client.
   * 
   * @param serverUrls - List of MCP server URLs to connect to
   */
  constructor(serverUrls?: string[]) {
    // Deduplicate URLs while preserving order
    this._serverUrls = [...new Set(serverUrls ?? [])];
  }

  /**
   * Get the list of configured server URLs.
   */
  get serverUrls(): string[] {
    return [...this._serverUrls];
  }

  /**
   * Get the internal sessions map (for testing).
   * @internal
   */
  get sessions(): Map<string, unknown> {
    return this._sessions;
  }

  /**
   * Add an MCP server URL.
   * 
   * @param url - The MCP server URL
   */
  addServer(url: string): void {
    if (!this._serverUrls.includes(url)) {
      this._serverUrls.push(url);
    }
  }

  /**
   * Get or create an MCP client session for a server URL.
   * 
   * @param url - The MCP server URL
   * @returns An MCP ClientSession instance
   * @throws MCPError if the MCP SDK is not installed or connection fails
   */
  private async _getSession(url: string): Promise<unknown> {
    if (this._sessions.has(url)) {
      return this._sessions.get(url);
    }

    // This is a stub implementation
    // In a real implementation, this would:
    // 1. Import the MCP SDK
    // 2. Create a ClientSession
    // 3. Initialize the session
    // 4. Store it for reuse
    
    throw new MCPError(
      'MCP integration requires the @modelcontextprotocol/sdk package. ' +
      'Install it with: npm install @modelcontextprotocol/sdk'
    );
  }

  /**
   * Call an MCP tool by name.
   * 
   * If `serverUrl` is provided, calls that specific server.
   * Otherwise searches all registered servers for the tool.
   * 
   * @param toolName - The name of the MCP tool to call
   * @param args - Arguments to pass to the tool
   * @param serverUrl - Optional specific server URL to use
   * @returns The tool's result content
   * @throws ToolNotFoundError if the tool is not found on any server
   * @throws MCPError if the MCP SDK is not installed
   */
  async callTool(
    toolName: string,
    args?: Record<string, unknown>,
    serverUrl?: string
  ): Promise<unknown> {
    const urls = serverUrl ? [serverUrl] : this._serverUrls;
    
    if (urls.length === 0) {
      throw new MCPError('No MCP server URLs configured');
    }

    let lastError: Error | null = null;

    for (const url of urls) {
      try {
        const session = await this._getSession(url);
        // In a real implementation:
        // const result = await session.callTool(toolName, { arguments: args ?? {} });
        // return this._extractContent(result);
        
        // Stub: simulate a successful call
        return { result: 'stub', tool: toolName, args };
      } catch (error) {
        if (error instanceof MCPError) {
          throw error; // Re-throw SDK not installed error
        }
        
        if (this._isToolNotFoundError(error as Error)) {
          lastError = error as Error;
          continue; // Try next server
        }
        
        // Other errors - re-raise
        throw error;
      }
    }

    // Tool not found on any server
    throw new ToolNotFoundError(toolName);
  }

  /**
   * Check if an exception indicates a tool was not found.
   * 
   * This method attempts to detect tool-not-found errors without relying
   * solely on fragile string matching. It tries:
   * 1. Check for specific MCP SDK exception types
   * 2. Check for common error code patterns
   * 3. Fallback to checking error message content
   * 
   * @param error - The exception to check
   * @returns True if the error indicates the tool was not found
   */
  private _isToolNotFoundError(error: Error): boolean {
    // Try to detect specific MCP SDK exception types
    const errorType = error.constructor.name.toLowerCase();
    if (errorType.includes('tool') && (errorType.includes('notfound') || errorType.includes('missing'))) {
      return true;
    }

    // Check for common error attributes (some SDKs use error codes)
    const errorWithCode = error as Error & { code?: string | number };
    if (errorWithCode.code !== undefined) {
      const code = errorWithCode.code;
      if (code === 'TOOL_NOT_FOUND' || code === 'METHOD_NOT_FOUND' || code === -32601) {
        return true;
      }
    }

    // Check error message as last resort (more specific patterns first)
    const errorStr = error.message.toLowerCase();
    const specificPatterns = [
      'unknown tool',
      'tool not found',
      "tool '",
      'tool "',
      'no tool named',
      'tool does not exist',
    ];
    
    for (const pattern of specificPatterns) {
      if (errorStr.includes(pattern)) {
        return true;
      }
    }

    // Generic "not found" only if tool is mentioned
    if (errorStr.includes('not found') && errorStr.includes('tool')) {
      return true;
    }

    return false;
  }

  /**
   * List available tools from MCP servers.
   * 
   * @param serverUrl - If provided, list tools from this server only
   * @returns List of tool descriptors with name, description, and input schema
   */
  async listTools(serverUrl?: string): Promise<MCPToolDescriptor[]> {
    const urls = serverUrl ? [serverUrl] : this._serverUrls;
    const allTools: MCPToolDescriptor[] = [];

    for (const url of urls) {
      try {
        const session = await this._getSession(url);
        // In a real implementation:
        // const response = await session.listTools();
        // for (const tool of response.tools) {
        //   allTools.push({
        //     name: tool.name,
        //     description: tool.description ?? '',
        //     inputSchema: tool.inputSchema ?? {},
        //     serverUrl: url,
        //   });
        // }
        
        // Stub: return empty
      } catch {
        // Silently skip servers that fail
      }
    }

    return allTools;
  }

  /**
   * Read a resource from an MCP server.
   * 
   * @param uri - The resource URI to read
   * @param serverUrl - If provided, read from this server only
   * @returns The resource content
   * @throws MCPError if no servers are configured
   */
  async readResource(uri: string, serverUrl?: string): Promise<unknown> {
    const url = serverUrl ?? (this._serverUrls[0] || null);
    
    if (url === null) {
      throw new MCPError('No MCP server URLs configured');
    }

    const session = await this._getSession(url);
    // In a real implementation:
    // return await session.readResource(uri);
    
    // Stub
    return { uri, content: 'stub' };
  }

  /**
   * Close all MCP sessions.
   */
  async close(): Promise<void> {
    // Close all sessions
    for (const [url, session] of this._sessions.entries()) {
      try {
        // In a real implementation:
        // await session.close();
      } catch {
        // Ignore errors during cleanup
      }
    }
    this._sessions.clear();
  }

  /**
   * Extract content from an MCP tool result.
   * 
   * @param result - The raw MCP CallToolResult
   * @returns The extracted content as a string or array
   */
  private _extractContent(result: MCPToolResult): unknown {
    if (!result.content || result.content.length === 0) {
      return result;
    }

    const contents = result.content;
    
    if (contents.length === 1) {
      const item = contents[0];
      if (item.type === 'text') {
        return item.text;
      }
      return item;
    }

    return contents.map(c => c.type === 'text' ? c.text : c);
  }

  /**
   * Get string representation.
   */
  toString(): string {
    return `MCPClient(servers=${JSON.stringify(this._serverUrls)})`;
  }
}
