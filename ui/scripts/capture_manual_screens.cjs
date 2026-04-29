const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const baseUrl = 'http://127.0.0.1:3000';
const outDir = path.resolve(__dirname, '..', '..', 'manual_screens');
fs.mkdirSync(outDir, { recursive: true });

async function setupMockRoutes(page) {
  await page.route(/.*\/auth\/me(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: {
          id: 1,
          name: 'Demo Admin',
          email: 'admin@example.com',
          organization: 'LAW LLM',
          use_case: 'Manual testing',
          advocate_address: 'Demo Chambers, City',
          advocate_mobile: '+91-9999999999',
          role: 'admin',
          status: 'granted',
          access_granted: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      }),
    });
  });

  await page.route(/.*\/chat\/sessions(\?.*)?$/, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        sessions: [
          {
            session_id: 's1',
            title: 'Tenant dispute notice',
            last_message_at: new Date().toISOString(),
            message_count: 4,
            preview: 'Need advice on non-payment and notice.',
          },
        ],
      }),
    });
  });

  await page.route(/.*\/admin\/.*/, async (route) => {
    const url = route.request().url();
    if (url.includes('/tenants')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ tenants: [] }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, users: [], events: [], summary: { total: 0, unique_ips: 0, authenticated: 0, anonymous: 0, failed: 0 } }) });
  });

  await page.route(/.*\/api\/.*/, async (route) => {
    const url = route.request().url();
    if (url.includes('/api/auth/me')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user: {
            id: 1,
            name: 'Demo Admin',
            email: 'admin@example.com',
            organization: 'LAW LLM',
            use_case: 'Manual testing',
            advocate_address: 'Demo Chambers, City',
            advocate_mobile: '+91-9999999999',
            role: 'admin',
            status: 'granted',
            access_granted: true,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
        }),
      });
      return;
    }
    if (url.includes('/api/chat/sessions')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sessions: [
            {
              session_id: 's1',
              title: 'Tenant dispute notice',
              last_message_at: new Date().toISOString(),
              message_count: 4,
              preview: 'Need advice on non-payment and notice.',
            },
          ],
        }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
  });
}

async function capturePublicPages(browser) {
  const page = await browser.newPage({ viewport: { width: 1512, height: 900 } });
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.screenshot({ path: path.join(outDir, '01_login.png'), fullPage: true });

  await page.getByRole('button', { name: /request access/i }).click();
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(outDir, '02_request_access.png'), fullPage: true });

  await page.goto(`${baseUrl}/?setup_token=demo-token-123`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(outDir, '03_set_password.png'), fullPage: true });
  await page.close();
}

async function captureAuthedPage(browser, tab, fileName) {
  const context = await browser.newContext({ viewport: { width: 1512, height: 900 } });
  const page = await context.newPage();
  await setupMockRoutes(page);
  await page.addInitScript((activeTab) => {
    localStorage.setItem('vidhi_auth_token', 'demo-token');
    localStorage.setItem('vidhi_theme_mode', 'dark');
    localStorage.setItem('vidhi_active_tab', activeTab);
  }, tab);
  await page.goto(baseUrl, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(outDir, fileName), fullPage: true });
  await context.close();
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  try {
    await capturePublicPages(browser);
    await captureAuthedPage(browser, 'chat', '04_legal_chat.png');
    await captureAuthedPage(browser, 'generator', '05_document_generator.png');
    await captureAuthedPage(browser, 'analyzer', '06_document_analyzer.png');
    await captureAuthedPage(browser, 'settings', '07_settings.png');
    await captureAuthedPage(browser, 'admin', '08_admin_access.png');
  } finally {
    await browser.close();
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
