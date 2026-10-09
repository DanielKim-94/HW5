import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests', workers: 1, timeout: 30000,
  use: { baseURL: 'http://localhost:5174', browserName: 'chromium', channel: 'chrome', viewport: { width: 1440, height: 1100 } },
  reporter: 'list',
});
