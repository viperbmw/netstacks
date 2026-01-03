import { test, expect } from '@playwright/test';

// Helper to set auth tokens in localStorage before page load.
// NOTE: We log in against the running Auth service to obtain a *real* JWT.
// This avoids flakiness when NETSTACKS_DEV_MODE=false (default in docker-compose).
async function setupAuth(page) {
  const loginResponse = await page.request.post('/api/auth/login', {
    data: { username: 'admin', password: 'admin' },
  });

  expect(loginResponse.ok()).toBeTruthy();
  const login = await loginResponse.json();

  const accessToken = login.access_token;
  const refreshToken = login.refresh_token;
  const expiresIn = login.expires_in || 1800;

  expect(accessToken).toBeTruthy();

  await page.addInitScript(
    ({ accessToken, refreshToken, expiresIn }) => {
      const TOKEN_KEY = 'netstacks_jwt_token';
      const REFRESH_TOKEN_KEY = 'netstacks_jwt_refresh';
      const TOKEN_EXPIRY_KEY = 'netstacks_jwt_expiry';

      localStorage.setItem(TOKEN_KEY, accessToken);
      if (refreshToken) {
        localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
      }
      // Match api-client.js behaviour: store expiry as ms epoch with a 60s buffer.
      const expiryTime = Date.now() + ((expiresIn - 60) * 1000);
      localStorage.setItem(TOKEN_EXPIRY_KEY, String(expiryTime));
    },
    { accessToken, refreshToken, expiresIn }
  );
}

test.describe('NetStacks Frontend Tests', () => {

  test.describe('Login Page', () => {
    test('should load login page', async ({ page }) => {
      await page.goto('/login');
      await expect(page).toHaveTitle(/NetStacks/);
      await expect(page.locator('input[name="username"], #username')).toBeVisible();
    });

    test('should successfully login with valid credentials', async ({ page }) => {
      await page.goto('/login');
      await page.fill('input[name="username"], #username', 'admin');
      await page.fill('input[name="password"], #password', 'admin');
      await page.click('button[type="submit"]');

      // Wait for redirect to dashboard or any non-login page
      await page.waitForURL(url => !url.pathname.includes('login'), { timeout: 15000 });
      await expect(page.locator('.navbar-brand')).toBeVisible();
    });
  });

  test.describe('Dashboard', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('should load dashboard after login', async ({ page }) => {
      await page.goto('/');
      await expect(page.locator('.navbar-brand')).toContainText('NetStacks');
    });
  });

  test.describe('AI Settings Page', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('should load AI settings page', async ({ page }) => {
      await page.goto('/settings/ai');
      await expect(page.locator('h3, h1')).toContainText('AI Settings');
    });

    test('should display LLM providers section', async ({ page }) => {
      await page.goto('/settings/ai');
      await expect(page.locator('.card-header h5:has-text("LLM Providers")')).toBeVisible();
    });

    test('should be able to open Add Provider modal', async ({ page }) => {
      await page.goto('/settings/ai');
      await page.click('button:has-text("Add Provider")');
      await expect(page.locator('#providerModal')).toBeVisible();
    });

    test('should save AI settings', async ({ page }) => {
      await page.goto('/settings/ai');

      // Fill in temperature field
      await page.fill('#default-temperature', '0.5');

      // Click save button
      await page.click('button:has-text("Save Settings")');

      // Check for success (no error alert)
      await page.waitForTimeout(1000);
      const errorAlert = page.locator('.alert-danger');
      await expect(errorAlert).toHaveCount(0);
    });
  });

  test.describe('Agents Page', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('should load agents page', async ({ page }) => {
      await page.goto('/agents');
      await expect(page.locator('h1')).toContainText('AI Agents');
    });

    test('should display workflow diagram', async ({ page }) => {
      await page.goto('/agents');
      await expect(page.locator('#workflow-diagram')).toBeVisible();
    });

    test('should load agents list', async ({ page }) => {
      await page.goto('/agents');

      // Wait for loading to complete
      await page.waitForSelector('#agents-loading', { state: 'hidden', timeout: 10000 });

      // Either agents-container or agents-empty should be visible
      const container = page.locator('#agents-container:visible, #agents-empty:visible');
      await expect(container.first()).toBeVisible();
    });

    test('should be able to expand create agent panel', async ({ page }) => {
      await page.goto('/agents');
      await page.click('button[data-bs-target="#create-agent-panel"]');
      await expect(page.locator('#create-agent-panel')).toBeVisible();
    });

    test('should create a new agent', async ({ page }) => {
      await page.goto('/agents');

      // Expand create agent panel
      await page.click('button[data-bs-target="#create-agent-panel"]');
      await page.waitForSelector('#create-agent-panel.show');

      // Fill in agent details
      await page.fill('#agent-name', 'TestPlaywrightAgent');
      await page.selectOption('#agent-type', 'general');

      // Submit form
      await page.click('#create-agent-form button[type="submit"]');

      // Wait for success toast or reload
      await page.waitForTimeout(2000);

      // Verify agent appears in list (may have multiple if test ran before)
      await expect(page.locator('text=TestPlaywrightAgent').first()).toBeVisible({ timeout: 10000 });
    });
  });

  test.describe('Alerts Page', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('should load alerts page', async ({ page }) => {
      await page.goto('/alerts');
      await expect(page.locator('h1, h3')).toContainText(/Alert/i);
    });
  });

  test.describe('Devices Page', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('should load devices page', async ({ page }) => {
      await page.goto('/devices');
      // Devices page is the config_backups.html view and its primary heading is "Devices".
      await expect(page.locator('h1')).toContainText(/Devices/i);
    });
  });

  test.describe('Templates Page', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('should load templates page', async ({ page }) => {
      await page.goto('/templates');
      // Be explicit to avoid strict-mode violations (dashboard has multiple h3 counters).
      await expect(page.locator('h1')).toContainText(/Template/i);
    });
  });

  test.describe('Navigation', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('should navigate to all main pages', async ({ page }) => {
      const pages = [
        { url: '/', title: /NetStacks/ },
        { url: '/devices', title: /Device/i },
        { url: '/templates', title: /Template/i },
        { url: '/agents', title: /Agent/i },
        { url: '/alerts', title: /Alert/i },
        { url: '/incidents', title: /Incident/i },
        { url: '/settings', title: /Setting/i },
      ];

      for (const { url, title } of pages) {
        await page.goto(url);
        await expect(page).toHaveTitle(title);
      }
    });
  });

  test.describe('API Endpoints via UI', () => {
    test.beforeEach(async ({ page }) => {
      await setupAuth(page);
    });

    test('agents stats should load on agents page', async ({ page }) => {
      await page.goto('/agents');

      // Stats cards should populate
      await page.waitForTimeout(2000);

      const activeCount = page.locator('#active-agents-count');
      const totalCount = page.locator('#total-agents-count');

      await expect(activeCount).not.toHaveText('-');
      await expect(totalCount).not.toHaveText('-');
    });
  });
});
