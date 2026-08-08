/**
 * MCP (Model Context Protocol) client for A2A Lite TypeScript.
 *
 * Wraps the official @modelcontextprotocol/sdk to let skills call MCP tools.
 *
 * Requires: npm install @modelcontextprotocol/sdk
 *
 * Example:
 *   agent.addMcpServer("http://localhost:5001/sse");
 *
 *   agent.skill("research", async ({ query }, { mcp }) => {
 *     const result = await mcp.callTool("web_search", { query });
 *     return result;
 *   });
 */

export class MCPClient {
  private serverUrls: string[];
  private sessions: Map<string, unknown> = new Map();

  constructor(options?: { serverUrls?: string[] }) {
    this.serverUrls = options?.serverUrls?.slice() ?? [];
  }

  addServer(url: string): void {
    this.serverUrls.push(url);
  }

  private async getSession(url: string): Promise<any> {
    if (this.sessions.has(url)) return this.sessions.get(url);

    let Client: any, SSEClientTransport: any;
    try {
      // @ts-ignore — optional peer dependency, resolved at runtime
      const clientMod = await import('@modelcontextprotocol/sdk/client/index.js');
      // @ts-ignore — optional peer dependency, resolved at runtime
      const sseMod = await import('@modelcontextprotocol/sdk/client/sse.js');
      Client = clientMod.Client;
      SSEClientTransport = sseMod.SSEClientTransport;
    } catch {
      throw new Error(
        "MCP integration requires '@modelcontextprotocol/sdk'. " +
          'Install it with: npm install @modelcontextprotocol/sdk',
      );
    }

    const transport = new SSEClientTransport(new URL(url));
    const client = new Client({ name: 'a2a-lite-mcp-client', version: '1.0.0' }, { capabilities: {} });
    await client.connect(transport);
    this.sessions.set(url, client);
    return client;
  }

  /**
   * Call an MCP tool by name.
   *
   * If serverUrl is provided, calls that server directly.
   * Otherwise searches all registered servers.
   */
  async callTool(toolName: string, params: Record<string, unknown> = {}, serverUrl?: string): Promise<unknown> {
    const urls = serverUrl ? [serverUrl] : this.serverUrls;

    for (const url of urls) {
      try {
        const session = await this.getSession(url);
        const result = await session.callTool({ name: toolName, arguments: params });
        return extractMcpContent(result);
      } catch (err) {
        const msg = (err as Error).message?.toLowerCase() ?? '';
        if (msg.includes('not found') || msg.includes('unknown tool')) continue;
        throw err;
      }
    }

    throw new Error(`Tool '${toolName}' not found on any MCP server. Servers: ${urls.join(', ')}`);
  }

  /**
   * List available tools from MCP servers.
   */
  async listTools(
    serverUrl?: string,
  ): Promise<Array<{ name: string; description: string; inputSchema: unknown; serverUrl: string }>> {
    const urls = serverUrl ? [serverUrl] : this.serverUrls;
    const allTools: Array<{
      name: string;
      description: string;
      inputSchema: unknown;
      serverUrl: string;
    }> = [];

    for (const url of urls) {
      try {
        const session = await this.getSession(url);
        const response = await session.listTools();
        for (const tool of response.tools ?? []) {
          allTools.push({
            name: tool.name,
            description: tool.description ?? '',
            inputSchema: tool.inputSchema ?? {},
            serverUrl: url,
          });
        }
      } catch (err) {
        console.warn(`Failed to list tools from ${url}:`, err);
      }
    }

    return allTools;
  }

  /**
   * Read a resource from an MCP server.
   */
  async readResource(uri: string, serverUrl?: string): Promise<unknown> {
    const url = serverUrl ?? this.serverUrls[0];
    if (!url) throw new Error('No MCP server URLs configured');
    const session = await this.getSession(url);
    return session.readResource({ uri });
  }

  /**
   * Close all MCP sessions.
   */
  async close(): Promise<void> {
    for (const [url, session] of this.sessions) {
      try {
        await (session as any).close?.();
      } catch {
        console.warn(`Error closing MCP session for ${url}`);
      }
    }
    this.sessions.clear();
  }
}

function extractMcpContent(result: unknown): unknown {
  if (result && typeof result === 'object' && 'content' in result) {
    const contents = (result as any).content as unknown[];
    if (contents.length === 1) {
      const item = contents[0] as any;
      return item.text ?? item;
    }
    return contents.map((c: any) => c.text ?? c);
  }
  return result;
}
