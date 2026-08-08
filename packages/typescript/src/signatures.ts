/**
 * Agent Card signatures (experimental) — A2A v1.0.
 *
 * Thin wrappers over the official SDK's JWS-based card signing utilities.
 * The SDK bundles `jose`, so no extra dependency is required for basic use.
 *
 * Example:
 *   import { Agent, signAgentCard, verifyAgentCard } from 'a2a-lite';
 *
 *   const signer = signAgentCard(privateKey, { alg: 'ES256', kid: 'key-1', typ: 'JOSE' });
 *   const signedCard = await signer(agent.buildAgentCard());
 *
 *   const verify = verifyAgentCard(async (kid) => fetchPublicKey(kid));
 *   await verify(signedCard); // throws if no valid signature
 */

import {
  generateAgentCardSignature,
  verifyAgentCardSignature,
  canonicalizeAgentCard,
} from '@a2a-js/sdk';

export type SignaturePrivateKey = Parameters<typeof generateAgentCardSignature>[0];
export type SignatureProtectedHeader = Parameters<typeof generateAgentCardSignature>[1];
export type SignatureUnprotectedHeader = Parameters<typeof generateAgentCardSignature>[2];
export type SignatureKeyResolver = Parameters<typeof verifyAgentCardSignature>[0];
export type AgentCardSigner = ReturnType<typeof generateAgentCardSignature>;
export type AgentCardVerifier = ReturnType<typeof verifyAgentCardSignature>;

/**
 * Create a signer that signs an agent card with JWS (Flattened JSON
 * Serialization) over a JCS (RFC 8785) canonicalization of the card.
 * `protectedHeader` MUST include `alg`, `kid` and `typ`.
 */
export function signAgentCard(
  privateKey: SignaturePrivateKey,
  protectedHeader: SignatureProtectedHeader,
  header?: SignatureUnprotectedHeader,
): AgentCardSigner {
  return generateAgentCardSignature(privateKey, protectedHeader, header);
}

/**
 * Create a verifier that succeeds if at least one signature on the card
 * verifies against a key returned by `keyResolver(kid, jku)`.
 */
export function verifyAgentCard(keyResolver: SignatureKeyResolver): AgentCardVerifier {
  return verifyAgentCardSignature(keyResolver);
}

export { canonicalizeAgentCard };
