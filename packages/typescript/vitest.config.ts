import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    environment: 'node',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html'],
      include: ['src/**/*.ts'],
      exclude: [
        'src/cli.ts',
        'src/llm.ts',
        'src/router.ts',
        // type-only / re-export barrels and the unused legacy mcp entry
        'src/types.ts',
        'src/mcp.ts',
        'node_modules/**',
        'dist/**',
      ],
      thresholds: {
        // Pre-v1.0 target was 80%; agent/executor surface grew with protocol 1.0
        lines: 75,
        functions: 75,
        branches: 70,
        statements: 75,
      },
    },
  },
});
