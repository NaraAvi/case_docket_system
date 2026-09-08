import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['app/static/js/tests/**/*.test.js'],
    restoreMocks: true,
  },
});
