import { defineConfig } from 'tsup';

export default defineConfig([
  // Library build
  {
    entry: ['src/index.ts'],
    format: ['esm', 'cjs'],
    dts: true,
    clean: true,
  },
  // CLI build — shebang required so npm treats it as a valid bin
  {
    entry: ['src/cli.ts'],
    format: ['esm', 'cjs'],
    dts: false,
    banner: {
      js: '#!/usr/bin/env node',
    },
  },
]);
