/**
 * Multi-Agent Demo - Orchestrates multiple agents.
 *
 * First start: npx ts-node examples/04_multi_agent/finance_agent.ts
 *              npx ts-node examples/04_multi_agent/reporter_agent.ts
 * Then run:    npx ts-node examples/04_multi_agent/run_demo.ts
 */
async function callAgent(agentUrl: string, skill: string, params: Record<string, unknown>) {
  const response = await fetch(agentUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0', id: '1', method: 'message/send',
      params: { message: { role: 'user', parts: [{ kind: 'text', text: JSON.stringify({ skill, params }) }] } },
    }),
  });
  const result = await response.json() as any;
  const textPart = result.result?.parts?.find((p: any) => p.kind === 'text' || p.type === 'text');
  return textPart ? JSON.parse(textPart.text) : result.result;
}

async function runDemo() {
  console.log('🚀 Multi-Agent Demo\n');
  try {
    console.log('📊 Getting stock prices...');
    for (const symbol of ['AAPL', 'GOOGL', 'MSFT']) {
      const result = await callAgent('http://localhost:8788', 'get_stock_price', { symbol });
      console.log('   ' + symbol + ': $' + result.price);
    }

    console.log('\n💰 Calculating portfolio...');
    const portfolio = await callAgent('http://localhost:8788', 'get_portfolio_value', { holdings: { AAPL: 10, GOOGL: 5, MSFT: 8 } });
    console.log('   Total: $' + portfolio.total_value.toFixed(2));

    console.log('\n📝 Generating report...');
    const report = await callAgent('http://localhost:8789', 'generate_summary', { data: { portfolio_value: portfolio.total_value, stocks: 3 }, format: 'markdown' });
    console.log('\n' + report.report);

    console.log('\n✅ Demo complete!');
  } catch (e: any) {
    console.error('❌ Error: ' + e.message);
    console.log('\nStart agents first:\n  npx ts-node examples/04_multi_agent/finance_agent.ts\n  npx ts-node examples/04_multi_agent/reporter_agent.ts');
  }
}

runDemo();
