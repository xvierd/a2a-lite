// The SDK migrations run first in durable.py; this adds the Lite transaction/lease tables.
import { migratePostgresRuntime } from '../../packages/typescript/src/index.ts';

if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is required');
await migratePostgresRuntime({ connectionString: process.env.DATABASE_URL });
