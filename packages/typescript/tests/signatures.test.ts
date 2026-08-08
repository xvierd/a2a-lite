import { describe, it, expect } from 'vitest';
import { Agent, signAgentCard, verifyAgentCard, canonicalizeAgentCard } from '../src/index.js';

async function generateKeyPair() {
  // jose is bundled with @a2a-js/sdk — resolved transitively.
  const jose = await import('jose');
  return jose.generateKeyPair('ES256');
}

describe('Agent Card signatures (experimental)', () => {
  it('signs a card and verifies the signature', async () => {
    const { publicKey, privateKey } = await generateKeyPair();

    const agent = new Agent({ name: 'SignedBot', description: 'Signed agent' });
    agent.skill('greet', async () => 'hi');
    const card = agent.buildAgentCard();

    const signer = signAgentCard(privateKey, { alg: 'ES256', kid: 'key-1', typ: 'JOSE' });
    const signedCard = await signer(card);

    expect(signedCard.signatures).toHaveLength(1);
    expect(signedCard.signatures[0].protected).toBeTruthy();
    expect(signedCard.signatures[0].signature).toBeTruthy();

    const verify = verifyAgentCard(async (kid) => {
      expect(kid).toBe('key-1');
      return publicKey;
    });

    await expect(verify(signedCard)).resolves.toBeUndefined();
  });

  it('rejects a tampered card', async () => {
    const { publicKey, privateKey } = await generateKeyPair();

    const agent = new Agent({ name: 'SignedBot', description: 'Signed agent' });
    agent.skill('greet', async () => 'hi');

    const signer = signAgentCard(privateKey, { alg: 'ES256', kid: 'key-1', typ: 'JOSE' });
    const signedCard = await signer(agent.buildAgentCard());

    const tampered = { ...signedCard, description: 'tampered description' };

    const verify = verifyAgentCard(async () => publicKey);
    await expect(verify(tampered)).rejects.toThrow();
  });

  it('canonicalizeAgentCard produces a stable payload without signatures', async () => {
    const agent = new Agent({ name: 'Bot', description: 'Test' });
    agent.skill('greet', async () => 'hi');
    const card = agent.buildAgentCard();

    const canonical = canonicalizeAgentCard(card);
    expect(typeof canonical).toBe('string');
    expect(canonical).not.toContain('signatures');
    expect(canonical).toContain('Bot');
  });
});
