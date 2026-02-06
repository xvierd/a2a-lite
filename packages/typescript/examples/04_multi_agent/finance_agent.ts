/**
 * Finance Agent - Part of multi-agent example.
 *
 * Run: npx ts-node examples/04_multi_agent/finance_agent.ts
 */
import { Agent } from '../../src';

const stockPrices: Record<string, number> = { AAPL: 178.50, GOOGL: 141.25, MSFT: 378.90, AMZN: 178.25, TSLA: 248.50 };

const agent = new Agent({ name: 'FinanceAgent', description: 'Financial data and analysis' });

agent.skill('get_stock_price', { description: 'Get stock price', tags: ['finance'] }, async ({ symbol }: { symbol: string }) => {
  const price = stockPrices[symbol.toUpperCase()];
  if (!price) return { error: 'Unknown symbol: ' + symbol };
  return { symbol: symbol.toUpperCase(), price, currency: 'USD' };
});

agent.skill('get_portfolio_value', { description: 'Calculate portfolio value', tags: ['finance'] }, async ({ holdings }: { holdings: Record<string, number> }) => {
  let total = 0;
  const details: Array<{ symbol: string; shares: number; price: number; value: number }> = [];
  for (const [symbol, shares] of Object.entries(holdings)) {
    const price = stockPrices[symbol.toUpperCase()] || 0;
    const value = price * shares;
    total += value;
    details.push({ symbol: symbol.toUpperCase(), shares, price, value });
  }
  return { total_value: total, currency: 'USD', holdings: details };
});

agent.run({ port: 8788 });
