'use strict';

/**
 * Bounded browser acceptance for the actual recorder and review HTML/CSS/JS.
 * All state, vocabulary and video are explicitly synthetic. The native bridge
 * is replaced before navigation; no recording, uploads, device access or user
 * files are involved. This does not establish native WebView2/OBS acceptance.
 *
 * Run: node tests/test_ui_browser.cjs
 * Supply Playwright through NODE_PATH or PLAYWRIGHT_MODULE when not installed
 * in this project. Existing Edge is used; no browser/dependency is downloaded.
 * Optional: TAR_UI_CHANNEL, TAR_UI_OUTPUT (default work/visual-acceptance).
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const output = path.resolve(process.env.TAR_UI_OUTPUT || path.join(root, 'work', 'visual-acceptance'));
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));
const bundledWords = read('vocabularies/uiux-terms.txt').split(/\r?\n/).map(word=>word.trim()).filter(word=>word&&!word.startsWith('#'));
const bundledVocabulary = {id:'bundled-uiux-browser-fixture',name:'uiux-terms.txt',words:bundledWords};
const words = [
  '这是合成测试：这个入口很显眼，但我没找到返回的地方。',
  '这是合成测试：我猜这个标记表示任务还没完成。',
  '这是合成测试：我想先绕到右边，看看有没有别的路线。',
  '这是合成测试：原来点这里就能过去，比我预想的简单。',
];
const importedFiles = [
  { id: 'synthetic-game', name: '示例游戏词库.txt', words: ['测试关卡', '交互入口'] },
  { id: 'synthetic-characters', name: '示例角色词库.scel', words: ['测试角色', '交互入口'] },
];

function snapshot(overrides = {}) {
  return {
    config: {
      game: '示例游戏 · 合成测试', vault: 'D:\\synthetic-only\\think-aloud-database',
      preset: '均衡 1080p30', source: '游戏窗口', window: 'synthetic-window', monitor: 'synthetic-display',
      mic: 'synthetic-mic', language: 'zh', hotwords: '交互入口\n确认反馈',
      hotword_files: [{ id: 'synthetic-reference', name: '示例交互术语.txt', words: ['交互入口', '确认反馈'] }],
      hotword_manual: '', transcription_provider: 'qwen', configured: true,
    },
    presets: [{ id: 'synthetic-one', name: '示例游戏 · 合成测试', vault: 'D:\\synthetic-only\\think-aloud-database' }],
    active_preset_id: 'synthetic-one',
    default_hotword_files: [bundledVocabulary],
    suggested_vault: 'D:\\synthetic-only\\think-aloud-database',
    readiness: { ready: true, checking: false, errors: [], checked_at: 123 },
    activity: { busy: false, kind: 'idle', status: '待开始', detail: '' },
    background_jobs: [{ session_id: 'synthetic-session-0', state: 'running', detail: '合成测试进度：正在整理，可继续录制。' }],
    sessions: Array.from({ length: 14 }, (_, i) => ({
      id: `synthetic-session-${i}`, game: i % 3 === 2 ? '另一个示例游戏' : '示例游戏',
      created: `2026-09-${String(22 - i).padStart(2, '0')}T10:30:00`, duration: 438 + i * 61,
      state: i === 0 ? '转写中' : '可回看', test: true,
    })),
    devices: {
      window: [{ itemName: '示例游戏窗口（合成测试）', itemValue: 'synthetic-window', itemEnabled: true }],
      monitor: [{ itemName: '示例显示器（合成测试）', itemValue: 'synthetic-display', itemEnabled: true }],
      mic: [{ itemName: '示例麦克风（合成测试）', itemValue: 'synthetic-mic', itemEnabled: true }],
    },
    model: { state: 'missing', downloaded_bytes: 0, total_bytes: 100 },
    capabilities: { cloud_key: true },
    ...overrides,
  };
}

function reviewHTML() {
  const data = {
    id: 'synthetic-review', title: '示例游戏 · 合成回看', created: '2026-09-22T10:30:00',
    desktop: true, test: true, video: '/synthetic.webm',
    segments: Array.from({ length: 48 }, (_, i) => ({ start: i, end: i + 0.95, text: words[i % words.length] })),
  };
  const values = {
    TITLE: data.title, DATA: JSON.stringify(data), CSS: read('ui/review.css'), JS: read('ui/review.js'),
    PLYR_CSS: read('ui/vendor/plyr/plyr.css'), PLYR_JS: read('ui/vendor/plyr/plyr.min.js'),
    PLYR_SVG: read('ui/vendor/plyr/plyr.svg'), LICENSE: 'Synthetic acceptance fixture; bundled Plyr license applies',
  };
  return read('player.html').replace(/%%([A-Z_]+)%%/g, (_, key) => {
    assert.ok(Object.hasOwn(values, key), `Unknown review template placeholder: ${key}`);
    return values[key];
  });
}

const evidence = {
  scope: 'Synthetic browser acceptance only. Actual source UI with a fake native bridge and generated test-pattern video. No OBS, microphone, cloud or user data.',
  source: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
  checks: [], screenshots: [], errors: [],
};
let media = null;
const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  if (url.pathname === '/fixture') { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><title>Synthetic fixture generator</title>'); return; }
  if (url.pathname === '/review') { response.setHeader('Content-Type', 'text/html; charset=utf-8'); response.end(reviewHTML()); return; }
  if (url.pathname === '/synthetic.webm' && media) {
    evidence.mediaRequests ||= []; evidence.mediaRequests.push({ range: request.headers.range || null, bytes: media.length });
    response.setHeader('Content-Type', 'video/webm'); response.setHeader('Accept-Ranges', 'bytes');
    const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range || '');
    if (range) {
      const start = Number(range[1]), end = Math.min(range[2] ? Number(range[2]) : media.length - 1, media.length - 1);
      if (start > end) { response.writeHead(416, { 'Content-Range': `bytes */${media.length}` }); response.end(); return; }
      response.writeHead(206, { 'Content-Range': `bytes ${start}-${end}/${media.length}`, 'Content-Length': end - start + 1 });
      response.end(media.subarray(start, end + 1)); return;
    }
    response.setHeader('Content-Length', media.length); response.end(media); return;
  }
  if (url.pathname.startsWith('/ui/')) {
    const file = path.resolve(root, '.' + decodeURIComponent(url.pathname));
    if (file.startsWith(path.join(root, 'ui') + path.sep) && fs.existsSync(file) && fs.statSync(file).isFile()) {
      const mime = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };
      response.setHeader('Content-Type', mime[path.extname(file)] || 'application/octet-stream'); response.end(fs.readFileSync(file)); return;
    }
  }
  response.writeHead(404); response.end('Synthetic test route not found');
});

async function check(name, task) {
  try { const details = await task(); evidence.checks.push({ name, pass: true, ...(details === undefined ? {} : { details }) }); }
  catch (error) { evidence.checks.push({ name, pass: false, error: error.message }); console.error(`FAIL: ${name}\n${error.stack}`); }
}
async function screen(page, name) {
  await page.screenshot({ path: path.join(output, `${name}.png`), animations: 'disabled' });
  evidence.screenshots.push(`${name}.png`);
}
async function box(page, selector) {
  const result = await page.locator(selector).boundingBox(); assert.ok(result, `${selector} is visible`); return result;
}
const closeEnough = (a, b, label) => assert.ok(Math.abs(a - b) <= 1, `${label}: ${a} versus ${b}`);
async function unchangedBounds(page, selector, action) {
  const before = await box(page, selector); await action(); const after = await box(page, selector);
  for (const key of ['x', 'y', 'width', 'height']) closeEnough(before[key], after[key], `${selector}.${key}`);
}
async function noHorizontalOverflow(page) {
  const result = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
  assert.ok(result.scroll <= result.width + 1, JSON.stringify(result));
}
async function assertInsideViewport(page, selector) {
  const rect = await box(page, selector), viewport = page.viewportSize();
  assert.ok(rect.x >= -1 && rect.y >= -1 && rect.x + rect.width <= viewport.width + 1 && rect.y + rect.height <= viewport.height + 1, `${selector} outside ${JSON.stringify(viewport)}: ${JSON.stringify(rect)}`);
}
async function theme(page, requested) {
  if (await page.locator('html').getAttribute('data-theme') !== requested) await page.locator('#themeButton').click();
  assert.equal(await page.locator('html').getAttribute('data-theme'), requested);
}
async function patchSnapshot(page, patch) {
  await page.evaluate(value => { Object.assign(window.__syntheticFixture.snapshot, value); }, patch);
}
async function calls(page, method) {
  return page.evaluate(name => window.__syntheticFixture.calls.filter(call => call.method === name), method);
}
async function bridge(page, state = snapshot(), requestedTheme = 'light') {
  await page.addInitScript(({ state, imported, requestedTheme }) => {
    localStorage.setItem('recorder-theme', requestedTheme);
    window.__syntheticFixture = { snapshot: state, imported, calls: [], layout: null, polls: 0, refreshSequence: 0, refreshSnapshot: null };
    window.pywebview = { api: new Proxy({}, { get: (_, method) => async (...args) => {
      const fixture = window.__syntheticFixture;
      if (method === 'get_state') { fixture.polls++; return { ok: true, data: JSON.parse(JSON.stringify(fixture.snapshot)) }; }
      fixture.calls.push({ method, args });
      if (method === 'update_action') {
        if (fixture.updateFailure) return {ok:false,error:fixture.updateFailure};
        const u=fixture.snapshot.updates, request=args[0];
        if(request.action==='check')Object.assign(u,{state:'checking',include_prerelease:request.include_prerelease,error:''});
        if(request.action==='download')Object.assign(u,{state:'downloading',downloaded_bytes:0,error:''});
        if(request.action==='cancel'){
          if(u.cancel_pending){if(fixture.confirmUpdateCancel){u.cancel_pending=false;u.error='已取消这次安装，当前版本保留。';fixture.snapshot.closing=false;}}
          else Object.assign(u,{state:u.latest_version?'available':'idle',downloaded_bytes:0,error:''});
        }
        if(request.action==='install')fixture.snapshot.closing=true;
        return {ok:true,data:JSON.parse(JSON.stringify(u))};
      }
      if (method === 'refresh_devices') {
        const id = fixture.refreshSequence++ ? `fixture-refresh-${fixture.refreshSequence}` : 'fixture-refresh';
        if (fixture.refreshSnapshot) Object.assign(fixture.snapshot, JSON.parse(JSON.stringify(fixture.refreshSnapshot)));
        fixture.snapshot.device_refresh = { id, state: 'succeeded' };
        return { ok: true, accepted: true, data: { refresh_id: id } };
      }
      if (method === 'choose_hotword_files') return { ok: true, data: { files: fixture.imported } };
      if (method === 'get_layout') return { ok: true, data: fixture.layout };
      if (method === 'save_layout') { fixture.layout = { ...fixture.layout, [args[0]]: args[1] }; return { ok: true }; }
      if (['ready', 'copy_path', 'open_folder', 'open_document', 'open_bailian_console', 'open_dictionary_site'].includes(method)) return { ok: true };
      throw new Error(`Synthetic harness did not authorize native action: ${String(method)}`);
    } }) };
  }, { state, imported: importedFiles, requestedTheme });
}

async function makeSyntheticVideo(browser, origin) {
  const page = await browser.newPage();
  try {
    await page.goto(origin + '/fixture');
    const bytes = await page.evaluate(async () => {
      const canvas = document.createElement('canvas'); canvas.width = 960; canvas.height = 540; document.body.append(canvas);
      const ctx = canvas.getContext('2d'), stream = canvas.captureStream(0), chunks = [];
      const track = stream.getVideoTracks()[0];
      if (typeof track.requestFrame !== 'function') throw new Error('This browser cannot explicitly capture synthetic canvas frames.');
      const format = ['video/webm;codecs=vp8', 'video/webm'].find(value => MediaRecorder.isTypeSupported(value));
      if (!format) throw new Error('This installed browser cannot encode the synthetic WebM fixture.');
      const recorder = new MediaRecorder(stream, { mimeType: format });
      recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      const stopped = new Promise(resolve => { recorder.onstop = resolve; });
      function draw(frame) {
        ctx.fillStyle = '#252b29'; ctx.fillRect(0, 0, 960, 540);
        for (let x = 0; x < 960; x += 48) { ctx.strokeStyle = '#44504a'; ctx.strokeRect(x, 0, 48, 540); }
        for (let y = 0; y < 540; y += 48) { ctx.strokeStyle = '#44504a'; ctx.strokeRect(0, y, 960, 48); }
        ctx.fillStyle = '#ece7dc'; ctx.font = 'bold 40px sans-serif'; ctx.fillText('SYNTHETIC UI TEST', 64, 220);
        ctx.font = '24px sans-serif'; ctx.fillText('Generated test pattern - no game or microphone capture', 64, 264);
        ctx.fillStyle = '#b64b37'; ctx.fillRect(64, 325, 32 + frame * 25, 8);
      }
      draw(0); const started = new Promise(resolve => { recorder.onstart = resolve; }); recorder.start(); await started;
      for (let frame = 1; frame <= 20; frame++) { draw(frame); track.requestFrame(); await new Promise(resolve => setTimeout(resolve, 100)); }
      recorder.stop(); await stopped; stream.getTracks().forEach(track => track.stop());
      const result = new Uint8Array(await new Blob(chunks, { type: format }).arrayBuffer());
      if (result.length < 1000) throw new Error(`Synthetic MediaRecorder fixture has no usable video frames (${result.length} bytes).`);
      return Array.from(result);
    });
    media = Buffer.from(bytes);
  } finally { await page.close(); }
}

async function vocabularyChecks(context, origin) {
  const page=await context.newPage(); await bridge(page);
  await page.goto(origin+'/ui/index.html'); await page.locator('#settingsButton').waitFor();
  await check('new presets visibly select bundled UIUX words; preview is read-only and removable',async()=>{
    await page.locator('#newPresetButton').click();await page.locator('#wizardNext').click();
    await page.locator('#game').fill('词库验收 · 合成预设');
    await page.locator('#target').selectOption('synthetic-window');await page.locator('#mic').selectOption('synthetic-mic');
    await page.locator('#wizardNext').click();await page.locator('#providerQwen').click();
    assert.equal(await page.locator('#vocabularySummary').innerText(),'UI/UX 已选');
    await page.locator('#advancedSettings summary').first().click();
    assert.equal(await page.locator('#hotwordFiles li').count(),1);
    await page.locator('[data-view-vocabulary]').click();
    assert.equal(await page.locator('.vocabulary-words li').count(),bundledWords.length);
    assert.match(await page.locator('#actionBody').innerText(),/心智模型/);
    assert.equal((await calls(page,'save_preset')).length,0);
    await screen(page,'vocabulary-preview-light-1240x900');
    await page.getByRole('button',{name:'关闭',exact:true}).click();
    assert.equal(await page.locator('#wizard').isVisible(),true);
    await page.locator('[data-remove-vocabulary]').click();
    assert.equal(await page.locator('#vocabularySummary').innerText(),'未选词库');
    await page.locator('#wizardCancel').click();
  });
  await check('compact dark vocabulary preview scrolls independently and returns to the draft',async()=>{
    await page.setViewportSize({width:820,height:620});await theme(page,'dark');
    await page.locator('#newPresetButton').click();await page.locator('#wizardNext').click();
    await page.locator('#game').fill('第二个合成预设');
    await page.locator('#target').selectOption('synthetic-window');await page.locator('#mic').selectOption('synthetic-mic');
    await page.locator('#wizardNext').click();await page.locator('#providerQwen').click();
    await page.locator('#advancedSettings summary').first().click();
    await page.locator('[data-view-vocabulary]').click();
    await page.locator('#actionBody').evaluate(node=>node.scrollTop=node.scrollHeight);
    assert.ok(await page.locator('#actionBody').evaluate(node=>node.scrollTop>0));
    await assertInsideViewport(page,'#actionDialog');await noHorizontalOverflow(page);
    await screen(page,'vocabulary-preview-dark-820x620');
    await page.getByRole('button',{name:'关闭',exact:true}).click();
    await page.locator('#wizardCancel').click();
    assert.equal((await calls(page,'save_preset')).length,0);
  });
  await page.close();
}

async function homeChecks(context, origin) {
  const page = await context.newPage(); await bridge(page);
  await page.goto(origin + '/ui/index.html');
  await page.locator('#sessionList .session-row').first().waitFor();
  await check('home ready while a synthetic background transcription is running', async () => {
    assert.equal(await page.locator('#recordButton').isEnabled(), true);
    assert.match(await page.locator('#homeStatus').innerText(), /准备就绪/);
    assert.equal(await page.locator('#blockers').isVisible(), false);
    assert.match(await page.locator('#backgroundSummary').innerText(), /整理中/);
    assert.equal((await calls(page, 'start_recording')).length, 0);
  });
  await check('equal home headings and aligned 48 px capture controls', async () => {
    const headings = await page.locator('#homeTitle,.session-heading h2').evaluateAll(nodes => nodes.map(node => ({ size: getComputedStyle(node).fontSize, weight: getComputedStyle(node).fontWeight })));
    assert.equal(headings.length, 2); assert.deepEqual(headings[0], headings[1]);
    const rects = await Promise.all(['#presetSelect', '#settingsButton', '#recordButton'].map(selector => box(page, selector)));
    rects.forEach(rect => { closeEnough(rect.height, 48, 'capture control height'); closeEnough(rect.y + rect.height / 2, rects[0].y + rects[0].height / 2, 'capture control alignment'); });
    await noHorizontalOverflow(page); return { headings, rects };
  });
  await check('home is only the product window, with an independently scrolling session list', async () => {
    assert.equal(await page.getByText('原话选中', { exact: true }).count(), 0);
    assert.equal(await page.getByText('窗口未打开', { exact: true }).count(), 0);
    await unchangedBounds(page, '#capturePanel', async () => {
      const scroll = await page.locator('#sessionList').evaluate(node => { node.scrollTop = 300; return node.scrollTop; });
      assert.ok(scroll > 0, 'session list must actually scroll');
    });
    await page.locator('#sessionList').evaluate(node => { node.scrollTop = 0; });
    await screen(page, 'home-light-1240x900');
    await theme(page, 'dark'); await screen(page, 'home-dark-1240x900'); await theme(page, 'light');
  });
  await check('unavailable reasons replace ready text in the same above-button slot', async () => {
    const readyButton = await box(page, '#recordButton');
    try { for (const reason of ['未找到游戏窗口，请先打开游戏。', '云端密钥缺失，请重新配置。']) {
      await patchSnapshot(page, { readiness: { ready: false, checking: false, errors: [{ message: reason, step: 1 }] } });
      await page.waitForFunction(text => document.querySelector('#blockers').textContent === text, reason);
      assert.equal(await page.locator('#recordButton').isEnabled(), false);
      assert.equal(await page.locator('#homeStatus').isVisible(), false);
      assert.equal(await page.locator('#blockers').isVisible(), true);
      assert.equal(await page.locator('#statusSlot #blockers').count(), 1);
      assert.equal(await page.locator('#statusSlot #homeStatus').count(), 1);
      const reasonBox = await box(page, '#blockers'), button = await box(page, '#recordButton');
      assert.ok(reasonBox.y + reasonBox.height <= button.y + 1, 'disabled reason belongs above the CTA');
      closeEnough(button.y, readyButton.y, 'CTA remains stationary between ready and single reason');
    }
    await screen(page, 'home-unavailable-1240x900');
    } finally {
      await patchSnapshot(page, { readiness: snapshot().readiness });
      await page.waitForFunction(() => !document.querySelector('#recordButton').disabled);
    }
  });
  await check('home recovery duplicates are absent and the full address hot area ends at the gear', async () => {
    assert.equal(await page.locator('#recoveryActions,#recheckButton,#fixSettingsButton').count(), 0);
    const address = await box(page, '#openVault'), gear = await box(page, '#settingsButton');
    closeEnough(address.x + address.width, gear.x + gear.width, 'address right edge equals gear');
    const background = await page.locator('#openVault').evaluate(node => getComputedStyle(node).backgroundColor);
    assert.notEqual(background, 'rgba(0, 0, 0, 0)'); assert.notEqual(background, 'transparent');
    await page.locator('#openVault').click({ position: { x: address.width - 8, y: address.height / 2 } });
    assert.equal((await calls(page, 'open_folder')).length, 1, 'right edge of address is an active folder button');
  });
  for (const viewport of [{ width: 1240, height: 900 }, { width: 820, height: 620 }]) {
    for (const requestedTheme of ['light', 'dark']) {
      await check(`stable home geometry across wrapped error and checking states (${requestedTheme} ${viewport.width})`, async () => {
        await page.setViewportSize(viewport); await theme(page, requestedTheme);
        const selectors = ['#recordButton', '#presetSelect', '#settingsButton', '#openVault', '.session-section'];
        const baseline = Object.fromEntries(await Promise.all(selectors.map(async selector => [selector, await box(page, selector)])));
        const states = [
          { name: 'ready', readiness: snapshot().readiness },
          { name: 'one-line', readiness: { ready: false, checking: false, errors: [{ message: '麦克风未连接。' }] } },
          { name: 'two-lines', readiness: { ready: false, checking: false, errors: [{ message: '已选云端转写，但尚未保存本机 API Key。' }] } },
          { name: 'many-lines', readiness: { ready: false, checking: false, errors: ['设置的游戏窗口尚未打开。', '所选麦克风未连接，请检查连接。', '尚未保存本机 API Key。', '保存位置当前不可写，请检查目录。', '这些内容全部来自合成测试。'].map(message => ({ message })) } },
          { name: 'checking', readiness: { ready: false, checking: true, errors: [] } },
          { name: 'ready-again', readiness: snapshot().readiness },
        ];
        const measured = [];
        try {
          for (const state of states) {
            await patchSnapshot(page, { readiness: state.readiness });
            await page.waitForFunction(state => {
              const expected = state.readiness.errors.map(item => item.message).join('\n');
              return document.querySelector('#blockers').textContent === expected &&
                document.querySelector('#recordButton').disabled === !state.readiness.ready &&
                (!state.readiness.checking || document.querySelector('#homeStatus').textContent === '正在检查录制条件');
            }, state);
            const current = Object.fromEntries(await Promise.all(selectors.map(async selector => [selector, await box(page, selector)])));
            for (const selector of selectors) for (const key of ['x', 'y', 'width', 'height']) closeEnough(current[selector][key], baseline[selector][key], `${state.name} ${selector}.${key}`);
            if (state.name === 'many-lines') {
              assert.equal(await page.locator('#statusSlot').getAttribute('tabindex'), '0', 'overflow details are keyboard reachable');
              const scroll = await page.locator('#statusSlot').evaluate(node => { node.scrollTop = node.scrollHeight; return { top: node.scrollTop, full: node.scrollHeight, visible: node.clientHeight }; });
              assert.ok(scroll.full > scroll.visible && scroll.top > 0, 'all long errors remain available in internal scrolling');
              await unchangedBounds(page, '#recordButton', async () => { await page.locator('#statusSlot').evaluate(node => { node.scrollTop = 0; }); });
              await screen(page, `home-errors-${requestedTheme}-${viewport.width}x${viewport.height}`);
            }
            measured.push({ state: state.name, bounds: current });
          }
          return measured;
        } finally {
          await patchSnapshot(page, { readiness: snapshot().readiness });
          await page.waitForFunction(() => !document.querySelector('#recordButton').disabled);
        }
      });
    }
  }
  await page.setViewportSize({ width: 1240, height: 900 }); await theme(page, 'light');
  await check('compact home wraps complete long storage paths', async () => {
    await page.setViewportSize({ width: 820, height: 620 });
    const longPath = 'D:\\synthetic-only\\' + '很长的示例项目名称和归档位置\\'.repeat(8) + 'think-aloud-database';
    await patchSnapshot(page, { config: { ...snapshot().config, vault: longPath } });
    await page.waitForFunction(value => document.querySelector('#savedLocation').textContent.endsWith(value), longPath);
    const text = await page.locator('#savedLocation').evaluate(node => ({ text: node.textContent, height: node.getBoundingClientRect().height, line: parseFloat(getComputedStyle(node).lineHeight), scroll: node.scrollWidth, width: node.clientWidth, overflow: getComputedStyle(node).textOverflow }));
    assert.equal(text.text, '保存到 ' + longPath); assert.ok(text.height > text.line * 1.5, 'long path wraps to multiple lines');
    assert.ok(text.scroll <= text.width + 1, 'wrapped path must not overflow'); assert.notEqual(text.overflow, 'ellipsis');
    await noHorizontalOverflow(page); await assertInsideViewport(page, '#recordButton');
    await screen(page, 'home-long-path-820x620');
    await patchSnapshot(page, { config: snapshot().config });
    await page.waitForFunction(() => document.querySelector('#savedLocation').textContent.endsWith('synthetic-only\\think-aloud-database'));
    await screen(page, 'home-light-820x620'); await theme(page, 'dark'); await screen(page, 'home-dark-820x620'); await theme(page, 'light');
    await page.setViewportSize({ width: 1240, height: 900 });
  });
  await check('new preset has four steps; detected devices require no manual refresh', async () => {
    await page.locator('#newPresetButton').click();
    assert.equal(await page.locator('#wizardTitle').innerText(), '记录方法');
    assert.equal(await page.locator('.wizard-steps .step:visible').count(), 4);
    assert.equal(await page.locator('.method-card').count(), 4);
    const flow = page.locator('#methodContent .method-flow');
    assert.match(await flow.innerText(), /开始录制[\s\S]*体验 \+ 说出想法[\s\S]*回看 \+ 分析问题/);
    assert.ok((await box(page, '#methodContent .method-flow')).y < (await box(page, '#methodContent .method-lead')).y, 'core method precedes all examples and supporting copy');
    await screen(page, 'wizard-method-light-1240x900');
    await page.locator('#wizardNext').click();
    assert.equal(await page.locator('#wizardTitle').innerText(), '游戏与设备');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'game', 'name field receives focus on entering the device step');
    assert.equal(await page.locator('#target option[value="synthetic-window"]').count(), 1);
    assert.equal(await page.locator('#mic option[value="synthetic-mic"]').count(), 1);
    assert.equal((await calls(page, 'refresh_devices')).length, 0);
    await page.locator('#game').fill('未保存的合成预设');
    const polls = await page.evaluate(() => window.__syntheticFixture.polls);
    await page.waitForFunction(before => window.__syntheticFixture.polls > before, polls);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'game', 'polling preserves the name caret');
    await page.locator('#source').focus();
    const laterPolls = await page.evaluate(() => window.__syntheticFixture.polls);
    await page.waitForFunction(before => window.__syntheticFixture.polls > before, laterPolls);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'source', 'polling does not steal focus back to the name field');
    await page.locator('#target').selectOption('synthetic-window'); await page.locator('#mic').selectOption('synthetic-mic');
    await screen(page, 'wizard-devices-light-1240x900');
    await page.locator('#wizardNext').click(); assert.equal(await page.locator('#wizardTitle').innerText(), '录制与转写');
    await page.locator('#wizardNext').click(); assert.equal(await page.locator('#wizardTitle').innerText(), '保存位置');
    assert.match(await page.locator('#wizardNext').innerText(), /保存预设/);
    await screen(page, 'wizard-location-light-1240x900');
    await page.locator('#wizardCancel').click();
    assert.equal((await calls(page, 'save_preset')).length, 0);
    assert.equal(await page.locator('#presetSelect option:checked').innerText(), snapshot().config.game);
  });
  await check('edit skips guide; cancellation preserves settings and clears synthetic secret input', async () => {
    await page.locator('#settingsButton').click();
    assert.equal(await page.locator('#wizardTitle').innerText(), '游戏与设备');
    assert.equal(await page.locator('.wizard-steps .step:visible').count(), 3);
    assert.equal(await page.locator('#game').inputValue(), snapshot().config.game);
    await page.locator('#game').fill('不应持久化的修改');
    await page.locator('#wizardNext').click();
    assert.equal(await page.locator('#cloudKey').inputValue(), '');
    assert.match(await page.locator('#cloudStatus').innerText(), /密钥已保存/);
    assert.equal(await page.locator('#cloudKey').getAttribute('type'), 'password');
    await page.locator('#cloudKey').fill('synthetic-not-a-real-key');
    await page.locator('#wizardCancel').click();
    await page.locator('#settingsButton').click();
    assert.equal(await page.locator('#game').inputValue(), snapshot().config.game);
    await page.locator('#wizardNext').click();
    assert.equal(await page.locator('#cloudKey').inputValue(), '');
    assert.equal((await calls(page, 'save_cloud_key')).length, 0);
    assert.equal((await calls(page, 'save_preset')).length, 0);
  });
  await check('Bailian console uses a native link action; vocabulary accepts multiple files', async () => {
    await page.getByRole('link', { name: /百炼控制台/ }).click();
    assert.equal((await calls(page, 'open_bailian_console')).length, 1);
    await page.locator('#advancedSettings summary').first().click();
    await page.locator('#chooseHotwordFiles').click();
    await page.waitForFunction(() => document.querySelectorAll('#hotwordFiles li').length === 3);
    assert.match(await page.locator('#vocabularyCount').innerText(), /3 份词库.*4 个词/);
    await page.locator('#chooseHotwordFiles').click();
    assert.equal(await page.locator('#hotwordFiles li').count(), 3, 'reimport does not duplicate selected files');
    assert.equal((await calls(page, 'choose_hotword_files')).length, 2);
    await page.locator('#dictionaryDownload').click(); assert.equal((await calls(page, 'open_dictionary_site')).length, 1);
    await screen(page, 'wizard-transcription-light-1240x900');
    await page.locator('[data-remove-vocabulary="synthetic-game"]').click();
    assert.equal(await page.locator('#hotwordFiles li').count(), 2);
  });
  await check('transcription uses exactly two accessible tabs with click and keyboard selection', async () => {
    assert.equal(await page.locator('#transcription_provider').count(), 0);
    assert.equal(await page.getByText('仅保存录制，稍后整理', { exact: true }).count(), 0);
    assert.equal(await page.locator('#providerTabs [role=tab]').count(), 2);
    assert.equal(await page.locator('#providerQwen').getAttribute('aria-selected'), 'true');
    await page.locator('#providerLocal').click();
    assert.equal(await page.locator('#localControls').isVisible(), true); assert.equal(await page.locator('#cloudControls').isVisible(), false);
    assert.equal(await page.locator('#providerLocal').getAttribute('aria-selected'), 'true');
    assert.equal(await page.locator('#providerLocal').getAttribute('tabindex'), '0');
    assert.equal(await page.locator('#providerQwen').getAttribute('tabindex'), '-1');
    await page.locator('#providerLocal').press('ArrowRight');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'providerQwen');
    assert.equal(await page.locator('#cloudControls').isVisible(), true); assert.equal(await page.locator('#localControls').isVisible(), false);
    await page.locator('#providerQwen').press('ArrowLeft');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'providerLocal');
    assert.equal(await page.locator('#localControls').isVisible(), true);
    await page.locator('#providerLocal').press('End');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'providerQwen');
    await page.locator('#providerQwen').press('Home');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'providerLocal');
    const complete = await page.locator('.wizard-steps .step.completed span').first().evaluate(node => ({ position: getComputedStyle(node, '::after').position, font: getComputedStyle(node).fontSize }));
    assert.equal(complete.position, 'absolute'); assert.equal(complete.font, '0px');
    await screen(page, 'wizard-local-tab-light-1240x900');
    await page.locator('#providerQwen').click();
    assert.equal((await calls(page, 'save_preset')).length, 0, 'changing tabs only changes the draft');
  });
  await check('wizard body scrolls independently; footer stays visible at minimum size in both themes', async () => {
    await page.setViewportSize({ width: 820, height: 620 });
    await unchangedBounds(page, '.wizard-footer', async () => {
      const metrics = await page.locator('#wizardBody').evaluate(node => { node.scrollTop = node.scrollHeight; return { scroll: node.scrollTop, height: node.clientHeight }; });
      assert.ok(metrics.scroll > 0 && metrics.height > 60, 'wizard body must scroll');
    });
    await assertInsideViewport(page, '.wizard-footer'); await assertInsideViewport(page, '#wizardNext');
    await noHorizontalOverflow(page); await screen(page, 'wizard-transcription-light-820x620');
    await page.locator('#wizardCancel').click(); await theme(page, 'dark');
    await page.locator('#settingsButton').click(); await screen(page, 'wizard-devices-dark-820x620');
    await page.locator('#wizardNext').click(); await page.locator('#advancedSettings summary').first().click();
    await page.locator('#wizardBody').evaluate(node => { node.scrollTop = node.scrollHeight; });
    await screen(page, 'wizard-transcription-dark-820x620');
    await page.setViewportSize({ width: 1240, height: 900 });
    await page.locator('#wizardBody').evaluate(node => { node.scrollTop = 0; });
    await screen(page, 'wizard-transcription-dark-1240x900');
    await page.locator('#wizardBack').click(); await screen(page, 'wizard-devices-dark-1240x900');
    await page.locator('#wizardCancel').click();
  });
  await page.close();
}

async function firstUseChecks(context, origin) {
  const page = await context.newPage();
  await bridge(page, snapshot({ presets: [], active_preset_id: null, readiness: { ready: false, checking: false, errors: [{ message: '请先完成设置' }] } }));
  await page.goto(origin + '/ui/index.html'); await page.locator('#wizard[open]').waitFor();
  await check('first launch automatically opens the same four-step creation wizard', async () => {
    assert.equal(await page.locator('#wizardTitle').innerText(), '记录方法');
    assert.equal(await page.locator('.wizard-steps .step:visible').count(), 4);
    await page.locator('#wizardCancel').click(); assert.equal(await page.locator('#recordButton').isEnabled(), false);
    assert.equal((await calls(page, 'save_preset')).length, 0);
  });
  await page.close();
}

async function deviceSetupChecks(context, origin) {
  const detected = {
    devices: {
      window: snapshot().devices.window,
      monitor: [
        { itemName: '副显示器（合成测试）', itemValue: 'synthetic-secondary-display', itemEnabled: true },
        { itemName: '主显示器（合成测试，不在列表首位）', itemValue: 'synthetic-primary-display', itemEnabled: true },
      ],
      mic: [
        { itemName: '指定麦克风（合成测试）', itemValue: 'synthetic-physical-mic', itemEnabled: true },
        { itemName: '默认麦克风（合成测试）', itemValue: 'default', itemEnabled: true },
      ],
    },
    device_defaults: { monitor: 'synthetic-primary-display', mic: 'default' },
  };
  for (const scenario of [{ theme: 'light', width: 1240, height: 900 }, { theme: 'dark', width: 820, height: 620 }]) {
    const page = await context.newPage(); await page.setViewportSize({ width: scenario.width, height: scenario.height });
    await bridge(page, snapshot({ devices: { window: [], monitor: [], mic: [] }, device_defaults: {} }), scenario.theme);
    await page.goto(origin + '/ui/index.html'); await page.locator('#newPresetButton:not([disabled])').waitFor();
    await check(`empty devices offer OBS setup, use explicit defaults, and preserve later manual choices (${scenario.theme} ${scenario.width})`, async () => {
      const original = await page.evaluate(() => JSON.stringify(window.__syntheticFixture.snapshot.config));
      await page.locator('#newPresetButton').click(); await page.locator('#wizardNext').click();
      assert.equal(await page.locator('#refreshDevices').innerText(), '设置 OBS');
      assert.equal(await page.evaluate(() => document.activeElement.id), 'game');
      await page.locator('#game').fill('合成 OBS 初始化验证');
      await page.evaluate(value => { window.__syntheticFixture.refreshSnapshot = value; }, detected);
      await page.locator('#refreshDevices').click();
      await page.waitForFunction(() => document.querySelector('#source').value === '整个显示器' && document.querySelector('#target').value === 'synthetic-primary-display' && document.querySelector('#mic').value === 'default');
      assert.equal(await page.locator('#refreshDevices').innerText(), '刷新设备');
      assert.equal(await page.locator('#target option').first().getAttribute('value'), 'synthetic-secondary-display', 'default selection must not assume the first monitor is primary');
      assert.equal(await page.locator('#wizardError').isVisible(), false);
      assert.equal(await page.evaluate(() => JSON.stringify(window.__syntheticFixture.snapshot.config)), original, 'setup initializes only the draft');
      assert.equal((await calls(page, 'save_preset')).length, 0);
      assert.equal((await calls(page, 'refresh_devices')).length, 1);
      await screen(page, `wizard-obs-defaults-${scenario.theme}-${scenario.width}x${scenario.height}`);
      await page.locator('#target').selectOption('synthetic-secondary-display');
      await page.locator('#mic').selectOption('synthetic-physical-mic');
      await page.locator('#refreshDevices').click();
      await page.waitForFunction(() => window.__syntheticFixture.calls.filter(call => call.method === 'refresh_devices').length === 2 && !document.querySelector('#refreshDevices').disabled);
      assert.equal(await page.locator('#target').inputValue(), 'synthetic-secondary-display');
      assert.equal(await page.locator('#mic').inputValue(), 'synthetic-physical-mic');
      assert.equal(await page.evaluate(() => JSON.stringify(window.__syntheticFixture.snapshot.config)), original);
      await page.locator('#wizardCancel').click();
      assert.equal((await calls(page, 'save_preset')).length, 0);
    });
    await page.close();
  }
}

async function reviewChecks(context, origin) {
  const page = await context.newPage(); await bridge(page);
  await page.goto(origin + '/review'); await page.locator('#lines .line').first().waitFor();
  try { await page.waitForFunction(() => document.querySelector('#video').readyState >= 1); }
  catch (error) {
    const diagnostic = await page.locator('#video').evaluate(node => ({ readyState: node.readyState, networkState: node.networkState, currentSrc: node.currentSrc, src: node.getAttribute('src'), error: node.error && { code: node.error.code, message: node.error.message }, vp8: node.canPlayType('video/webm;codecs=vp8'), status: document.querySelector('#status').textContent }));
    evidence.reviewMediaDiagnostic = { ...diagnostic, fixtureBytes: media?.length, fixtureHeader: media?.subarray(0, 24).toString('hex') };
    await screen(page, 'review-media-failure');
    throw new Error(`${error.message}\nSynthetic media diagnostic: ${JSON.stringify(evidence.reviewMediaDiagnostic)}`);
  }
  // Media metadata is ready before the next rendered source-fit pass. Measure
  // the settled layout, then prove user scrolling cannot change that geometry.
  await page.evaluate(async()=>{for(let i=0;i<6;i++)await new Promise(requestAnimationFrame);});
  await check('synthetic video genuinely loads and review reports readiness', async () => {
    const readiness = await calls(page, 'ready'); assert.ok(readiness.some(call => call.args[0] === null));
    assert.equal(await page.locator('#testLabel').isVisible(), true);
    assert.equal(await page.locator('#status').innerText(), '');
    return { video: 'Browser-generated test pattern (not a captured game)', ready: readiness };
  });
  await check('transcript scroll preserves video geometry and pauses follow', async () => {
    await unchangedBounds(page, '#videoPane', async () => {
      await page.locator('#lines').hover(); await page.mouse.wheel(0, 550);
      await page.waitForFunction(() => document.querySelector('#lines').scrollTop > 0);
    });
    assert.equal(await page.locator('#follow').innerText(), '恢复跟随');
    assert.equal(await page.locator('#follow').getAttribute('aria-pressed'), 'false');
    await page.locator('#follow').click(); assert.equal(await page.locator('#follow').getAttribute('aria-pressed'), 'true');
  });
  await check('playing a quote marks its original words with a timestamp divider', async () => {
    await page.locator('#lines').evaluate(node => { node.scrollTop = 0; });
    await page.locator('#lines .line').first().click();
    await page.waitForFunction(() => document.querySelector('#lines .line.active'));
    await page.evaluate(() => { window.reviewPlayer.pause(); });
    const selected = page.locator('#lines .line.active').first();
    assert.equal(await selected.getAttribute('aria-current'), 'true');
    const detail = await selected.evaluate(node => {
      const time = node.querySelector('time'), text = node.querySelector('.segment-text');
      const css = getComputedStyle(time), next = getComputedStyle(text), row = getComputedStyle(node);
      return { time: { ...time.getBoundingClientRect().toJSON() }, text: { ...text.getBoundingClientRect().toJSON() }, divider: css.borderRightWidth, textDivider: next.borderLeftWidth, dividerColor: next.borderLeftColor, rowBorder: row.borderLeftWidth };
    });
    assert.ok(parseFloat(detail.divider) > 0 || parseFloat(detail.textDivider) > 0, 'selected row needs a separator between timestamp and original words');
    assert.notEqual(detail.dividerColor, 'rgba(0, 0, 0, 0)', 'selected separator is visible');
    assert.ok(detail.text.x > detail.time.x, 'timestamp precedes quote in the wide layout');
    await screen(page, 'review-light-1240x900');
    return detail;
  });
  await check('review search filters original words; split copy keeps its geometry and keyboard behavior', async () => {
    await page.locator('#search').fill('返回'); assert.equal(await page.locator('#lines .line:visible').count(), 12);
    await page.locator('#search').press('ArrowLeft'); assert.equal(await page.locator('#search').inputValue(), '返回');
    await page.locator('#search').fill('');
    await unchangedBounds(page, '#copySplit', async () => { await page.locator('#copyPath').click(); await page.waitForFunction(() => document.querySelector('#copyLabel').textContent === 'copied!'); });
    assert.equal((await calls(page, 'copy_path')).at(-1).args[0], 'vault');
    await page.locator('#fileActionsToggle').focus(); await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('#fileActionsToggle').getAttribute('aria-expanded'), 'true');
    await assertInsideViewport(page, '#fileActions');
    await page.locator('#fileActions [data-copy="transcript"]').click();
    assert.equal((await calls(page, 'copy_path')).at(-1).args[0], 'transcript');
    await page.locator('#fileActionsToggle').click(); await page.keyboard.press('Escape');
    assert.equal(await page.locator('#fileActionsToggle').getAttribute('aria-expanded'), 'false');
  });
  await check('review divider works by keyboard without scrolling the document', async () => {
    const initial = Number(await page.locator('#reviewSplitter').getAttribute('aria-valuenow'));
    await page.locator('#reviewSplitter').focus(); await page.keyboard.press('ArrowLeft');
    const after = Number(await page.locator('#reviewSplitter').getAttribute('aria-valuenow'));
    assert.ok(after < initial); assert.ok((await calls(page, 'save_layout')).length > 0);
    await page.keyboard.press('Enter'); await noHorizontalOverflow(page);
    assert.equal(await page.evaluate(() => document.scrollingElement.scrollTop), 0);
    await theme(page, 'dark'); await screen(page, 'review-dark-1240x900');
  });
  await check('compact stacked review keeps video fixed, transcript scrollable and copy menu in bounds', async () => {
    await page.setViewportSize({ width: 560, height: 540 });
    await page.waitForFunction(() => document.querySelector('#reviewSplitter').getAttribute('aria-orientation') === 'horizontal');
    await unchangedBounds(page, '#videoPane', async () => {
      await page.locator('#lines').hover(); await page.mouse.wheel(0, 450);
      await page.waitForFunction(() => document.querySelector('#lines').scrollTop > 0);
    });
    const pane = await box(page, '#videoPane'), transcript = await box(page, '#transcriptPane');
    assert.ok(transcript.y >= pane.y + pane.height, 'compact panes stack');
    assert.ok((await box(page, '#lines')).height >= 32, 'transcript retains usable space');
    await noHorizontalOverflow(page); await assertInsideViewport(page, '#copySplit');
    await page.locator('#lines').evaluate(node => { node.scrollTop = 0; });
    await screen(page, 'review-dark-560x540');
    await page.locator('#fileActionsToggle').click(); await assertInsideViewport(page, '#fileActions');
    await screen(page, 'review-copy-menu-dark-560x540'); await page.keyboard.press('Escape');
    await theme(page, 'light'); await screen(page, 'review-light-560x540');
  });
  await page.close();
}

async function windowSelectionChecks(context, origin) {
  const page = await context.newPage(), state = snapshot();
  const saved = 'Synthetic:OldClass:game.exe', live = 'Synthetic:NewClass:game.exe';
  const other = 'Other:OtherClass:other.exe';
  state.config.window = saved;
  state.devices.window = [
    {itemName:'示例游戏（当前窗口）',itemValue:live,itemEnabled:true},
    {itemName:'另一个游戏窗口',itemValue:other,itemEnabled:true},
  ];
  state.readiness.window_selection = {requested:saved,resolved:live,status:'matched',matched_by:'exe_title'};
  await bridge(page, state); await page.goto(origin + '/ui/index.html');
  await page.locator('#settingsButton').click();
  await check('saved game resolves visibly to its current identity without an unavailable placeholder', async () => {
    assert.equal(await page.locator('#target').inputValue(), live);
    assert.match(await page.locator('#target option:checked').innerText(), /已匹配当前窗口/);
    assert.doesNotMatch(await page.locator('#target').innerText(), /当前未找到/);
    await screen(page, 'saved-game-unique-match');
  });
  await check('polling never replaces a manually chosen different game', async () => {
    await page.locator('#target').selectOption(other);
    await page.locator('#game').click(); await page.evaluate(() => poll());
    assert.equal(await page.locator('#target').inputValue(), other);
  });
  await check('cancel preserves the original preset and reopens with the current match', async () => {
    await page.locator('#wizardCancel').click(); await page.locator('#settingsButton').click();
    assert.equal(await page.locator('#target').inputValue(), live);
    assert.equal(await page.evaluate(() => window.__syntheticFixture.snapshot.config.window), saved);
    assert.equal((await calls(page, 'save_preset')).length, 0);
  });
  await check('ambiguous matches retain the saved target and never select a candidate automatically', async () => {
    await patchSnapshot(page, {readiness:{ready:false,checking:false,errors:[{code:'WINDOW_AMBIGUOUS',step:1,message:'检测到多个匹配的游戏窗口，请重新选择。'}],
      window_selection:{requested:saved,resolved:null,status:'ambiguous'}}});
    await page.locator('#game').click(); await page.evaluate(() => poll());
    assert.equal(await page.locator('#target').inputValue(), saved);
    assert.match(await page.locator('#target option:checked').innerText(), /当前未找到/);
    await page.locator('#wizardCancel').click();
    assert.equal(await page.locator('#recordButton').isDisabled(), true);
    assert.match(await page.locator('#blockers').innerText(), /多个匹配/);
  });
  await page.close();
}

async function main() {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true, channel: process.env.TAR_UI_CHANNEL || 'msedge' });
  try {
    if(!process.env.TAR_UI_ONLY||process.env.TAR_UI_ONLY==='review')await makeSyntheticVideo(browser, origin);
    const context = await browser.newContext({ viewport: { width: 1240, height: 900 }, deviceScaleFactor: 1 });
    context.setDefaultTimeout(6000); context.setDefaultNavigationTimeout(10000);
    await context.route('**/*', route => {
      if (route.request().url().startsWith(origin + '/')) return route.continue();
      evidence.errors.push(`Blocked non-fixture request: ${route.request().url()}`); return route.abort();
    });
    context.on('page', page => page.on('pageerror', error => evidence.errors.push(error.message)));
    for (const [name, task] of [['recorder scenarios', homeChecks], ['first launch scenario', firstUseChecks], ['device setup scenarios', deviceSetupChecks], ['window scenarios', windowSelectionChecks], ['vocabulary scenarios', vocabularyChecks], ['update scenarios', updateChecks], ['review scenarios', reviewChecks]]) {
      if(process.env.TAR_UI_ONLY&&!name.startsWith(process.env.TAR_UI_ONLY+' '))continue;
      (evidence.scenarios||=[]).push(name);
      await check(name, () => task(context, origin));
    }
    await check('no browser exceptions or unexpected network requests', () => assert.deepEqual(evidence.errors, []));
    await context.close();
  } finally { await browser.close(); server.close(); }
  evidence.passed = evidence.checks.every(result => result.pass);
  fs.writeFileSync(path.join(output, 'acceptance.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({ passed: evidence.passed, checks: evidence.checks.length, failures: evidence.checks.filter(result => !result.pass), screenshots: evidence.screenshots.length, output }, null, 2));
  if (!evidence.passed) process.exitCode = 1;
}
main().catch(error => { console.error(error.stack); server.close(); process.exitCode = 1; });

async function updateChecks(context,origin){
  const page=await context.newPage();await page.setViewportSize({width:1060,height:780});await bridge(page);
  await page.goto(origin+'/ui/index.html');await page.waitForFunction(()=>!document.querySelector('#recordButton').disabled);
  const base={current_version:'0.6.0-preview.3',state:'idle',latest_version:null,include_prerelease:false,can_install:false,install_blockers:[],review_count:0};
  const updates=async value=>{await patchSnapshot(page,{updates:{...base,...value},closing:false});await page.evaluate(()=>poll());};
  await check('updates absent on older bridge: safe dialog, no automatic requests and stable main CTA',async()=>{
    const initial=await box(page,'#recordButton');await page.locator('#versionButton').click();
    assert.equal(await page.locator('#updateCheck').isDisabled(),true);assert.equal(await page.locator('#updateCurrent').textContent(),'尚未获取');
    assert.equal((await calls(page,'update_action')).length,0);await page.keyboard.press('Escape');
    assert.equal(await page.locator('#versionButton').evaluate(n=>n===document.activeElement),true);
    const after=await box(page,'#recordButton');assert.deepEqual(after,initial);
    await updates({});assert.equal(await page.locator('#versionButton').textContent(),'v0.6.0-preview.3');
    assert.deepEqual(await box(page,'#recordButton'),initial);await screen(page,'updates-home-1060');
  });
  await check('stable is default and opening dialog does not check; explicit check and cancel use bridge',async()=>{
    await page.locator('#versionButton').click();assert.equal(await page.locator('#updateChannel').inputValue(),'stable');
    assert.equal((await calls(page,'update_action')).length,0);await screen(page,'updates-idle-light');
    await page.locator('#updateCheck').click();await page.waitForFunction(()=>document.querySelector('#updateStatus').textContent==='正在检查更新');
    assert.deepEqual((await calls(page,'update_action')).at(-1).args,[{action:'check',include_prerelease:false}]);
    assert.equal(await page.locator('#updateChannel').isDisabled(),true);await page.locator('#updateCancel').click();
    await page.waitForFunction(()=>document.querySelector('#updateStatus').textContent==='尚未检查更新');
    assert.equal((await calls(page,'update_action')).at(-1).args[0].action,'cancel');
  });
  await check('latest, no release and release notes states are concrete; notes cannot inject HTML',async()=>{
    await updates({state:'current',latest_version:'0.6.0-preview.3'});assert.equal(await page.locator('#updateStatus').textContent(),'已是当前频道的最新版本');
    assert.equal(await page.locator('#updateDownload').isVisible(),false);
    await updates({state:'no_release'});assert.equal(await page.locator('#updateLatest').textContent(),'暂无发布');
    await updates({state:'available',latest_version:'0.7.0',notes:'改进时间轴拖动与操作记录的可读性。\n修复回看窗口关闭时的状态同步。\n<script>window.__badRelease=true</script>',total_bytes:251658240,release_url:'https://github.com/Elkhiffa/think-aloud-recorder/releases/tag/v0.7.0'});
    assert.equal(await page.locator('#updateLatest').textContent(),'v0.7.0');assert.ok((await page.locator('#updateSize').textContent()).includes('240.0 MiB'));
    assert.ok((await page.locator('#updateNotes').textContent()).includes('<script>'));assert.equal(await page.locator('#updateNotes script').count(),0);
    await page.locator('#updateRelease').click();assert.equal((await calls(page,'update_action')).at(-1).args[0].action,'open_release');
    await screen(page,'updates-available-light');
  });
  await check('switching channel is explicit, requires a fresh check and never saves recording presets',async()=>{
    const count=(await calls(page,'update_action')).length;
    await page.locator('#updateChannel').selectOption('preview');assert.equal((await calls(page,'update_action')).length,count);
    assert.equal(await page.locator('#updateDownload').isDisabled(),true);
    await page.evaluate(()=>poll());assert.equal(await page.locator('#updateChannel').inputValue(),'preview');
    await page.locator('#updateCheck').click();assert.deepEqual((await calls(page,'update_action')).at(-1).args,[{action:'check',include_prerelease:true}]);
    assert.equal((await calls(page,'save_preset')).length,0);await page.locator('#updateCancel').click();
  });
  await check('download progress is determinate when sized, cancellable and leaves recording available',async()=>{
    await updates({state:'available',latest_version:'0.7.0',total_bytes:251658240,notes:'改进时间轴拖动与操作记录的可读性。'});
    await page.locator('#updateDownload').click();await page.waitForFunction(()=>document.querySelector('#updateStatus').textContent==='正在下载更新');
    assert.equal((await calls(page,'update_action')).at(-1).args[0].action,'download');
    await updates({state:'downloading',latest_version:'0.7.0',downloaded_bytes:100663296,total_bytes:251658240,notes:'改进时间轴拖动与操作记录的可读性。'});
    assert.equal(await page.locator('#updateProgress').evaluate(n=>n.value),40);
    assert.equal(await page.locator('#recordButton').isDisabled(),false);await screen(page,'updates-downloading-light');
    await page.locator('#updateClose').click();assert.equal(await page.locator('#recordButton').isEnabled(),true);
    await page.locator('#versionButton').click();assert.equal(await page.locator('#updateProgress').evaluate(n=>n.value),40);
    await updates({state:'downloading',latest_version:'0.7.0',downloaded_bytes:12345});assert.equal(await page.locator('#updateProgress').getAttribute('value'),null);
    await page.locator('#updateCancel').click();assert.equal((await calls(page,'update_action')).at(-1).args[0].action,'cancel');
    await updates({state:'verifying',latest_version:'0.7.0',total_bytes:100,downloaded_bytes:100});
    assert.equal(await page.locator('#updateInstall').isVisible(),false);assert.equal(await page.locator('#updateCancel').isVisible(),false);
  });
  await check('network failure is readable, supports explicit retry and does not affect capture CTA',async()=>{
    await updates({state:'error',latest_version:'0.7.0',error:'无法连接 GitHub，请检查网络后重试。'});
    assert.equal(await page.locator('#updateError').isVisible(),true);assert.equal(await page.locator('#updateDownload').textContent(),'重试下载');
    await page.locator('#updateDownload').click();assert.equal((await calls(page,'update_action')).at(-1).args[0].action,'download');
    await updates({state:'idle'});await page.evaluate(()=>window.__syntheticFixture.updateFailure='更新服务器暂时不可用。');
    await page.locator('#updateCheck').click();await page.waitForFunction(()=>document.querySelector('#updateError').textContent==='更新服务器暂时不可用。');
    assert.equal(await page.locator('#recordButton').isDisabled(),false);assert.equal(await page.locator('#updateCheck').isDisabled(),false);
    await screen(page,'updates-error-light');await page.evaluate(()=>window.__syntheticFixture.updateFailure='');
    await page.locator('#updateCheck').click();await page.locator('#updateCancel').click();
  });
  await check('verified installation uses backend blockers and exact review count, survives polling and races',async()=>{
    const ready={state:'ready',latest_version:'0.7.0',can_install:false,review_count:2,notes:'改进时间轴拖动与操作记录的可读性。\n新增软件内更新。',total_bytes:251658240,install_blockers:['还有场次正在整理或排队，请等待完成。','本地模型正在下载或校验，请先暂停并等待文件保存。']};
    await updates(ready);assert.equal(await page.locator('#updateInstall').isDisabled(),true);
    assert.equal(await page.locator('#updateCloseSummary').textContent(),'将关闭记录器和 2 个回看窗口。');
    assert.equal(await page.locator('#updateBlockers li').count(),2);await screen(page,'updates-blocked-light');
    await updates({...ready,can_install:true,install_blockers:['还有场次正在整理或排队，请等待完成。']});assert.equal(await page.locator('#updateInstall').isDisabled(),true);
    await updates({...ready,can_install:true,install_blockers:[]});assert.equal(await page.locator('#updateInstall').isDisabled(),false);
    await page.evaluate(()=>window.__syntheticFixture.updateFailure='请先结束录制并等待录像保存完成。');
    await page.locator('#updateInstall').click();await page.waitForFunction(()=>document.querySelector('#updateError').textContent==='请先结束录制并等待录像保存完成。');
    assert.equal(await page.locator('#updateInstall').isDisabled(),false);await page.evaluate(()=>window.__syntheticFixture.updateFailure='');
    await page.locator('#updateInstall').click();assert.equal((await calls(page,'update_action')).at(-1).args[0].action,'install');
    assert.equal(await page.locator('#updateInstall').isDisabled(),true);
    await updates({...ready,can_install:true,install_blockers:[],error:'回看窗口未能关闭，请重试。'});
    assert.equal(await page.locator('#updateInstall').isDisabled(),false);assert.equal(await page.locator('#updateError').textContent(),'回看窗口未能关闭，请重试。');
  });
  await check('unconfirmed cancellation can retry after install acceptance and cannot imply safe shutdown',async()=>{
    await updates({state:'ready',latest_version:'0.7.0',can_install:true});await page.locator('#updateInstall').click();
    await patchSnapshot(page,{closing:true,updates:{...base,state:'ready',latest_version:'0.7.0',cancel_pending:true,error:'更新助手尚未确认取消。应用已阻止关闭，请点击“重试取消”。'}});await page.evaluate(()=>poll());
    assert.equal(await page.locator('#updateStatus').textContent(),'取消尚未确认');assert.equal(await page.locator('#updateCancel').textContent(),'重试取消');
    assert.equal(await page.locator('#updateCancel').isEnabled(),true);assert.equal(await page.locator('#updateInstall').isVisible(),false);
    assert.ok(!(await page.locator('#homeStatus').textContent()).includes('安全关闭'));assert.ok(!(await page.locator('#jobDetail').textContent()).includes('自动关闭'));
    await page.evaluate(()=>window.__syntheticFixture.updateFailure='取消标记暂时无法保存，请重试。');await page.locator('#updateCancel').click();
    await page.waitForFunction(()=>document.querySelector('#updateError').textContent==='取消标记暂时无法保存，请重试。');assert.equal(await page.locator('#updateCancel').isEnabled(),true);
    await page.evaluate(()=>window.__syntheticFixture.updateFailure='');await page.locator('#updateCancel').click();
    assert.deepEqual((await calls(page,'update_action')).at(-1).args,[{action:'cancel'}]);assert.equal(await page.locator('#updateStatus').textContent(),'取消尚未确认');
    await screen(page,'updates-cancel-unconfirmed-light');
    await page.evaluate(()=>window.__syntheticFixture.confirmUpdateCancel=true);await page.locator('#updateCancel').click();
    await page.waitForFunction(()=>document.querySelector('#updateCancel').classList.contains('hidden'));
    assert.equal(await page.locator('#updateError').textContent(),'已取消这次安装，当前版本保留。');assert.equal(await page.locator('#recordButton').isEnabled(),true);
  });
  await check('previous update results survive idle polling with selectable backup and recovery instructions',async()=>{
    const names={failed:'上次更新未完成',rolled_back:'上次更新已回滚',recovery_required:'上次更新需要恢复',startup_unconfirmed:'上次更新尚未确认启动',complete:'上次更新已完成'};
    for(const [state,title] of Object.entries(names)){
      await updates({last_install:{state,version:'0.7.0',message:'合成测试结果：'+state,time:1790130434,backup_path:'D:\\synthetic-only\\事务目录\\backup'}});
      assert.equal(await page.locator('#updateLastResult').isVisible(),true);assert.equal(await page.locator('#updateLastTitle').textContent(),title);
      assert.equal(await page.locator('#updateLastMessage').textContent(),'合成测试结果：'+state);await page.evaluate(()=>poll());assert.equal(await page.locator('#updateLastTitle').textContent(),title);
    }
    await updates({last_install:{state:'recovery_required',version:'0.7.0',message:'更新未完成，请使用保留的安装助手恢复；不要删除备份。',time:1790130434,backup_path:'D:\\synthetic-only\\事务目录\\backup'}});
    assert.ok((await page.locator('#updateRecoveryHint').textContent()).includes('docs/updates.md'));
    assert.equal(await page.locator('#updateRecoveryArea').isVisible(),false);await page.locator('#updateBackupPath').click();await page.keyboard.press('Control+A');
    assert.equal(await page.locator('#updateBackupPath').evaluate(n=>n.selectionEnd-n.selectionStart),await page.locator('#updateBackupPath').evaluate(n=>n.value.length));
    await page.evaluate(()=>poll());assert.equal(await page.locator('#updateBackupPath').evaluate(n=>n.selectionEnd-n.selectionStart),await page.locator('#updateBackupPath').evaluate(n=>n.value.length));
    await screen(page,'updates-previous-recovery-light');
    await updates({last_install:{state:'rolled_back',version:'0.7.0',message:'新版本未通过检查，已恢复旧版本；备份和报告保留。',time:1790130434,backup_path:'D:\\synthetic-only\\事务目录\\backup'}});await screen(page,'updates-previous-rollback-light');
    await updates({last_install:{state:'recovery_required',version:'0.7.0',time:1790130434,backup_path:'D:\\synthetic-only\\事务目录\\backup',recovery_path:'D:\\synthetic-only\\事务目录\\恢复更新前版本.cmd',message:'更新未完成，请使用保留的安装助手恢复；不要删除备份。'}});
    assert.equal(await page.locator('#updateRecoveryValue').getAttribute('readonly'),'');await page.locator('#updateRecoveryValue').click();await page.keyboard.press('Control+A');
    assert.ok(await page.locator('#updateRecoveryValue').evaluate(n=>n.selectionEnd===n.value.length));
    assert.ok((await page.locator('#updateRecoveryHint').textContent()).includes('双击下面的恢复文件'));await screen(page,'updates-recovery-file-light');
    await page.setViewportSize({width:390,height:640});await assertInsideViewport(page,'#updateDialog');
    assert.equal(await page.locator('#updateDialog').evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);await page.locator('#updateRecoveryValue').scrollIntoViewIfNeeded();await screen(page,'updates-recovery-file-compact');
  });
  await check('compact and dark update dialog scrolls inside viewport with reachable footer and no overflow',async()=>{
    await page.locator('#updateClose').click();await page.setViewportSize({width:390,height:640});await theme(page,'dark');
    await updates({state:'ready',latest_version:'0.7.0',current_version:'0.6.0-preview.3',can_install:false,review_count:3,install_blockers:['还有场次正在整理或排队，请等待完成。'],notes:Array.from({length:25},(_,i)=>(i+1)+'. 合成测试更新说明：保留原有资料库与录制设置。').join('\n')});
    await noHorizontalOverflow(page);await screen(page,'updates-home-compact-dark');await page.locator('#versionButton').click();
    await assertInsideViewport(page,'#updateDialog');await assertInsideViewport(page,'.update-footer');
    assert.equal(await page.locator('#updateDialog').evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);
    await page.locator('.update-body').hover();await page.mouse.wheel(0,1200);await page.waitForFunction(()=>document.querySelector('.update-body').scrollTop>0);
    await assertInsideViewport(page,'#updateInstall');await screen(page,'updates-compact-dark');
    await page.keyboard.press('Escape');assert.equal(await page.locator('#versionButton').evaluate(n=>n===document.activeElement),true);
    await page.setViewportSize({width:1060,height:780});await theme(page,'light');
  });
  await page.close();
}
