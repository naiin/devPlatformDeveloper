#!/usr/bin/env node
// Browser and authorization checks. Requires the checked-in Backstage dependencies.
const { chromium } = require('../backstage/node_modules/playwright');
const fs = require('node:fs/promises');
(async () => {
  const browser = await chromium.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  let identity;
  page.on('response', async response => {
    if (response.url().includes('/auth/guest/refresh') && response.ok()) {
      const data = await response.json().catch(() => ({}));
      identity = data.backstageIdentity?.token;
    }
  });
  await page.goto('http://demo.talos.test/backstage/', { waitUntil: 'networkidle', timeout: 90000 });
  console.log((await page.locator('body').innerText()).slice(0, 1200));
  const enter = page.getByRole('button', { name: /^enter$/i });
  if (await enter.count()) await enter.click();
  await page.waitForTimeout(5000);
  await page.screenshot({ path: 'generated/backstage-catalog.png', fullPage: true });
  const text = await page.locator('body').innerText();
  if (!text.includes('platform-api')) throw new Error('Platform catalog component did not render');
  if (!identity) throw new Error('Guest identity was not issued');
  const headers = { Authorization: `Bearer ${identity}`, 'Content-Type': 'application/json' };
  const entities = await page.request.get('http://demo.talos.test/backstage/api/catalog/entities', { headers });
  if (!entities.ok()) throw new Error(`Catalog request failed: ${entities.status()}`);
  const data = await entities.json();
  if (!data.some(e => e.kind === 'Template' && e.metadata.name === 'create-fastapi-microservice')) throw new Error('FastAPI template missing');
  const denied = await page.request.post('http://demo.talos.test/backstage/api/scaffolder/v2/tasks', {
    headers, data: { templateRef: 'template:default/create-fastapi-microservice', values: { name: 'portal-verify', description: 'Authorization verification' }, secrets: {} },
  });
  if (denied.status() !== 403) throw new Error(`Guest task submission should return 403, received ${denied.status()}`);
  await fs.writeFile('generated/backstage-proof.json', JSON.stringify({ verifiedAt: new Date().toISOString(), portal: 'http://demo.talos.test/backstage/', catalogEntities: data.length, templateRegistered: true, guestTaskCreationStatus: denied.status(), githubPublishingVerified: false }, null, 2));
  console.log('Catalog UI, FastAPI template and guest write denial verified.');
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
