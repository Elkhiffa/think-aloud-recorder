'use strict';

/**
 * Bounded browser acceptance for the actual recorder, desk and review HTML/CSS/JS.
 * All state, vocabulary and video are explicitly synthetic. The native bridge
 * is replaced before navigation; no recording, uploads, device access or user
 * files are involved. This does not establish native WebView2/OBS acceptance.
 *
 * Run: node tests/test_ui_browser.cjs
 * Supply Playwright through NODE_PATH or PLAYWRIGHT_MODULE when not installed
 * in this project. Existing Edge is used; no browser/dependency is downloaded.
 * Optional: TAR_UI_CHANNEL, TAR_UI_OUTPUT (default work/visual-acceptance),
 * TAR_UI_ONLY=<recorder|settings|new|first|device|window|vocabulary|update|desk|review> runs one group.
 *
 * Main window (ui/index.html) follows docs/plans/2026-10-19-redesign.md: a 720×600 page with a rail,
 * a self-drawn title bar, three sections, and one #sheet overlay for settings (游戏 | 通用) and the
 * 'new' / 'first' wizards. Session rows, filters and row actions live in the desk window (ui/desk.html).
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
const MAIN = { width: 720, height: 600 }; // initial = minimum main window size (app.py)
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
const referenceVocabulary = { id: 'synthetic-reference', name: '示例交互术语.txt', words: ['交互入口', '确认反馈'] };
const GAME_PAYLOAD_KEYS = ['name', 'game', 'window', 'vault', 'hotword_manual', 'game_hotword_files', 'expected_vocabulary_revision', 'confirmed_vault'];
const GENERAL_PAYLOAD_KEYS = ['source', 'monitor', 'mic', 'preset', 'language', 'transcription_provider', 'record_inputs', 'general_hotword_files', 'expected_vocabulary_revision', 'library_root'];

function snapshot(overrides = {}) {
  return {
    config: {
      game: '示例游戏 · 合成测试', vault: 'D:\\synthetic-only\\think-aloud-database', library_root: 'D:\\synthetic-only',
      preset: '均衡 1080p30', source: '游戏窗口', window: 'synthetic-window', monitor: 'synthetic-display',
      mic: 'synthetic-mic', language: 'zh', hotwords: '交互入口\n确认反馈',
      hotword_files: [clone(referenceVocabulary)], general_hotword_files: [clone(referenceVocabulary)], game_hotword_files: [],
      hotword_manual: '', transcription_provider: 'qwen', configured: true,
    },
    presets: [
      { id: 'synthetic-one', name: '示例游戏 · 合成测试', vault: 'D:\\synthetic-only\\think-aloud-database' },
      { id: 'synthetic-two', name: '另一个示例游戏', vault: 'D:\\synthetic-only\\another-game' },
    ],
    active_preset_id: 'synthetic-one',
    default_hotword_files: [bundledVocabulary],
    suggested_vault: 'D:\\synthetic-only\\think-aloud-database',
    readiness: { ready: true, checking: false, errors: [], checked_at: 123 },
    activity: { busy: false, kind: 'idle', status: '待开始', detail: '' },
    background_jobs: [{ session_id: 'synthetic-session-0', state: 'running', detail: '合成测试进度：正在整理，可继续录制。' }],
    insight: { insights: 6, latest: { name: '合成报告.md', modified: 1790130434 } },
    sessions: Array.from({ length: 14 }, (_, i) => ({
      id: `synthetic-session-${i}`, game: i % 3 === 2 ? '另一个示例游戏' : '示例游戏', path: `D:\\synthetic-only\\think-aloud-database\\synthetic-session-${i}`,
      created: `2026-09-${String(22 - i).padStart(2, '0')}T10:30:00`, duration: 438 + i * 61,
      state: i === 0 ? '转写中' : '可回看', test: true,
      ...(i===1?{title:'清河探索与初次止戈',session_name:'清河探索与初次止戈',activity_details:'清河任务 + 野外探索 + 止戈 + 萌宠争锋 + 城镇养成 + 装备比较与资源收集',preprocessing:{state:'complete',events:8}}:{}),
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
// A finished last session: problems, a quote and a review link.
const completeSession = () => ({
  id: 'synthetic-complete', game: '示例游戏', path: 'D:\\synthetic-only\\think-aloud-database\\synthetic-complete', test: true,
  created: '2026-09-23T20:05:00', duration: 3725, state: '可回看', session_name: '清河探索与初次止戈',
  preprocessing: { state: 'complete', events: 8, kinds: { obstacle: 2, confusion: 3, cost: 1, suggestion: 4 },
    quote: { text: '这个入口很显眼但我没找到返回', at: 754, kind: 'obstacle' } },
});

function reviewHTML() {
  const data = {
    id: 'synthetic-review', title: '示例游戏 · 合成回看', created: '2026-09-22T10:30:00',
    desktop: true, test: true, video: '/synthetic.webm',
    segments: Array.from({ length: 48 }, (_, i) => ({ start: i, end: i + 0.95, text: words[i % words.length] })),
  };
  const values = {
    TITLE: data.title, DATA: JSON.stringify(data), CSS: read('ui/review.css'), JS: read('ui/review.js'),
    FONTS: '', PLYR_CSS: read('ui/vendor/plyr/plyr.css'), PLYR_JS: read('ui/vendor/plyr/plyr.min.js'),
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
// Number of rendered text lines (distinct line boxes) inside an element.
async function textLines(page, selector) {
  return page.locator(selector).evaluate(node => { const range = document.createRange(); range.selectNodeContents(node); return new Set([...range.getClientRects()].filter(r => r.width > 0).map(r => Math.round(r.top))).size; });
}
// The review page still has its own theme button; the main window's appearance lives in 设置 → 通用
// ([data-theme-choice] chips call setTheme, shared through localStorage 'recorder-theme').
async function theme(page, requested) {
  if (await page.locator('#recordButton').count()) await page.evaluate(choice => setTheme(choice), requested);
  else if (await page.locator('html').getAttribute('data-theme') !== requested) await page.locator('#themeButton').click();
  assert.equal(await page.locator('html').getAttribute('data-theme'), requested);
}
async function patchSnapshot(page, patch) {
  await page.evaluate(value => { Object.assign(window.__syntheticFixture.snapshot, value); }, patch);
}
async function pollNow(page) { await page.evaluate(() => poll()); }
async function calls(page, method) {
  return page.evaluate(name => window.__syntheticFixture.calls.filter(call => call.method === name), method);
}
const sheet = page => page.locator('#sheet');
async function openSettings(page, tab = 'game') {
  await page.locator('#settingsButton').click(); await sheet(page).waitFor({ state: 'visible' });
  assert.equal(await page.locator('#sheetTitle').innerText(), '设置');
  if (tab === 'general') await page.locator('#tabGeneral').click();
  assert.equal(await page.locator(tab === 'general' ? '#tabGeneral' : '#tabGame').evaluate(n => n.classList.contains('on')), true);
}
// A game tab that does not fit is reached through 更多.
async function clickGame(page, selector) {
  const tab = page.locator('#gameTabs ' + selector);
  if (!(await tab.isVisible())) await page.locator('#gamesMoreButton').click();
  await tab.click();
}
async function closeSheet(page) {
  if (await page.locator('#actionDialog').evaluate(n => n.open)) await page.locator('#actionFooter button').first().click();
  if (await sheet(page).isVisible()) await page.locator('#wizardCancel').click();
  await sheet(page).waitFor({ state: 'hidden' });
}
// After any check on a shared page, leave no dialog or sheet open for the next one.
async function pageCheck(page, name, task) {
  await check(name, async () => { try { return await task(); } finally { await page.evaluate(() => { const dialog = document.querySelector('#actionDialog'); if (dialog?.open) dialog.close(); if (typeof sheetOpen === 'function' && sheetOpen()) closeSheet(); }).catch(() => {}); } });
}
async function stepLabels(page) { return page.locator('#wizardSteps span').evaluateAll(nodes => nodes.map(n => ({ text: n.textContent.replace(/^\d+/, ''), on: n.classList.contains('on') }))); }
async function bridge(page, state = snapshot(), requestedTheme = 'light') {
  await page.addInitScript(({ state, imported, requestedTheme }) => {
    localStorage.setItem('recorder-theme', requestedTheme);
    window.__syntheticFixture = { snapshot: state, imported, calls: [], layout: null, polls: 0, refreshSequence: 0, refreshSnapshot: null, saveFailure: '', directory: 'D:\\synthetic-only\\chosen-folder' };
    window.pywebview = { api: new Proxy({}, { get: (_, method) => async (...args) => {
      const fixture = window.__syntheticFixture;
      if (method === 'get_state') { fixture.polls++; return { ok: true, data: JSON.parse(JSON.stringify(fixture.snapshot)) }; }
      // Frame colour follows the theme on every load; it is window chrome, not a user action.
      if (method === 'win_set_frame_color') return { ok: true };
      if (method === 'get_microphone_state') return { ok: true, data: { session_id: fixture.snapshot.activity?.active_id || null, state: 'signal', level: .5, quiet_seconds: 0 } };
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
      if (method === 'refresh_device_inventory') {
        const id=`fixture-inventory-${fixture.refreshSequence++}`;
        if(fixture.refreshSnapshot)Object.assign(fixture.snapshot,JSON.parse(JSON.stringify(fixture.refreshSnapshot)));
        fixture.snapshot.device_inventory={id,state:fixture.holdInventory?'running':'succeeded',window_selection:fixture.snapshot.device_inventory?.window_selection||fixture.snapshot.readiness?.window_selection};
        return {ok:true,data:{inventory_id:id}};
      }
      if (method === 'select_preset') {
        const preset = fixture.snapshot.presets.find(item => item.id === args[0]);
        if (!preset) return { ok: false, error: '合成测试：预设不存在。' };
        fixture.snapshot.active_preset_id = preset.id; fixture.snapshot.config = { ...fixture.snapshot.config, game: preset.name, vault: preset.vault };
        return { ok: true, data: {} };
      }
      if (method === 'save_preset' || method === 'save_general') {
        if (fixture.saveFailure) return { ok: false, error: fixture.saveFailure };
        return { ok: true, data: { id: args[1] || 'synthetic-created' } };
      }
      if (method === 'choose_directory') return { ok: true, data: { path: fixture.directory } };
      if (method === 'choose_hotword_files') return { ok: true, data: { files: fixture.imported } };
      if (method === 'get_layout') return { ok: true, data: fixture.layout };
      if (method === 'save_layout') { fixture.layout = { ...fixture.layout, [args[0]]: args[1] }; return { ok: true }; }
      if (['ready', 'copy_path', 'open_folder', 'open_document', 'open_bailian_console', 'open_dictionary_site', 'save_cloud_key',
        'open_desk', 'open_review', 'process_session', 'stop_recording', 'win_minimize', 'win_toggle_maximize', 'win_close'].includes(method)) return { ok: true };
      throw new Error(`Synthetic harness did not authorize native action: ${String(method)}`);
    } }) };
  }, { state, imported: importedFiles, requestedTheme });
}
async function mainPage(context, origin, state = snapshot(), requestedTheme = 'light', viewport = MAIN) {
  const page = await context.newPage(); await page.setViewportSize(viewport); await bridge(page, state, requestedTheme);
  await page.goto(origin + '/ui/index.html'); await page.waitForFunction(() => window.__syntheticFixture.polls > 0 && store.connected);
  return page;
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

// ---------------------------------------------------------------- main window (idle, alert, recording)
async function homeChecks(context, origin) {
  const page = await mainPage(context, origin);
  await page.locator('#lastSession .last').waitFor();
  await pageCheck(page, 'home ready while a synthetic background transcription is running', async () => {
    assert.equal(await page.locator('#recordButton').isEnabled(), true);
    assert.equal(await page.locator('#homeStatus').innerText(), '已就绪');
    assert.equal(await page.locator('#homeStatus').evaluate(n => n.classList.contains('ready')), true);
    assert.equal(await page.locator('#blockers').isVisible(), false);
    assert.equal(await page.locator('#alertActions').isVisible(), false);
    // The running background job is shown where the last session sits, not as a blocker.
    assert.deepEqual(await page.locator('#lastSession .steps li').allInnerTexts(), ['已保存', '转写中', '待整理']);
    assert.equal(await page.locator('#lastSession .steps li.now').innerText(), '转写中');
    assert.equal(await page.locator('#queueBrief').innerText(), '1 段转写中', 'background work is summarised under 全部场次');
    assert.equal((await calls(page, 'start_recording')).length, 0);
  });
  await pageCheck(page, '720×600 main window shows the title, all three sections and the window buttons without overflow', async () => {
    for (const mode of ['light', 'dark']) {
      await theme(page, mode); await screen(page, `home-${mode}-720x600`);
      await noHorizontalOverflow(page);
      assert.equal(await page.locator('#home').evaluate(n => n.scrollTop), 0);
      assert.equal(await page.getByText('原话选中', { exact: true }).count(), 0); assert.equal(await page.getByText('窗口未打开', { exact: true }).count(), 0);
      for (const selector of ['#gameTabs .g.on', '#recordButton', '#lastSession', '#openLibrary', '#openInsight', '#insightBrief', '#winMin', '#winMax', '#winClose', '#methodButton', '#settingsButton']) await assertInsideViewport(page, selector);
      const [title, min, max, close] = await Promise.all(['#gameTabs .g.on', '#winMin', '#winMax', '#winClose'].map(selector => box(page, selector)));
      assert.ok(min.x < max.x && max.x < close.x, 'minimize, maximize, close from left to right');
      closeEnough(close.x + close.width, MAIN.width, 'close button sits at the right edge');
      closeEnough(min.y, 0, 'window buttons sit at the top edge');
      assert.ok(title.x + title.width <= min.x, 'game title does not run under the window buttons');
      const order = await Promise.all(['#capturePanel', '#lastSection', '#insightSection'].map(selector => box(page, selector)));
      assert.ok(order[0].y + order[0].height <= order[1].y + 1 && order[1].y + order[1].height <= order[2].y + 1, 'three sections stack in order');
    }
    await theme(page, 'light');
    await page.locator('#winMin').click(); await page.locator('#winMax').click(); await page.locator('#winClose').click();
    assert.deepEqual((await page.evaluate(() => window.__syntheticFixture.calls.map(call => call.method))).filter(name => name.startsWith('win_')), ['win_minimize', 'win_toggle_maximize', 'win_close']);
  });
  await pageCheck(page, 'equal section headings; record button and ready status never wrap', async () => {
    const headings = await page.locator('#lastHeading,#openLibrary .h,#openInsight .h').evaluateAll(nodes => nodes.map(node => ({ size: getComputedStyle(node).fontSize, weight: getComputedStyle(node).fontWeight, family: getComputedStyle(node).fontFamily })));
    assert.equal(headings.length, 3); assert.deepEqual(headings[1], headings[0]); assert.deepEqual(headings[2], headings[0]);
    assert.equal(await textLines(page, '#recordButtonText'), 1); assert.equal(await textLines(page, '#homeStatus'), 1);
    const button = await box(page, '#recordButton'), status = await box(page, '#homeStatus');
    assert.ok(status.x >= button.x + button.width, 'ready status sits beside the record button');
    closeEnough(status.y + status.height / 2, button.y + button.height / 2, 'ready status is vertically centred on the record button');
    return headings;
  });
  await pageCheck(page, 'game tabs: the current game is the page title, others switch through select_preset, ＋ opens a new game', async () => {
    assert.deepEqual(await page.locator('#gameTabs [data-game]').evaluateAll(nodes => nodes.map(n => [n.dataset.game, n.classList.contains('on'), n.getAttribute('aria-current')])), [['synthetic-one', true, 'page'], ['synthetic-two', false, null]]);
    assert.equal(await page.locator('#gameTabs .g.on').innerText(), snapshot().config.game);
    const order = await page.locator('#gameTabs [data-game]').evaluateAll(nodes => nodes.map(n => n.dataset.game));
    await clickGame(page, '[data-game="synthetic-two"]');
    await page.waitForFunction(() => document.querySelector('#gameTabs .g.on')?.dataset.game === 'synthetic-two');
    assert.deepEqual((await calls(page, 'select_preset')).map(call => call.args), [['synthetic-two']]);
    for (const where of ['#gameTabs > a[data-game]', '#gamesMoreMenu [data-game]']) { const ids = await page.locator(where).evaluateAll(nodes => nodes.map(n => n.dataset.game)); assert.deepEqual(ids, order.filter(id => ids.includes(id)), 'tab order is fixed and does not reorder on switching (tabs and 更多 each follow the game list)'); }
    await page.locator('#gameTabs .g.on').click(); assert.equal((await calls(page, 'select_preset')).length, 1, 'clicking the current game does nothing');
    await clickGame(page, '[data-game="synthetic-one"]');
    await page.waitForFunction(() => document.querySelector('#gameTabs .g.on')?.dataset.game === 'synthetic-one');
    await clickGame(page, '[data-game-add]'); await sheet(page).waitFor({ state: 'visible' });
    assert.equal(await page.locator('#sheetTitle').innerText(), '新建游戏');
    await closeSheet(page); assert.equal((await calls(page, 'save_preset')).length, 0);
    await page.locator('#gameTabs').evaluate(nav => { nav.scrollLeft = 0; }); // Playwright scrolled the clipped ＋ into view
  });
  await pageCheck(page, 'game tabs that do not fit beside the title fold into 更多 instead of being cut off', async () => {
    // Design: other games follow the title in small type; when they do not fit they fold into 更多.
    const clipped = await page.locator('#gameTabs').evaluate(nav => { nav.scrollLeft = 0; const area = nav.getBoundingClientRect(); return [...nav.querySelectorAll('a,button')].filter(el => { const r = el.getBoundingClientRect(); return r.right > area.right + 1 || r.left < area.left - 1; }).map(el => el.dataset.game || (el.hasAttribute('data-game-add') ? '＋' : el.textContent)); });
    const more = await page.locator('#gameTabs').getByText('更多').count();
    assert.ok(!clipped.length || more > 0, `game tabs cut off by the title area without 更多: ${JSON.stringify(clipped)} (nav ${JSON.stringify(await box(page, '#gameTabs'))})`);
  });
  await check('with many long game names at 720 wide, nothing is cut off and the folded games and ＋ are reachable in 更多', async () => {
    const names = ['燕云十六声 · 开放世界主线', '逆水寒 · 手游版副本', '永劫无间 · 新手引导', '鸣潮 · 声骸系统'];
    const p = await mainPage(context, origin, snapshot({ presets: names.map((name, i) => ({ id: 'long-' + i, name, vault: 'D:\\synthetic-only\\long-' + i })), active_preset_id: 'long-0' }));
    try {
      const clipped = await p.locator('#gameTabs').evaluate(nav => { const area = nav.getBoundingClientRect(); return [...nav.querySelectorAll(':scope > a, :scope > .more > button')].filter(el => { const r = el.getBoundingClientRect(); return r.right > area.right + 1; }).map(el => el.textContent); });
      assert.deepEqual(clipped, [], 'every visible tab lies inside the title area');
      assert.equal(await p.locator('#gamesMoreButton').isVisible(), true);
      await p.locator('#gamesMoreButton').click();
      assert.equal(await p.locator('#gamesMoreMenu').isVisible(), true);
      const folded = await p.locator('#gamesMoreMenu .item').allInnerTexts();
      assert.ok(folded.length >= 1, 'at least one game is folded');
      const visible = await p.locator('#gameTabs > a[data-game]').allInnerTexts();
      assert.deepEqual([...visible, ...folded.filter(text => !text.startsWith('＋'))], names, 'with the first game current, the tabs and then 更多 keep the game order');
      assert.ok((await p.locator('#gameTabs [data-game-add]').count()) === 1, '＋ stays reachable, as a tab or in the menu');
      await screen(p, 'home-games-more-light-720x600');
      // Resizing unfolds and refolds the same nodes: the order holds and the title is never re-created.
      await p.evaluate(() => { window.__title = document.querySelector('#gameTabs .g.on'); });
      await p.setViewportSize({ width: 1900, height: 600 });
      await p.waitForFunction(() => document.querySelector('#gamesMore').classList.contains('hidden'));
      assert.deepEqual(await p.locator('#gameTabs > a[data-game]').allInnerTexts(), names, 'wide enough: every game is a tab again, in order');
      await p.setViewportSize(MAIN);
      await p.waitForFunction(() => !document.querySelector('#gamesMore').classList.contains('hidden'));
      assert.equal(await p.evaluate(() => window.__title === document.querySelector('#gameTabs .g.on') && window.__title.isConnected), true);
      await p.locator('#gamesMoreButton').click();
      await p.locator('#gamesMoreMenu [data-game="long-3"]').click();
      assert.deepEqual((await calls(p, 'select_preset')).at(-1).args, ['long-3']);
      assert.equal(await p.locator('#gamesMoreMenu').isVisible(), false, 'choosing a game closes the menu');
    } finally { await p.close(); }
  });
  await pageCheck(page, 'alert replaces the ready text beside the disabled record button, with recheck and settings actions', async () => {
    const readyButton = await box(page, '#recordButton'), readyPanel = await box(page, '#capturePanel'), readyLast = await box(page, '#lastSection');
    try { for (const reason of ['未找到游戏窗口，请先打开游戏。', '云端密钥缺失，请重新配置。']) {
      await patchSnapshot(page, { readiness: { ready: false, checking: false, errors: [{ message: reason, step: 1 }] } });
      await page.waitForFunction(text => document.querySelector('#blockers').textContent === text, reason);
      await screen(page, 'home-alert-720x600');
      assert.equal(await page.locator('#recordButton').isEnabled(), false);
      assert.equal(await page.locator('#homeStatus').isVisible(), false);
      assert.equal(await page.locator('#blockers').isVisible(), true);
      assert.equal(await page.locator('#statusSlot #blockers').count(), 1);
      assert.equal(await page.locator('#statusSlot #homeStatus').count(), 1);
      assert.equal(await page.locator('#capturePanel').evaluate(n => n.classList.contains('alerting')), true);
      assert.equal(await page.locator('#alertActions').isVisible(), true);
      assert.equal(await page.locator('#alertRecheck').isVisible(), true); assert.equal(await page.locator('#alertSettings').isVisible(), true);
      const reasonBox = await box(page, '#statusSlot'), button = await box(page, '#recordButton');
      assert.ok(reasonBox.x >= button.x + button.width, 'the alert sits beside the disabled record button');
      for (const key of ['x', 'y', 'width', 'height']) closeEnough(button[key], readyButton[key], `record button ${key} stays put`);
      closeEnough((await box(page, '#capturePanel')).height, readyPanel.height, 'first section keeps its height for a single reason');
      closeEnough((await box(page, '#lastSection')).y, readyLast.y, 'second section does not move for a single reason');
    }
    await page.locator('#alertRecheck').click(); assert.equal((await calls(page, 'refresh_devices')).length, 1);
    } finally {
      await patchSnapshot(page, { readiness: snapshot().readiness });
      await page.waitForFunction(() => !document.querySelector('#recordButton').disabled);
    }
  });
  await pageCheck(page, 'alert settings action opens the tab that holds the failing setting', async () => {
    try {
      for (const [code, tab] of [['MICROPHONE_MISSING', '#tabGeneral'], ['WINDOW_MISSING', '#tabGame']]) {
        await patchSnapshot(page, { readiness: { ready: false, checking: false, errors: [{ code, message: '合成阻碍：' + code, step: 1 }] } });
        await page.waitForFunction(text => document.querySelector('#blockers').textContent === text && !document.querySelector('#alertSettings').classList.contains('hidden'), '合成阻碍：' + code);
        await page.locator('#alertSettings').click(); await sheet(page).waitFor({ state: 'visible' });
        assert.equal(await page.locator(tab).evaluate(n => n.classList.contains('on')), true, code);
        await closeSheet(page);
      }
    } finally { await patchSnapshot(page, { readiness: snapshot().readiness }); await page.waitForFunction(() => !document.querySelector('#recordButton').disabled); }
  });
  for (const viewport of [MAIN, { width: 920, height: 1040 }]) {
    for (const requestedTheme of ['light', 'dark']) {
      await pageCheck(page, `stable home geometry across wrapped error and checking states (${requestedTheme} ${viewport.width})`, async () => {
        await page.setViewportSize(viewport); await theme(page, requestedTheme);
        const selectors = ['#recordButton', '#settingsButton', '#gameTabs .g.on', '#capturePanel', '#lastSection'];
        const baseline = Object.fromEntries(await Promise.all(selectors.map(async selector => [selector, await box(page, selector)])));
        const states = [
          { name: 'ready', readiness: snapshot().readiness },
          { name: 'one-line', readiness: { ready: false, checking: false, errors: [{ message: '麦克风未连接。' }] } },
          { name: 'two-lines', readiness: { ready: false, checking: false, errors: [{ message: '已选云端转写，但尚未保存本机 API Key。' }, { message: '保存位置当前不可写，请检查目录。' }] } },
          { name: 'many-lines', readiness: { ready: false, checking: false, errors: ['设置的游戏窗口尚未打开。', '所选麦克风未连接，请检查连接。', '尚未保存本机 API Key。', '保存位置当前不可写，请检查目录。', '这些内容全部来自合成测试。'].map(message => ({ message })) } },
          { name: 'one-long', readiness: { ready: false, checking: false, errors: [{ message: '录制引擎文件缺失，请恢复完整应用文件夹；这一条合成原因故意写得很长，用来确认放不下两行时会收起并提供查看全文，而不是在提示块里滚动或把下面的内容挤下去。' }] } },
          { name: 'checking', readiness: { ready: false, checking: true, errors: [] } },
          { name: 'ready-again', readiness: snapshot().readiness },
        ];
        const measured = [];
        try {
          for (const state of states) {
            await patchSnapshot(page, { readiness: state.readiness });
            await page.waitForFunction(state => {
              const expected = state.readiness.errors[0]?.message || '';
              return document.querySelector('#blockers').textContent === expected &&
                document.querySelector('#recordButton').disabled === !state.readiness.ready &&
                (!state.readiness.checking || document.querySelector('#homeStatus').textContent === '正在检查录制条件');
            }, state);
            const current = Object.fromEntries(await Promise.all(selectors.map(async selector => [selector, await box(page, selector)])));
            measured.push({ state: state.name, bounds: current });
            if (state.name === 'many-lines') await screen(page, `home-errors-${requestedTheme}-${viewport.width}x${viewport.height}`);
            // Design (第三轮): the alert sits beside the greyed button and the first section keeps its height.
            for (const selector of selectors) for (const key of ['x', 'y', 'width', 'height']) closeEnough(current[selector][key], baseline[selector][key], `${state.name} ${selector}.${key}`);
            if (state.readiness.errors.length > 1 || state.name === 'one-long') {
              // The alert never scrolls: one reason in at most two lines, the rest behind one click.
              assert.ok(await page.locator('#statusSlot').evaluate(node => node.scrollHeight <= node.clientHeight + 1 && getComputedStyle(node).overflowY !== 'auto'), 'the alert does not scroll');
              assert.ok(await page.locator('#blockers').evaluate(node => node.getBoundingClientRect().height <= 41), 'one reason in at most two lines');
              const errors = state.readiness.errors.map(item => item.message);
              assert.equal(await page.locator('#alertMore').innerText(), errors.length > 1 ? `全部 ${errors.length} 项` : '查看全文');
              await page.locator('#alertMore').click(); await page.locator('#actionDialog[open]').waitFor();
              assert.deepEqual(await page.locator('#actionBody .alert-list li').allInnerTexts(), errors, 'every reason is listed in full');
              await page.locator('#actionFooter button').first().click();
            } else assert.equal(await page.locator('#alertMore').isVisible(), false, `${state.name}: nothing more to show`);
          }
          return measured;
        } catch (error) { error.message += `\nmeasured: ${JSON.stringify(measured.map(m => ({ state: m.state, capturePanel: m.bounds['#capturePanel'], lastSection: m.bounds['#lastSection'] })))}`; throw error; }
        finally {
          await patchSnapshot(page, { readiness: snapshot().readiness });
          await page.waitForFunction(() => !document.querySelector('#recordButton').disabled);
        }
      });
    }
  }
  await page.setViewportSize(MAIN); await theme(page, 'light');
  await pageCheck(page, 'finished last session shows problems and a quote; the quote steps aside while alerting', async () => {
    const sessions = [completeSession(), ...snapshot().sessions];
    try {
      await patchSnapshot(page, { sessions }); await page.waitForFunction(() => document.querySelector('#lastSession blockquote'));
      assert.match(await page.locator('#lastSession h3').innerText(), /^清河探索与初次止戈/);
      assert.match(await page.locator('#lastSession .meta').innerText(), /^6 个问题/, 'problems count only the four problem kinds');
      assert.match(await page.locator('#lastSession blockquote').innerText(), /这个入口很显眼但我没找到返回[\s\S]*00:12:34 · 阻碍/);
      assert.equal(await page.locator('#lastSession .day').innerText(), '23');
      assert.equal(await page.locator('#sessionCount').innerText(), String(sessions.length));
      assert.equal(await page.locator('#insightCount').innerText(), '6');
      assert.match(await page.locator('#insightBrief').innerText(), /^最新报告 \d+ 月 \d+ 日$/);
      await screen(page, 'home-last-complete-720x600');
      for (const selector of ['#lastSession blockquote', '[data-last-review]', '#openLibrary', '#openInsight', '#insightBrief']) await assertInsideViewport(page, selector);
      await page.locator('[data-last-review]').click(); assert.deepEqual((await calls(page, 'open_review')).at(-1).args, ['synthetic-complete']);
      await patchSnapshot(page, { readiness: { ready: false, checking: false, errors: [{ message: '麦克风未连接。' }] } });
      await page.waitForFunction(() => !document.querySelector('#lastSession blockquote'));
      assert.match(await page.locator('#lastSession .meta').innerText(), /6 个问题/, 'facts stay; only the quote steps aside');
      await patchSnapshot(page, { readiness: snapshot().readiness }); await page.waitForFunction(() => document.querySelector('#lastSession blockquote'));
    } finally { await patchSnapshot(page, { sessions: snapshot().sessions, readiness: snapshot().readiness }); await page.waitForFunction(() => !document.querySelector('#lastSession blockquote')); }
  });
  await pageCheck(page, 'untranscribed last session asks before transcribing; an unorganized one copies the hand-off', async () => {
    const base = snapshot().sessions;
    try {
      await patchSnapshot(page, { background_jobs: [], sessions: [{ ...base[0], state: '待转写' }, ...base.slice(1)] });
      await page.locator('[data-last-process]').waitFor();
      assert.equal(await page.locator('[data-last-process]').innerText(), '开始转写');
      await page.locator('[data-last-process]').click(); await page.locator('#actionDialog[open]').waitFor();
      assert.match(await page.locator('#actionBody').innerText(), /将上传这次的麦克风录音到 Qwen/);
      assert.match(await page.locator('#actionBody').innerText(), /恢复原任务，避免重复提交/);
      assert.equal((await calls(page, 'process_session')).length, 0, 'nothing starts before confirmation');
      await page.locator('#actionFooter button', { hasText: '开始整理' }).click();
      assert.deepEqual((await calls(page, 'process_session')).at(-1).args, ['synthetic-session-0']);
      await patchSnapshot(page, { sessions: [{ ...base[0], state: '可回看', preprocessing: { state: 'none' } }, ...base.slice(1)] });
      await page.locator('[data-copy-handoff]').waitFor();
      assert.deepEqual(await page.locator('#lastSession .steps li').allInnerTexts(), ['已保存', '已转写', '待整理']);
      await page.locator('[data-copy-handoff]').click();
      await page.waitForFunction(() => document.querySelector('#toast').classList.contains('show'));
      const copied = await page.evaluate(() => navigator.clipboard.readText());
      assert.match(copied, /场次文件夹：D:\\synthetic-only\\think-aloud-database\\synthetic-session-0/);
      assert.match(copied, /只整理这一场/);
      assert.equal(await page.locator('[data-last-review]').isEnabled(), true);
      await screen(page, 'home-last-handoff-720x600');
    } finally { await patchSnapshot(page, { sessions: base, background_jobs: snapshot().background_jobs }); }
  });
  await pageCheck(page, 'all-sessions and insight rows open the desk window on the matching tab', async () => {
    await page.locator('#openLibrary').click(); await page.locator('#openInsight').click();
    assert.deepEqual((await calls(page, 'open_desk')).map(call => call.args), [['sessions'], ['insight']]);
    assert.equal(await page.locator('#sessionCount').innerText(), '14');
  });
  await pageCheck(page, 'an empty library invites the first recording and hides the session and insight rows', async () => {
    try {
      await patchSnapshot(page, { sessions: [], background_jobs: [] });
      await page.waitForFunction(() => document.querySelector('#lastSession .empty')?.textContent.startsWith('还没有记录'));
      assert.equal(await page.locator('#lastSession').innerText(), '还没有记录。点开始录制，边玩边说出你此刻的想法。');
      assert.equal(await page.locator('#openLibrary').isVisible(), false); assert.equal(await page.locator('#openInsight').isVisible(), false);
      await screen(page, 'home-empty-720x600');
    } finally { await patchSnapshot(page, { sessions: snapshot().sessions, background_jobs: snapshot().background_jobs }); await page.locator('#openLibrary').waitFor(); }
  });
  await pageCheck(page, 'recording keeps only the clock, the microphone gauge and a prompt; settings and game switching lock', async () => {
    try {
      await patchSnapshot(page, { activity: { kind: 'recording', busy: false, status: '录制中', active_id: 'synthetic-recording', elapsed_seconds: 84 }, readiness: { ready: false, checking: false, errors: [] } });
      await page.waitForFunction(() => document.querySelector('#capturePanel').classList.contains('recording'));
      assert.equal(await page.locator('#liveClock').isVisible(), true); assert.equal(await page.locator('#recordingTime').innerText(), '00:01:24');
      assert.equal(await page.locator('#liveGauges').isVisible(), true); assert.equal(await page.locator('#livePrompt').isVisible(), true);
      for (const hidden of ['#lastSession', '#openLibrary', '#openInsight', '#insightBrief', '#blockers', '#alertActions']) assert.equal(await page.locator(hidden).isVisible(), false, hidden);
      assert.equal(await page.locator('#lastHeading').innerText(), '收音与操作');
      assert.equal(await page.locator('#gameTabs [data-game],#gameTabs [data-game-add]').count(), 0, 'no game switching while recording');
      assert.equal(await page.locator('#gameTabs .g.on').innerText(), snapshot().config.game);
      assert.match(await page.locator('#gameTabs .lock').innerText(), /录制中不能切换/);
      assert.equal(await page.locator('#recordButtonText').innerText(), '结束录制'); assert.equal(await textLines(page, '#recordButtonText'), 1);
      assert.equal(await page.locator('#recordButton').isEnabled(), true);
      assert.equal(await page.locator('#settingsButton').isDisabled(), true);
      await page.evaluate(() => openSheet('settings')); assert.equal(await sheet(page).isVisible(), false, 'settings cannot open while recording');
      await noHorizontalOverflow(page);
      for (const selector of ['#recordButton', '#liveClock', '#microphoneMonitor', '#livePrompt']) await assertInsideViewport(page, selector);
      await screen(page, 'home-recording-720x600');
      await page.locator('#recordButton').click(); assert.equal((await calls(page, 'stop_recording')).length, 1);
      assert.equal((await calls(page, 'start_recording')).length, 0);
    } finally {
      await patchSnapshot(page, { activity: snapshot().activity, readiness: snapshot().readiness });
      await page.waitForFunction(() => !document.querySelector('#capturePanel').classList.contains('recording') && !document.querySelector('#recordButton').disabled);
    }
    assert.equal(await page.locator('#lastSession').isVisible(), true); assert.equal(await page.locator('#liveGauges').isVisible(), false);
  });
  await pageCheck(page, 'quiet rail help; library folder access lives in game settings', async () => {
    assert.equal(await page.locator('.rail #methodButton').count(), 1); assert.equal(await page.locator('.rail #settingsButton').count(), 1);
    assert.equal(await page.locator('#openVault').isVisible(), false);
    await page.locator('#methodButton').click(); await page.locator('#actionDialog[open]').waitFor();
    assert.equal(await page.locator('#actionBody .method-card').count(), 4);
    await page.locator('#actionFooter button').first().click();
    await openSettings(page, 'game');
    await page.locator('#openVault').click();
    assert.deepEqual((await calls(page, 'open_folder')).map(call => call.args), [[]]);
    await closeSheet(page);
  });
  await pageCheck(page, 'long storage paths stay accessible without consuming home space', async () => {
    await page.setViewportSize({ width: 920, height: 1040 });
    const longPath = 'F:/synthetic-only/' + '很长的示例项目名称和归档位置/'.repeat(8) + 'think-aloud-database';
    const before = await box(page, '#capturePanel'), last = await box(page, '#lastSection');
    try {
      await patchSnapshot(page, { config: { ...snapshot().config, vault: longPath } }); await pollNow(page);
      assert.deepEqual(await box(page, '#capturePanel'), before); assert.deepEqual(await box(page, '#lastSection'), last);
      assert.equal(await page.getByText(longPath).count(), 0, 'the library path is not printed on the home page');
      await screen(page, 'home-light-920x1040'); await theme(page, 'dark'); await screen(page, 'home-dark-920x1040'); await theme(page, 'light');
      await page.setViewportSize(MAIN);
      await openSettings(page, 'game');
      assert.equal(await page.locator('#vault').inputValue(), longPath);
      assert.equal(await page.locator('#vault').getAttribute('readonly'), '');
      await page.locator('#vault').scrollIntoViewIfNeeded(); await assertInsideViewport(page, '#vault'); await assertInsideViewport(page, '#openVault');
      await assertInsideViewport(page, '#wizardCancel'); await noHorizontalOverflow(page);
      assert.ok(await page.locator('#wizardBody').evaluate(n => n.scrollWidth <= n.clientWidth + 1), 'settings body has no horizontal scroll');
      await screen(page, 'settings-long-path-720x600');
      await closeSheet(page);
    } finally { await patchSnapshot(page, { config: snapshot().config }); await page.setViewportSize(MAIN); }
  });
  await page.close();
}

// ---------------------------------------------------------------- settings sheet (游戏 | 通用)
async function settingsChecks(context, origin) {
  const page = await mainPage(context, origin);
  await pageCheck(page, 'settings open on the current game; untouched settings offer only 关闭', async () => {
    await openSettings(page, 'game');
    assert.equal(await page.locator('#sheetTabs').isVisible(), true); assert.equal(await page.locator('#wizardSteps').isVisible(), false);
    assert.deepEqual(await page.locator('#gameSubtabs a').evaluateAll(nodes => nodes.map(n => [n.textContent, n.classList.contains('on')])), [['示例游戏 · 合成测试', true], ['另一个示例游戏', false], ['＋ 新游戏', false]]);
    assert.equal(await page.locator('#panelGame').isVisible(), true); assert.equal(await page.locator('#panelGeneral').isVisible(), false);
    for (const field of ['game-name', 'game-window', 'game-vocab', 'game-manual', 'game-vault']) assert.equal(await page.locator(`#panelGame [data-in="${field}"]`).isVisible(), true, field);
    assert.equal(await page.locator('#game').inputValue(), snapshot().config.game);
    assert.equal(await page.locator('#vault').inputValue(), snapshot().config.vault);
    assert.equal(await page.locator('#wizardCancel').innerText(), '关闭'); assert.equal(await page.locator('#wizardNext').isVisible(), false);
    assert.equal(await page.locator('#sheetMessage').innerText(), '');
    assert.equal(await page.locator('#settingsButton').evaluate(n => n.classList.contains('on')), true);
    await screen(page, 'settings-game-light-720x600');
    await page.locator('#tabGeneral').click();
    assert.equal(await page.locator('#panelGeneral').isVisible(), true); assert.equal(await page.locator('#gameSubtabs').isVisible(), false);
    for (const id of ['#mic', '#source', '#preset', '#recordInputs', '#providerTabs', '#language', '#hotwordFiles', '#themeChoice', '#libraryRoot', '#methodLink', '#updateGroup']) assert.equal(await page.locator(id).count(), 1, id);
    assert.equal(await page.locator('#updateGroup').isVisible(), true);
    await screen(page, 'settings-general-light-720x600');
    await closeSheet(page);
    assert.equal(await page.locator('#settingsButton').evaluate(n => n.classList.contains('on')), false);
  });
  await pageCheck(page, 'edits mark the sheet dirty and block switching tabs or games until saved or cancelled', async () => {
    await openSettings(page, 'game');
    await page.locator('#game').fill('不应持久化的修改');
    assert.equal(await page.locator('#sheetMessage').innerText(), '有未保存的修改');
    assert.equal(await page.locator('#wizardCancel').innerText(), '取消');
    assert.equal(await page.locator('#wizardNext').isVisible(), true); assert.equal(await page.locator('#wizardNext').innerText(), '保存');
    await page.locator('#tabGeneral').click();
    assert.equal(await page.locator('#tabGame').evaluate(n => n.classList.contains('on')), true, 'tab switch is refused');
    assert.match(await page.locator('#wizardError').innerText(), /请先保存或取消当前修改/);
    await page.locator('#gameSubtabs [data-sub-game="synthetic-two"]').click();
    assert.match(await page.locator('#wizardError').innerText(), /请先保存或取消当前修改，再切换游戏/);
    assert.equal((await calls(page, 'select_preset')).length, 0, 'switching game with unsaved edits never reaches the bridge');
    await page.locator('#gameSubtabs [data-sub-add]').click(); assert.equal(await page.locator('#sheetTitle').innerText(), '设置');
    await screen(page, 'settings-dirty-light-720x600');
    await page.keyboard.press('Escape'); await sheet(page).waitFor({ state: 'hidden' });
    await openSettings(page, 'game');
    assert.equal(await page.locator('#game').inputValue(), snapshot().config.game, 'cancel discards the draft');
    assert.equal(await page.locator('#wizardError').isVisible(), false);
    assert.equal((await calls(page, 'save_preset')).length, 0);
    await closeSheet(page);
  });
  await pageCheck(page, 'a clean sheet switches games through its sub-tabs and reopens on the new current game', async () => {
    await openSettings(page, 'game');
    await page.locator('#gameSubtabs [data-sub-game="synthetic-two"]').click();
    await page.waitForFunction(() => document.querySelector('#gameSubtabs .on')?.dataset.subGame === 'synthetic-two' && !document.querySelector('#sheet').classList.contains('hidden'));
    assert.deepEqual((await calls(page, 'select_preset')).map(call => call.args), [['synthetic-two']]);
    assert.equal(await page.locator('#game').inputValue(), '另一个示例游戏');
    await page.locator('#gameSubtabs [data-sub-game="synthetic-one"]').click();
    await page.waitForFunction(() => document.querySelector('#gameSubtabs .on')?.dataset.subGame === 'synthetic-one' && !document.querySelector('#sheet').classList.contains('hidden'));
    await page.locator('#gameSubtabs [data-sub-add]').click();
    assert.equal(await page.locator('#sheetTitle').innerText(), '新建游戏');
    await closeSheet(page);
  });
  await pageCheck(page, 'cancellation preserves settings and clears synthetic secret input', async () => {
    await openSettings(page, 'general');
    assert.equal(await page.locator('#cloudKey').inputValue(), '');
    assert.match(await page.locator('#cloudStatus').innerText(), /密钥已保存/);
    assert.equal(await page.locator('#cloudKey').getAttribute('type'), 'password');
    await page.locator('#cloudKey').fill('synthetic-not-a-real-key');
    assert.equal(await page.locator('#sheetMessage').innerText(), '有未保存的修改', 'a typed key is an unsaved change');
    await page.locator('#wizardCancel').click(); await sheet(page).waitFor({ state: 'hidden' });
    assert.equal(await page.locator('#cloudKey').inputValue(), '', 'closing clears the secret input');
    await openSettings(page, 'general');
    assert.equal(await page.locator('#cloudKey').inputValue(), '');
    assert.equal((await calls(page, 'save_cloud_key')).length, 0);
    assert.equal((await calls(page, 'save_preset')).length + (await calls(page, 'save_general')).length, 0);
    await closeSheet(page);
  });
  await pageCheck(page, 'Bailian console uses a native link action; general vocabulary accepts multiple files', async () => {
    await openSettings(page, 'general');
    await page.getByRole('link', { name: /百炼控制台/ }).click();
    assert.equal((await calls(page, 'open_bailian_console')).length, 1);
    assert.equal(await page.locator('#hotwordFiles .chip').count(), 1);
    await page.locator('#chooseHotwordFiles').click();
    await page.waitForFunction(() => document.querySelectorAll('#hotwordFiles .chip').length === 3);
    assert.match(await page.locator('#vocabularyCount').innerText(), /通用 3 份.*本游戏 0 份.*合并后 4 个词/);
    await page.locator('#chooseHotwordFiles').click();
    assert.equal(await page.locator('#hotwordFiles .chip').count(), 3, 'reimport does not duplicate selected files');
    assert.equal((await calls(page, 'choose_hotword_files')).length, 2);
    await page.locator('#dictionaryDownload').click(); assert.equal((await calls(page, 'open_dictionary_site')).length, 1);
    await screen(page, 'settings-vocabulary-light-720x600');
    await page.locator('#hotwordFiles [data-remove-vocabulary="synthetic-game"]').click();
    assert.equal(await page.locator('#hotwordFiles .chip').count(), 2);
    assert.equal((await calls(page, 'save_general')).length, 0, 'vocabulary changes stay in the draft');
    await closeSheet(page);
  });
  await pageCheck(page, 'game vocabulary is added to this game only; the general list is untouched', async () => {
    await openSettings(page, 'game');
    await page.locator('#chooseGameHotwordFiles').click();
    await page.waitForFunction(() => document.querySelectorAll('#gameHotwordFiles .chip').length === 2);
    assert.deepEqual(await page.locator('#gameHotwordFiles [data-remove-vocabulary]').evaluateAll(n => n.map(b => b.dataset.removeVocabulary)), ['synthetic-game', 'synthetic-characters']);
    assert.equal(await page.locator('#hotwordFiles .chip').count(), 1, 'general list keeps only the general file');
    assert.equal(await page.locator('#sheetMessage').innerText(), '有未保存的修改');
    await closeSheet(page);
  });
  await pageCheck(page, 'transcription uses exactly two accessible tabs with click and keyboard selection', async () => {
    await openSettings(page, 'general');
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
    await screen(page, 'settings-local-tab-light-720x600');
    await page.locator('#providerQwen').click();
    assert.equal((await calls(page, 'save_general')).length, 0, 'changing tabs only changes the draft');
    await closeSheet(page);
  });
  await pageCheck(page, 'settings selects share one style in both themes and keep native keyboard selection', async () => {
    await openSettings(page, 'general');
    for (const mode of ['light', 'dark']) {
      await theme(page, mode);
      const styles = await page.locator('#mic,#source,#preset,#language,#updateChannel').evaluateAll(nodes => nodes.map(node => { const s = getComputedStyle(node); return [s.paddingLeft, s.paddingRight, s.height, s.borderRadius, s.appearance, s.backgroundColor, s.color].join('|'); }));
      assert.equal(new Set(styles).size, 1, JSON.stringify(styles));
    }
    await theme(page, 'light');
    await page.locator('#language').focus(); await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('#language').inputValue(), 'en');
    assert.equal(await page.locator('#sheetMessage').innerText(), '有未保存的修改');
    await closeSheet(page);
  });
  await pageCheck(page, 'appearance choice in settings applies at once and is shared through localStorage', async () => {
    await openSettings(page, 'general');
    for (const [choice, applied] of [['dark', 'dark'], ['light', 'light'], ['system', null]]) {
      await page.locator(`[data-theme-choice="${choice}"]`).click();
      assert.equal(await page.evaluate(() => localStorage.getItem('recorder-theme')), choice);
      assert.equal(await page.locator(`[data-theme-choice="${choice}"]`).evaluate(n => n.classList.contains('on')), true);
      if (applied) assert.equal(await page.locator('html').getAttribute('data-theme'), applied);
    }
    await page.locator('[data-theme-choice="light"]').click();
    assert.equal(await page.locator('#sheetMessage').innerText(), '', 'appearance applies immediately and is not a pending edit');
    await closeSheet(page);
  });
  await pageCheck(page, 'settings body scrolls independently; footer stays visible at minimum size in both themes', async () => {
    for (const mode of ['light', 'dark']) {
      await theme(page, mode); await openSettings(page, 'general');
      await unchangedBounds(page, '.sheet-foot', async () => {
        const metrics = await page.locator('#wizardBody').evaluate(node => { node.scrollTop = node.scrollHeight; return { scroll: node.scrollTop, height: node.clientHeight }; });
        assert.ok(metrics.scroll > 0 && metrics.height > 60, 'settings body must scroll');
      });
      await assertInsideViewport(page, '.sheet-foot'); await assertInsideViewport(page, '#wizardCancel');
      await page.locator('#language').selectOption('ja');
      await assertInsideViewport(page, '#wizardNext');
      await noHorizontalOverflow(page);
      assert.ok(await page.locator('#sheet').evaluate(n => n.scrollWidth <= n.clientWidth + 1));
      await screen(page, `settings-general-scrolled-${mode}-720x600`);
      await closeSheet(page);
    }
    await theme(page, 'light');
  });
  await pageCheck(page, 'saving the game tab sends only game fields; saving the general tab sends only shared fields; the key follows a successful save', async () => {
    await openSettings(page, 'game');
    await page.locator('#game').fill('改名后的示例游戏');
    await page.locator('#wizardNext').click();
    await page.waitForFunction(() => document.querySelector('#wizardCancel').textContent === '关闭');
    const game = (await calls(page, 'save_preset')).at(-1);
    assert.equal(game.args[1], 'synthetic-one', 'game settings edit the current game');
    assert.deepEqual(Object.keys(game.args[0]).filter(key => !GAME_PAYLOAD_KEYS.includes(key)), [], JSON.stringify(game.args[0]));
    assert.equal(game.args[0].name, '改名后的示例游戏'); assert.equal(game.args[0].window, 'synthetic-window');
    assert.deepEqual(game.args[0].game_hotword_files, []);
    assert.equal((await calls(page, 'save_general')).length, 0);
    assert.equal(await sheet(page).isVisible(), true, 'saving keeps the settings open');
    await page.locator('#tabGeneral').click();
    await page.locator('#language').selectOption('en'); await page.locator('#cloudKey').fill('synthetic-new-key');
    await page.evaluate(() => { window.__syntheticFixture.saveFailure = '合成测试：保存失败。'; });
    await page.locator('#wizardNext').click();
    await page.waitForFunction(() => document.querySelector('#wizardError').textContent.includes('合成测试：保存失败。'));
    assert.equal((await calls(page, 'save_cloud_key')).length, 0, 'no key is stored when settings were not saved');
    assert.equal(await page.locator('#cloudKey').inputValue(), 'synthetic-new-key', 'a failed save keeps the draft');
    await page.evaluate(() => { window.__syntheticFixture.saveFailure = ''; });
    await page.locator('#wizardNext').click();
    await page.waitForFunction(() => document.querySelector('#wizardCancel').textContent === '关闭');
    const general = (await calls(page, 'save_general')).at(-1);
    assert.deepEqual(Object.keys(general.args[0]).filter(key => !GENERAL_PAYLOAD_KEYS.includes(key)), [], JSON.stringify(general.args[0]));
    assert.equal(general.args[0].language, 'en'); assert.deepEqual(general.args[0].general_hotword_files.map(file => file.id), ['synthetic-reference']);
    const order = await page.evaluate(() => window.__syntheticFixture.calls.map(call => call.method).filter(name => ['save_general', 'save_cloud_key'].includes(name)));
    assert.deepEqual(order.slice(-2), ['save_general', 'save_cloud_key'], 'the key is saved only after the settings were saved');
    assert.deepEqual((await calls(page, 'save_cloud_key')).at(-1).args, ['synthetic-new-key']);
    assert.equal(await page.locator('#cloudKey').inputValue(), '');
    await closeSheet(page);
  });
  await page.close();
  // The 录制范围 / display choice: whole-display recording keeps its display with the shared settings.
  await check('whole-display recording: the display is a shared choice in 通用 and a changed display is saved', async () => {
    const state = snapshot({ device_inventory: { id: 'synthetic-displays', state: 'succeeded' } });
    Object.assign(state.config, { source: '整个显示器', record_inputs: false });
    state.devices.monitor = [{ itemName: '示例显示器（合成测试）', itemValue: 'synthetic-display', itemEnabled: true }, { itemName: '第二显示器（合成测试）', itemValue: 'synthetic-display-2', itemEnabled: true }];
    const p = await mainPage(context, origin, state);
    try {
      await openSettings(p, 'game');
      assert.equal(await p.locator('#target').isVisible(), false, 'the game page offers no display choice');
      assert.equal(await p.locator('#targetMonitorNote').isVisible(), true);
      assert.equal(await p.locator('#refreshDevices').isVisible(), true);
      await closeSheet(p); await openSettings(p, 'general');
      assert.equal(await p.locator('#monitor').isVisible(), true);
      await p.locator('#monitor').selectOption('synthetic-display-2');
      assert.equal(await p.locator('#sheetMessage').innerText(), '有未保存的修改');
      await p.locator('#wizardNext').click();
      await p.waitForFunction(() => document.querySelector('#wizardCancel').textContent === '关闭' || !document.querySelector('#wizardError').classList.contains('hidden'));
      const saved = [...(await calls(p, 'save_preset')).map(call => call.args[0].monitor), ...(await calls(p, 'save_general')).map(call => call.args[0].monitor)];
      assert.ok(saved.includes('synthetic-display-2'), `the changed display reaches a save call; save_preset payload keys: ${JSON.stringify((await calls(p, 'save_preset')).map(call => Object.keys(call.args[0])))}, save_general calls: ${(await calls(p, 'save_general')).length}, sheet message after save: ${JSON.stringify(await p.locator('#sheetMessage').innerText())}`);
    } finally { await p.close(); }
  });
}

// ---------------------------------------------------------------- new game wizard ('new': 游戏与窗口 → 保存位置)
async function newGameChecks(context, origin) {
  const page = await mainPage(context, origin);
  await pageCheck(page, 'new game has two steps; detected windows require no manual refresh; polling keeps focus', async () => {
    await clickGame(page, '[data-game-add]'); await sheet(page).waitFor({ state: 'visible' });
    assert.equal(await page.locator('#sheetTitle').innerText(), '新建游戏');
    assert.deepEqual(await stepLabels(page), [{ text: '游戏与窗口', on: true }, { text: '保存位置', on: false }]);
    assert.equal(await page.locator('#sheetTabs').isVisible(), false); assert.equal(await page.locator('#gameSubtabs').isVisible(), false);
    assert.equal(await page.locator('#panelGame').isVisible(), true); assert.equal(await page.locator('#panelGeneral').isVisible(), false);
    assert.equal(await page.locator('#panelMethod').isVisible(), false, 'the recording method is only part of the first launch');
    assert.equal(await page.locator('[data-in="game-vault"]').isVisible(), false);
    assert.equal(await page.locator('#game').inputValue(), '');
    assert.equal(await page.locator('#target option[value="synthetic-window"]').count(), 1);
    assert.equal((await calls(page, 'refresh_devices')).length, 0);
    assert.equal(await page.evaluate(() => store.draft.mic), 'synthetic-mic', 'a new game reuses the shared microphone');
    assert.equal(await page.evaluate(() => store.draft.transcription_provider), 'qwen', 'a new game reuses the shared transcription');
    assert.equal(await page.locator('#gameHotwordFiles .chip').count(), 0, 'a new game starts without game vocabulary');
    assert.equal(await page.locator('#wizardBack').isVisible(), false); assert.equal(await page.locator('#wizardNext').innerText(), '下一步');
    await page.locator('#game').fill('未保存的合成预设');
    const polls = await page.evaluate(() => window.__syntheticFixture.polls);
    await page.waitForFunction(before => window.__syntheticFixture.polls > before, polls);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'game', 'polling preserves the name caret');
    await page.locator('#target').focus();
    const laterPolls = await page.evaluate(() => window.__syntheticFixture.polls);
    await page.waitForFunction(before => window.__syntheticFixture.polls > before, laterPolls);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'target', 'polling does not steal focus back to the name field');
    await screen(page, 'new-game-light-720x600');
    await page.locator('#wizardNext').click();
    assert.equal(await page.locator('#wizardError').innerText(), '请选择游戏窗口。'); assert.equal((await stepLabels(page))[0].on, true);
    await page.locator('#target').selectOption('synthetic-window');
    await page.locator('#wizardNext').click();
    assert.deepEqual(await stepLabels(page), [{ text: '游戏与窗口', on: false }, { text: '保存位置', on: true }]);
    for (const field of ['game-name', 'game-window', 'game-vocab', 'game-manual']) assert.equal(await page.locator(`[data-in="${field}"]`).isVisible(), false, field);
    assert.equal(await page.locator('#vault').inputValue(), 'D:\\synthetic-only\\未保存的合成预设', 'the default location is 总库\\游戏名');
    assert.equal(await page.locator('#wizardNext').innerText(), '创建游戏'); assert.equal(await page.locator('#wizardBack').isVisible(), true);
    await screen(page, 'new-game-location-light-720x600');
    await page.locator('#wizardBack').click(); assert.equal(await page.locator('#game').inputValue(), '未保存的合成预设');
    await page.locator('#wizardCancel').click(); await sheet(page).waitFor({ state: 'hidden' });
    assert.equal((await calls(page, 'save_preset')).length, 0);
    assert.equal(await page.locator('#gameTabs .g.on').innerText(), snapshot().config.game);
  });
  await pageCheck(page, 'creating a game saves only game fields as a new preset', async () => {
    await clickGame(page, '[data-game-add]'); await sheet(page).waitFor({ state: 'visible' });
    await page.locator('#game').fill('合成新游戏'); await page.locator('#target').selectOption('synthetic-window');
    await page.locator('#wizardNext').click(); await page.locator('#chooseVault').click();
    assert.equal(await page.locator('#vault').inputValue(), 'D:\\synthetic-only\\chosen-folder');
    await page.locator('#wizardNext').click(); await sheet(page).waitFor({ state: 'hidden' });
    const saved = (await calls(page, 'save_preset')).at(-1);
    assert.equal(saved.args[1], null, 'a new game never overwrites an existing preset');
    assert.deepEqual(Object.keys(saved.args[0]).filter(key => !GAME_PAYLOAD_KEYS.includes(key)), [], JSON.stringify(saved.args[0]));
    assert.equal(saved.args[0].vault, 'D:\\synthetic-only\\chosen-folder');
    assert.equal((await calls(page, 'save_cloud_key')).length, 0);
  });
  await page.close();
}

// ---------------------------------------------------------------- first launch ('first': 记录方法 → 设备与转写 → 游戏与窗口 → 保存位置)
function firstSnapshot(overrides = {}) {
  const state = snapshot({ presets: [], active_preset_id: null, sessions: [], background_jobs: [], capabilities: { cloud_key: false },
    readiness: { ready: false, checking: false, errors: [{ message: '请先完成设置' }] },
    default_vault: { path: 'D:\\synthetic-only\\think-aloud-database', requires_confirmation: true, is_directory: true }, ...overrides });
  state.config = { configured: false, game: '', vault: '', hotword_files: [], general_hotword_files: [], game_hotword_files: [], transcription_provider: '' };
  return state;
}
async function firstUseChecks(context, origin) {
  const page = await mainPage(context, origin, firstSnapshot());
  await sheet(page).waitFor({ state: 'visible' });
  await check('first launch automatically opens the four-step setup, starting with the recording method', async () => {
    assert.equal(await page.locator('#sheetTitle').innerText(), '开始使用');
    assert.deepEqual(await stepLabels(page), [{ text: '记录方法', on: true }, { text: '设备与转写', on: false }, { text: '游戏与窗口', on: false }, { text: '保存位置', on: false }]);
    assert.equal(await page.locator('#sheetTabs').isVisible(), false);
    assert.equal(await page.locator('.method-card:visible').count(), 4);
    assert.ok((await box(page, '#methodContent .method-lead')).y < (await box(page, '#methodContent .method-grid')).y, 'core method precedes all examples and supporting copy');
    assert.equal(await page.locator('#wizardNext').innerText(), '开始设置'); assert.equal(await page.locator('#wizardBack').isVisible(), false);
    await screen(page, 'first-method-light-720x600');
  });
  await check('device and transcription step: shared settings only, validated before moving on', async () => {
    await page.locator('#wizardNext').click();
    assert.equal((await stepLabels(page))[1].on, true);
    assert.equal(await page.locator('#panelGeneral').isVisible(), true); assert.equal(await page.locator('#panelGame').isVisible(), false);
    for (const id of ['#themeChoice', '#libraryRoot', '#updateGroup', '#methodLink']) assert.equal(await page.locator(id).isVisible(), false, `${id} belongs to 设置 only`);
    assert.equal(await page.locator('#mic').isVisible(), true);
    await page.locator('#wizardNext').click();
    assert.equal(await page.locator('#wizardError').innerText(), '请选择麦克风。'); assert.equal((await stepLabels(page))[1].on, true);
    await page.locator('#mic').selectOption('synthetic-mic');
    assert.equal(await page.locator('#providerLocal').getAttribute('aria-selected'), 'true', 'local transcription is the default; nothing is uploaded unless chosen');
    await page.locator('#providerQwen').click(); await page.locator('#cloudKey').fill('synthetic-first-key');
    await screen(page, 'first-devices-light-720x600');
    await page.locator('#wizardNext').click();
    assert.equal((await stepLabels(page))[2].on, true);
  });
  await check('first-run setup visibly selects the bundled UI/UX words; preview is read-only and removable', async () => {
    await page.locator('#wizardBack').click(); // the shared vocabulary sits on 设备与转写
    const chip = page.locator('[data-view-vocabulary="bundled-uiux-browser-fixture"]');
    assert.equal(await chip.isVisible(), true, 'the bundled vocabulary is visible in the setup');
    await chip.click(); await page.locator('#actionDialog[open]').waitFor();
    assert.equal(await page.locator('.vocabulary-words li').count(), bundledWords.length);
    assert.match(await page.locator('#actionBody').innerText(), /心智模型/);
    assert.equal(await page.locator('#actionBody input,#actionBody textarea,#actionBody [contenteditable]').count(), 0, 'preview is read-only');
    assert.equal((await calls(page, 'save_preset')).length, 0);
    await screen(page, 'first-vocabulary-preview-light-720x600');
    await page.locator('#actionFooter button').first().click();
    assert.equal(await sheet(page).isVisible(), true, 'closing the preview returns to the setup');
  });
  await check('first-run setup presents the bundled UI/UX words as shared vocabulary, not as this game\'s', async () => {
    const field = await page.locator('[data-view-vocabulary="bundled-uiux-browser-fixture"]').evaluate(node => {
      const container = node.closest('[data-in]'); return { field: container?.dataset.in, label: container?.querySelector('label')?.textContent, hint: container?.querySelector('.hint')?.textContent };
    });
    assert.equal(field.field, 'general-vocab', `bundled UI/UX vocabulary is listed under ${JSON.stringify(field)}`);
    await page.locator('#wizardNext').click(); assert.equal((await stepLabels(page))[2].on, true);
  });
  await check('game step validates the name and window; the location step requires confirming an existing library', async () => {
    await page.locator('#wizardNext').click();
    assert.equal(await page.locator('#wizardError').innerText(), '请填写游戏名称。');
    await page.locator('#game').fill('首次合成游戏'); await page.locator('#target').selectOption('synthetic-window');
    await page.locator('#wizardNext').click();
    assert.equal((await stepLabels(page))[3].on, true);
    assert.equal(await page.locator('#vault').inputValue(), 'D:\\synthetic-only\\think-aloud-database');
    assert.equal(await page.locator('#wizardNext').innerText(), '开始使用');
    assert.equal(await page.locator('#reuseVaultNotice').isVisible(), true);
    assert.match(await page.locator('#reuseVaultMessage').innerText(), /发现已有同名资料库/);
    assert.equal(await page.locator('#wizardNext').isDisabled(), true, 'an existing library is never reused silently');
    await screen(page, 'first-location-light-720x600');
    await page.locator('#reuseVault').click();
    assert.equal(await page.locator('#wizardNext').isEnabled(), true);
    assert.match(await page.locator('#reuseVaultMessage').innerText(), /将使用已有资料库/);
  });
  await check('finishing saves the full first preset, then the key; a failed save stores no key', async () => {
    await page.evaluate(() => { window.__syntheticFixture.saveFailure = '合成测试：首次保存失败。'; });
    await page.locator('#wizardNext').click();
    await page.waitForFunction(() => document.querySelector('#wizardError').textContent.includes('合成测试：首次保存失败。'));
    assert.equal((await calls(page, 'save_cloud_key')).length, 0); assert.equal(await sheet(page).isVisible(), true);
    await page.evaluate(() => { window.__syntheticFixture.saveFailure = ''; });
    await page.locator('#wizardNext').click(); await sheet(page).waitFor({ state: 'hidden' });
    const saved = (await calls(page, 'save_preset')).at(-1);
    assert.equal(saved.args[1], null);
    assert.equal(saved.args[0].game, '首次合成游戏'); assert.equal(saved.args[0].mic, 'synthetic-mic'); assert.equal(saved.args[0].transcription_provider, 'qwen');
    assert.equal(saved.args[0].confirmed_vault, 'D:\\synthetic-only\\think-aloud-database');
    assert.deepEqual(saved.args[0].hotword_files.map(file => file.id), ['bundled-uiux-browser-fixture']);
    assert.deepEqual(saved.args[0].general_hotword_files.map(file => file.id), ['bundled-uiux-browser-fixture'], 'the first setup saves its shared vocabulary as general');
    const order = await page.evaluate(() => window.__syntheticFixture.calls.map(call => call.method).filter(name => ['save_preset', 'save_cloud_key'].includes(name)));
    assert.deepEqual(order, ['save_preset', 'save_preset', 'save_cloud_key']);
    assert.deepEqual((await calls(page, 'save_cloud_key')).at(-1).args, ['synthetic-first-key']);
  });
  await page.close();
  await check('cancelling the first launch saves nothing and leaves recording unavailable', async () => {
    const p = await mainPage(context, origin, firstSnapshot());
    try {
      await sheet(p).waitFor({ state: 'visible' });
      await p.locator('#wizardCancel').click(); await sheet(p).waitFor({ state: 'hidden' });
      assert.equal(await p.locator('#recordButton').isEnabled(), false);
      assert.equal((await calls(p, 'save_preset')).length, 0);
      assert.equal(await p.locator('#gameTabs [data-game]').count(), 0); assert.equal(await p.locator('#gameTabs [data-game-add]').count(), 1);
      // Removing the bundled vocabulary is a draft change only.
      await p.locator('#settingsButton').click(); await sheet(p).waitFor({ state: 'visible' });
      await p.locator('#wizardNext').click(); await p.locator('#mic').selectOption('synthetic-mic');
      await p.locator('[data-remove-vocabulary="bundled-uiux-browser-fixture"]').click();
      assert.equal(await p.locator('[data-view-vocabulary="bundled-uiux-browser-fixture"]').count(), 0);
      assert.equal(await p.evaluate(() => store.draft.hotword_files.length), 0);
      await p.locator('#wizardCancel').click(); await sheet(p).waitFor({ state: 'hidden' });
      assert.equal((await calls(p, 'save_preset')).length, 0);
      await p.locator('#settingsButton').click(); await sheet(p).waitFor({ state: 'visible' });
      assert.equal(await p.locator('#sheetTitle').innerText(), '开始使用', 'the gear reopens the first setup while no game exists');
    } finally { await p.close(); }
  });
}

// ---------------------------------------------------------------- device reading during the first launch
async function deviceSetupChecks(context, origin) {
  const detected = {
    devices: {
      window: [...snapshot().devices.window, { itemName: '另一个窗口（合成测试）', itemValue: 'synthetic-other-window', itemEnabled: true }],
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
  for (const scenario of [{ theme: 'light' }, { theme: 'dark' }]) {
    const page = await mainPage(context, origin, firstSnapshot(clone(detected)), scenario.theme);
    await sheet(page).waitFor({ state: 'visible' });
    await check(`explicit device refresh changes only the draft and keeps manual choices (${scenario.theme})`, async () => {
      const original = await page.evaluate(() => JSON.stringify(window.__syntheticFixture.snapshot.config));
      await page.evaluate(value => { window.__syntheticFixture.refreshSnapshot = value; }, detected);
      await page.locator('#wizardNext').click(); // → 设备与转写
      await page.waitForFunction(() => document.querySelector('#mic option[value="default"]'));
      await page.locator('#mic').selectOption('synthetic-physical-mic'); await page.locator('#providerLocal').click();
      await page.locator('#wizardNext').click(); // → 游戏与窗口
      await page.locator('#game').fill('合成 OBS 初始化验证');
      await page.locator('#target').selectOption('synthetic-other-window');
      const before = (await calls(page, 'refresh_device_inventory')).length;
      await page.locator('#refreshDevices').click();
      await page.waitForFunction(count => window.__syntheticFixture.calls.filter(call => call.method === 'refresh_device_inventory').length === count + 1 && !document.querySelector('#refreshDevices').disabled, before);
      assert.equal(await page.locator('#refreshDevices').innerText(), '刷新设备');
      assert.equal(await page.locator('#target').inputValue(), 'synthetic-other-window');
      assert.equal(await page.evaluate(() => store.draft.mic), 'synthetic-physical-mic');
      assert.equal(await page.evaluate(() => store.draft.source), '游戏窗口', 'a refresh never rewrites the chosen recording range');
      assert.match(await page.locator('#deviceFeedback').innerText(), /已识别当前选择的游戏窗口和麦克风/);
      assert.equal(await page.evaluate(() => JSON.stringify(window.__syntheticFixture.snapshot.config)), original, 'setup changes only the draft');
      assert.equal((await calls(page, 'save_preset')).length, 0);
      assert.equal((await calls(page, 'refresh_devices')).length, 0, 'reading devices never restarts the recording engine');
      await screen(page, `first-devices-refreshed-${scenario.theme}-720x600`);
      await page.locator('#wizardCancel').click();
      assert.equal((await calls(page, 'save_preset')).length, 0);
    });
    await page.close();
  }
  await check('first-run device step offers device reading feedback and a refresh', async () => {
    const page = await mainPage(context, origin, firstSnapshot({ devices: { window: [], monitor: [], mic: [] }, device_defaults: {} }));
    try {
      await sheet(page).waitFor({ state: 'visible' });
      await page.locator('#wizardNext').click(); // → 设备与转写: the microphone must be chosen here
      assert.equal(await page.locator('#mic').isVisible(), true);
      assert.deepEqual(await page.locator('#mic option').allInnerTexts(), ['请选择麦克风']);
      const visible = { refresh: await page.locator('#refreshDevices').isVisible(), feedback: await page.locator('#deviceFeedback').isVisible() };
      await screen(page, 'first-devices-empty-light-720x600');
      assert.deepEqual(visible, { refresh: true, feedback: true }, 'with no microphone listed, the step that requires one shows why and how to read devices again');
    } finally { await page.close(); }
  });
  await check('first-run whole-display recording offers the display choice on the step that requires it', async () => {
    const page = await mainPage(context, origin, firstSnapshot({ device_inventory: { id: 'synthetic-first', state: 'succeeded' } }));
    try {
      await sheet(page).waitFor({ state: 'visible' });
      await page.locator('#wizardNext').click();
      await page.locator('#mic').selectOption('synthetic-mic'); await page.locator('#providerLocal').click();
      await page.locator('#source').selectOption('整个显示器');
      await page.locator('#wizardNext').click();
      const state = { step: (await stepLabels(page)).find(item => item.on).text, error: await page.locator('#wizardError').innerText(), displaySelectVisible: await page.locator('#monitor').isVisible() };
      assert.ok(state.step !== '设备与转写' || state.displaySelectVisible, `whole-display recording blocks the step without a visible display choice: ${JSON.stringify(state)}`);
    } finally { await page.close(); }
  });
}

// ---------------------------------------------------------------- window identity inside game settings
async function windowSelectionChecks(context, origin) {
  const state = snapshot();
  const saved = 'Synthetic:OldClass:game.exe', live = 'Synthetic:NewClass:game.exe';
  const other = 'Other:OtherClass:other.exe';
  state.config.window = saved;
  state.devices.window = [
    {itemName:'示例游戏（当前窗口）',itemValue:live,itemEnabled:true},
    {itemName:'另一个游戏窗口',itemValue:other,itemEnabled:true},
  ];
  state.readiness.window_selection = {requested:saved,resolved:live,status:'matched',matched_by:'exe_title'};
  const page = await mainPage(context, origin, state);
  await openSettings(page, 'game');
  await check('saved game resolves visibly to its current identity without an unavailable placeholder', async () => {
    await page.waitForFunction(value => document.querySelector('#target').value === value, live);
    assert.match(await page.locator('#target option:checked').innerText(), /已匹配当前窗口/);
    assert.doesNotMatch(await page.locator('#target').innerText(), /当前未找到/);
    assert.equal(await page.locator('#sheetMessage').innerText(), '', 'showing the current match is not an edit');
    await screen(page, 'saved-game-unique-match');
  });
  await check('polling never replaces a manually chosen different game', async () => {
    await page.locator('#target').selectOption(other);
    await page.locator('#game').click(); await page.evaluate(() => poll());
    assert.equal(await page.locator('#target').inputValue(), other);
  });
  await check('cancel preserves the original preset and reopens with the current match', async () => {
    await page.locator('#wizardCancel').click(); await openSettings(page, 'game');
    await page.waitForFunction(value => document.querySelector('#target').value === value, live);
    assert.equal(await page.evaluate(() => window.__syntheticFixture.snapshot.config.window), saved);
    assert.equal((await calls(page, 'save_preset')).length, 0);
  });
  await check('ambiguous matches retain the saved target and never select a candidate automatically', async () => {
    await patchSnapshot(page, {device_inventory:{id:'ambiguous',state:'succeeded',window_selection:{requested:saved,resolved:null,status:'ambiguous'}},readiness:{ready:false,checking:false,errors:[{code:'WINDOW_AMBIGUOUS',step:1,message:'检测到多个匹配的游戏窗口，请重新选择。'}],
      window_selection:{requested:saved,resolved:null,status:'ambiguous'}}});
    await page.locator('#game').click(); await page.evaluate(() => poll());
    assert.equal(await page.locator('#target').inputValue(), saved);
    assert.match(await page.locator('#target option:checked').innerText(), /多个匹配/);
    await page.locator('#wizardCancel').click();
    assert.equal(await page.locator('#recordButton').isDisabled(), true);
    assert.match(await page.locator('#blockers').innerText(), /多个匹配/);
  });
  await page.close();
}

// ---------------------------------------------------------------- vocabulary preview inside settings
async function vocabularyChecks(context, origin) {
  const state = snapshot();
  Object.assign(state.config, { hotword_files: [clone(bundledVocabulary)], general_hotword_files: [clone(bundledVocabulary)] });
  for (const mode of ['light', 'dark']) {
    const page = await mainPage(context, origin, state, mode);
    await check(`general vocabulary preview scrolls inside the window and returns to the draft (${mode})`, async () => {
      await openSettings(page, 'general');
      assert.equal(await page.locator('#hotwordFiles .chip').count(), 1);
      assert.match(await page.locator('#hotwordFiles .chip').innerText(), new RegExp(`uiux-terms\\.txt\\s*${bundledWords.length}`));
      await page.locator('#hotwordFiles [data-view-vocabulary]').click(); await page.locator('#actionDialog[open]').waitFor();
      assert.equal(await page.locator('.vocabulary-words li').count(), bundledWords.length);
      await page.locator('#actionBody').evaluate(node => node.scrollTop = node.scrollHeight);
      assert.ok(await page.locator('#actionBody').evaluate(node => node.scrollTop > 0));
      await assertInsideViewport(page, '#actionDialog'); await noHorizontalOverflow(page);
      await screen(page, `vocabulary-preview-${mode}-720x600`);
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#actionDialog').evaluate(n => n.open), false);
      assert.equal(await sheet(page).isVisible(), true, 'Escape closes only the preview, not the settings');
      await page.locator('#hotwordFiles [data-remove-vocabulary]').click();
      assert.equal(await page.locator('#hotwordFiles .chip').count(), 0);
      assert.equal(await page.locator('#vocabularyCount').innerText(), '尚未选择词库');
      await closeSheet(page);
      assert.equal((await calls(page, 'save_general')).length + (await calls(page, 'save_preset')).length, 0);
    });
    await page.close();
  }
}

// ---------------------------------------------------------------- desk window (场次 / 洞察)
const deskSessions = () => [
  { id: 'd1', game: '示例游戏', created: '2026-09-22T10:30:00', duration: 3725, state: '可回看', can_review: true, test: true, path: 'D:\\synthetic-only\\think-aloud-database\\d1',
    session_name: '清河探索与初次止戈', activity_details: '清河任务 + 野外探索 + 萌宠争锋', preprocessing: { state: 'complete', kinds: { obstacle: 2, confusion: 1, suggestion: 2 } } },
  { id: 'd2', game: '示例游戏', created: '2026-09-20T09:05:00', duration: 1500, state: '可回看', can_review: true, test: true, path: 'D:\\synthetic-only\\think-aloud-database\\d2', preprocessing: { state: 'none' } },
  { id: 'd3', game: '示例游戏', created: '2026-09-05T21:00:00', duration: 640, state: '转写失败', error: '合成测试：转写失败。', can_review: false, test: true, path: 'D:\\synthetic-only\\think-aloud-database\\d3' },
  { id: 'd4', game: '示例游戏', created: '2026-08-28T19:40:00', duration: 4210, state: '可回看', can_review: true, test: true, path: 'D:\\synthetic-only\\think-aloud-database\\d4',
    preprocessing: { state: 'complete', kinds: { cost: 3, confusion: 4 }, event_titles: ['萌宠争锋', '城镇养成'] } },
  { id: 'd5', game: '示例游戏', created: '2026-08-10T14:00:00', duration: 900, state: '可回看', can_review: true, test: true, path: 'D:\\synthetic-only\\think-aloud-database\\d5',
    session_name: '短场次', preprocessing: { state: 'complete', kinds: { negative: 1 } } },
];
function deskState(overrides = {}) {
  return { tab: 'sessions', game: '示例游戏 · 合成测试', sessions: deskSessions(), busy: false, recording: false,
    background_jobs: [{ session_id: 'd2', state: 'running', detail: '合成测试：后台转写中。' }], insight: { insights: 1 }, ...overrides };
}
const deskDetails = {
  d1: { id: 'd1', state: 'complete', label: '', kinds: { obstacle: 2, confusion: 1, suggestion: 2 },
    quotes: { confusion: [{ text: '这个标记是什么意思我没看懂', at: 12.5 }], obstacle: [{ text: '找不到返回的地方只能重进', at: 30 }, { text: '背包满了又不能直接丢东西', at: 95 }], cost: [], negative: [] },
    events: [{ title: '清河任务', start: 0, end: 120 }, { title: '野外探索', start: 120, end: 300 }], insights: [{ id: 'TA-01', title: '目标明确仍有摩擦', count: 2 }] },
  d2: { id: 'd2', state: 'none', label: '这一场还没有整理结果。', kinds: {}, quotes: {}, events: [], insights: [] },
};
const deskOverview = { vault: '合成资料库', reports: [{ name: 'r.md', modified: 1, bytes: 10 }], feedback: [], tag_groups: [], tags: [], instance_tags: {}, session_labels: { d1: '0922' },
  instances: [{ session_id: 'd1', instance_id: 'i1', said_start: 30, refers_start: 28, refers_end: 31, refers_basis: 'same_time', screen: 'bag', catalog_screen: 'bag', elements: [], kind: 'obstacle', statement: '合成陈述', issue_tags: [], issue_links: [], event_id: 'e1', event_title: '清河任务' }],
  issues: [{ id: 'TA-01', title: '目标明确仍有摩擦', description: '合成议题', status: 'confirmed', support: [{ session_id: 'd1', instance_id: 'i1', reason: '合成理由' }], counter: [], children: [] }], bug_unorganized: [] };
async function deskPage(context, origin, desk = deskState(), requestedTheme = 'light', viewport = { width: 1240, height: 900 }) {
  const page = await context.newPage(); await page.setViewportSize(viewport);
  await page.addInitScript(({ desk, details, overview, requestedTheme }) => {
    localStorage.setItem('recorder-theme', requestedTheme);
    const f = window.__deskFixture = { desk, details, overview, calls: [], reads: 0 };
    const copy = value => JSON.parse(JSON.stringify(value)), ok = data => ({ ok: true, data });
    window.pywebview = { api: new Proxy({}, { get: (_, method) => async (...args) => {
      if (method === 'desk_state') { f.reads++; return ok(copy(f.desk)); }
      if (method === 'get_overview') return ok(copy(f.overview));
      if (method === 'read_report') return ok({ name: 'r.md', text: '# 合成报告', citations: [] });
      if (method === 'thumbnail') return ok('data:image/gif;base64,R0lGODlhAQABAAAAACw=');
      if (method === 'win_set_frame_color' || method === 'ready') return ok({});
      f.calls.push({ method, args });
      if (method === 'session_detail') return f.details[args[0]] ? ok(copy(f.details[args[0]])) : { ok: false, error: '合成测试：没有这一场的整理结果。' };
      if (method === 'rename_session') { f.desk.sessions.find(row => row.id === args[0]).session_name = args[1]; return ok({}); }
      if (['review_session', 'process_session', 'package_session', 'open_folder', 'open_raw', 'recover_cloud_task', 'open_review', 'win_minimize', 'win_toggle_maximize', 'win_close'].includes(method)) return ok({});
      throw new Error('Synthetic desk harness did not authorize native action: ' + String(method));
    } }) };
  }, { desk, details: deskDetails, overview: deskOverview, requestedTheme });
  await page.goto(origin + '/ui/desk.html'); await page.locator('#sessionScroll .item').first().waitFor({ state: 'attached' });
  return page;
}
const deskCalls = (page, method) => page.evaluate(name => window.__deskFixture.calls.filter(call => call.method === name).map(call => call.args), method);
const deskRows = page => page.locator('#sessionScroll .item').evaluateAll(nodes => nodes.map(n => n.dataset.session));
async function deskChecks(context, origin) {
  const page = await deskPage(context, origin);
  await check('desk lists sessions by month, newest first, with sticky month headings and the game as title', async () => {
    assert.equal(await page.locator('#deskGame').innerText(), '示例游戏 · 合成测试');
    assert.deepEqual(await page.locator('#sessionScroll .month').evaluateAll(n => n.map(x => x.textContent)), ['九月2026 · 3 场', '八月2026 · 2 场']);
    assert.deepEqual(await deskRows(page), ['d1', 'd2', 'd3', 'd4', 'd5']);
    assert.equal(await page.locator('#sessionScroll .month').first().evaluate(n => getComputedStyle(n).position), 'sticky');
    const d4 = page.locator('#sessionScroll [data-session="d4"]');
    assert.match(await d4.locator('h4').innerText(), /^未命名萌宠争锋、城镇养成/);
    assert.equal(await d4.locator('.n b').innerText(), '7', 'problem count covers the four problem kinds only');
    assert.equal(await page.locator('#sessionScroll [data-session="d1"] .n b').innerText(), '3');
    assert.equal(await page.locator('#sessionScroll [data-session="d2"] .st').innerText(), '待整理');
    assert.equal(await page.locator('#sessionScroll [data-session="d3"] .st').innerText(), '转写失败');
    assert.equal(await page.locator('#sessionScroll [data-session="d2"] .n b').count(), 0, 'unorganized sessions show no problem count');
    assert.equal(await page.locator('#deskTabSessions').getAttribute('aria-selected'), 'true');
    await noHorizontalOverflow(page);
    await screen(page, 'desk-sessions-light-1240x900');
  });
  await check('state filter chips count and filter sessions; problem-kind chips multi-select', async () => {
    assert.deepEqual(await page.locator('#stateChips .chip').evaluateAll(n => n.map(x => x.textContent)), ['全部 5', '待整理 1', '已整理 3', '失败 1']);
    await page.locator('#stateChips [data-filter="todo"]').click(); assert.deepEqual(await deskRows(page), ['d2']);
    assert.equal(await page.locator('#stateChips [data-filter="todo"]').getAttribute('aria-pressed'), 'true');
    await page.locator('#stateChips [data-filter="done"]').click(); assert.deepEqual(await deskRows(page), ['d1', 'd4', 'd5']);
    await page.locator('#stateChips [data-filter="failed"]').click(); assert.deepEqual(await deskRows(page), ['d3']);
    await page.locator('#stateChips [data-filter="all"]').click(); assert.deepEqual(await deskRows(page), ['d1', 'd2', 'd3', 'd4', 'd5']);
    await page.locator('#kindChips [data-kind="obstacle"]').click(); assert.deepEqual(await deskRows(page), ['d1']);
    await page.locator('#kindChips [data-kind="cost"]').click(); assert.deepEqual(await deskRows(page), ['d1', 'd4']);
    assert.deepEqual(await page.locator('#kindChips [aria-pressed="true"]').evaluateAll(n => n.map(b => b.dataset.kind)), ['obstacle', 'cost']);
    await page.locator('#stateChips [data-filter="todo"]').click(); assert.match(await page.locator('#sessionScroll').innerText(), /没有符合筛选的场次/);
    await page.locator('#stateChips [data-filter="all"]').click(); await page.locator('#kindChips [data-kind="obstacle"]').click(); await page.locator('#kindChips [data-kind="cost"]').click();
    assert.deepEqual(await deskRows(page), ['d1', 'd2', 'd3', 'd4', 'd5']);
  });
  await check('sorting by problems drops month headings; keyboard selection works; search is behind an icon', async () => {
    await page.locator('#sortSelect').focus(); await page.keyboard.press('ArrowDown');
    assert.equal(await page.locator('#sortSelect').inputValue(), 'problems');
    assert.deepEqual((await deskRows(page)).slice(0, 3), ['d4', 'd1', 'd5']);
    assert.equal(await page.locator('#sessionScroll .month').count(), 0);
    await page.locator('#sortSelect').selectOption('time'); assert.equal(await page.locator('#sessionScroll .month').count(), 2);
    assert.equal(await page.locator('#searchInput').isVisible(), false);
    await page.locator('#searchToggle').click(); assert.equal(await page.evaluate(() => document.activeElement.id), 'searchInput');
    await page.locator('#searchInput').fill('萌宠'); assert.deepEqual(await deskRows(page), ['d1', 'd4']);
    await page.locator('#searchToggle').click(); assert.equal(await page.locator('#searchInput').isVisible(), false);
    assert.deepEqual(await deskRows(page), ['d1', 'd2', 'd3', 'd4', 'd5'], 'closing search clears it');
  });
  await check('the first session opens by default; its detail groups quotes, problems, insights and activities', async () => {
    await page.locator('#sessionDetail .kq').first().waitFor();
    assert.deepEqual(await deskCalls(page, 'session_detail'), [['d1']]);
    assert.equal(await page.locator('#sessionScroll [data-session="d1"]').evaluate(n => n.classList.contains('sel')), true);
    assert.equal(await page.locator('#sessionDetail h1').innerText(), '清河探索与初次止戈');
    assert.match(await page.locator('#sessionDetail .d-date').innerText(), /2026 年 9 月 22 日 周二 · 10:30 开始 · 时长 1:02:05/);
    assert.deepEqual(await page.locator('#sessionDetail .kq h5').evaluateAll(n => n.map(x => x.textContent)), ['困惑1 条', '阻碍2 条']);
    assert.deepEqual(await page.locator('#sessionDetail .dist li b').allInnerTexts(), ['1', '2', '0', '0']);
    assert.match(await page.locator('#sessionDetail .side-sec .note').first().innerText(), /另有 2 条/);
    assert.deepEqual(await page.locator('#sessionDetail .ins li').evaluateAll(n => n.map(x => x.textContent)), ['目标明确仍有摩擦2']);
    assert.equal(await page.locator('#sessionDetail .evs li').count(), 2);
    assert.equal(await page.locator('[data-act="handoff"]').count(), 0, 'organized sessions need no hand-off');
    await page.locator('#sessionDetail [data-at="30"]').click();
    assert.deepEqual((await deskCalls(page, 'open_review')).at(-1), ['d1', 30]);
    await screen(page, 'desk-detail-light-1240x900');
  });
  await check('detail actions call the matching bridge methods; rename, process and recover confirm first', async () => {
    for (const [act, method] of [['review', 'review_session'], ['folder', 'open_folder'], ['raw', 'open_raw'], ['export', 'package_session']]) {
      await page.locator(`#sessionDetail [data-act="${act}"]`).click();
      await page.waitForFunction(name => window.__deskFixture.calls.some(call => call.method === name), method);
      assert.deepEqual((await deskCalls(page, method)).at(-1), ['d1'], act);
    }
    await page.locator('[data-act="process"]').click(); await page.locator('#deskDialog[open]').waitFor();
    assert.match(await page.locator('#deskDialogBody').innerText(), /会上传这一场的麦克风录音/);
    assert.equal((await deskCalls(page, 'process_session')).length, 0, 'nothing starts before confirmation');
    await page.locator('#deskDialogFoot .btn.solid').click(); await page.waitForFunction(() => !document.querySelector('#deskDialog').open);
    assert.deepEqual(await deskCalls(page, 'process_session'), [['d1']]);
    await page.locator('[data-act="rename"]').click(); await page.locator('#deskDialog[open]').waitFor();
    assert.equal(await page.locator('#renameInput').inputValue(), '清河探索与初次止戈');
    await page.locator('#deskDialogFoot .btn', { hasText: '取消' }).click(); assert.equal((await deskCalls(page, 'rename_session')).length, 0);
    await page.locator('[data-act="rename"]').click(); await page.locator('#renameInput').fill('合成新名称');
    await page.locator('#deskDialogFoot .btn.solid').click(); await page.waitForFunction(() => !document.querySelector('#deskDialog').open);
    assert.deepEqual(await deskCalls(page, 'rename_session'), [['d1', '合成新名称']]);
    await page.waitForFunction(() => document.querySelector('#sessionScroll [data-session="d1"] h4').textContent.includes('合成新名称'));
    await page.locator('[data-act="recover"]').click(); await page.locator('#deskDialog[open]').waitFor();
    await page.locator('#deskDialogFoot .btn.solid').click();
    assert.equal(await page.locator('#deskDialog').evaluate(n => n.open), true, 'an empty task id keeps the dialog open');
    assert.equal((await deskCalls(page, 'recover_cloud_task')).length, 0);
    await page.locator('#recoverInput').fill('synthetic-task-123'); await page.locator('#deskDialogFoot .btn.solid').click();
    await page.waitForFunction(() => !document.querySelector('#deskDialog').open);
    assert.deepEqual(await deskCalls(page, 'recover_cloud_task'), [['d1', 'synthetic-task-123']]);
  });
  await check('an unorganized session offers the hand-off; while it is processing, only safe actions stay enabled', async () => {
    await page.locator('#sessionScroll [data-session="d2"]').click(); await page.locator('#sessionDetail [data-act="handoff"]').waitFor();
    assert.deepEqual((await deskCalls(page, 'session_detail')).at(-1), ['d2']);
    assert.match(await page.locator('#sessionDetail h1').innerText(), /^未命名09:05 开始的记录/);
    assert.match(await page.locator('#sessionDetail').innerText(), /合成测试：后台转写中。/);
    const enabled = await page.locator('#sessionDetail [data-act]').evaluateAll(nodes => Object.fromEntries(nodes.map(n => [n.dataset.act, !n.disabled])));
    assert.deepEqual(enabled, { review: true, handoff: true, rename: true, process: false, folder: true, export: false, raw: true, recover: false });
    await page.locator('[data-act="handoff"]').click(); await page.waitForFunction(() => document.querySelector('#deskToast').classList.contains('show'));
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    assert.match(copied, /场次文件夹：D:\\synthetic-only\\think-aloud-database\\d2/); assert.match(copied, /只整理这一场/);
    await screen(page, 'desk-unorganized-light-1240x900');
  });
  await check('a failed session without a playable recording cannot be reviewed; its other actions stay available', async () => {
    await page.locator('#sessionScroll [data-session="d3"]').click(); await page.waitForFunction(() => document.querySelector('#sessionDetail h1')?.textContent.includes('21:00'));
    assert.match(await page.locator('#sessionDetail').innerText(), /合成测试：转写失败。/);
    const enabled = await page.locator('#sessionDetail [data-act]').evaluateAll(nodes => Object.fromEntries(nodes.map(n => [n.dataset.act, !n.disabled])));
    assert.deepEqual(enabled, { review: false, handoff: true, rename: true, process: true, folder: true, export: true, raw: true, recover: true });
  });
  await check('while recording, processing, export and cloud recovery lock on every session', async () => {
    await page.locator('#sessionScroll [data-session="d1"]').click(); await page.locator('#sessionDetail .kq').first().waitFor();
    await page.evaluate(() => { window.__deskFixture.desk.busy = true; window.__deskFixture.desk.recording = true; });
    await page.waitForFunction(() => document.querySelector('#sessionDetail [data-act="process"]')?.disabled === true, null, { timeout: 8000 });
    const enabled = await page.locator('#sessionDetail [data-act]').evaluateAll(nodes => Object.fromEntries(nodes.map(n => [n.dataset.act, !n.disabled])));
    assert.deepEqual(enabled, { review: true, rename: true, process: false, folder: true, export: false, raw: true, recover: false });
    await page.evaluate(() => { window.__deskFixture.desk.busy = false; window.__deskFixture.desk.recording = false; });
    await page.waitForFunction(() => document.querySelector('#sessionDetail [data-act="process"]')?.disabled === false, null, { timeout: 8000 });
  });
  await check('insight links in a session open the insight tab; the tabs switch back', async () => {
    await page.locator('#sessionDetail .ins li[data-issue="TA-01"]').click();
    await page.waitForFunction(() => !document.querySelector('#paneInsight').classList.contains('hidden'));
    assert.equal(await page.locator('#paneSessions').isVisible(), false);
    assert.equal(await page.locator('#deskTabInsight').getAttribute('aria-selected'), 'true');
    await screen(page, 'desk-insight-light-1240x900');
    await page.locator('#deskTabSessions').click();
    assert.equal(await page.locator('#paneSessions').isVisible(), true); assert.equal(await page.locator('#deskTabSessions').getAttribute('aria-selected'), 'true');
    await page.locator('#deskTabInsight').click(); assert.equal(await page.locator('#paneInsight').isVisible(), true);
    await page.locator('#deskTabSessions').click();
  });
  await check('desk window buttons hand off to the native frame', async () => {
    for (const name of ['min', 'max', 'close']) await page.locator(`.desk-head [data-win="${name}"]`).click();
    assert.deepEqual((await page.evaluate(() => window.__deskFixture.calls.map(call => call.method))).filter(name => name.startsWith('win_')), ['win_minimize', 'win_toggle_maximize', 'win_close']);
  });
  await page.close();
  await check('desk opens on the requested tab, follows the shared dark theme and fits its 960×600 minimum', async () => {
    const p = await deskPage(context, origin, deskState({ tab: 'insight' }), 'dark', { width: 960, height: 600 });
    try {
      await p.waitForFunction(() => !document.querySelector('#paneInsight').classList.contains('hidden'));
      assert.equal(await p.locator('html').getAttribute('data-theme'), 'dark');
      await noHorizontalOverflow(p); await screen(p, 'desk-insight-dark-960x600');
      await p.locator('#deskTabSessions').click(); await p.locator('#sessionDetail .kq').first().waitFor();
      await noHorizontalOverflow(p);
      for (const selector of ['#sessionScroll', '#sessionDetail', '.desk-head [data-win="close"]']) await assertInsideViewport(p, selector);
      await screen(p, 'desk-sessions-dark-960x600');
    } finally { await p.close(); }
  });
}

async function reviewChecks(context, origin) {
  const page = await context.newPage(); await page.setViewportSize({ width: 1240, height: 900 }); await bridge(page);
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

async function main() {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true, channel: process.env.TAR_UI_CHANNEL || 'msedge' });
  try {
    if(!process.env.TAR_UI_ONLY||process.env.TAR_UI_ONLY==='review')await makeSyntheticVideo(browser, origin);
    const context = await browser.newContext({ viewport: MAIN, deviceScaleFactor: 1 });
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin });
    context.setDefaultTimeout(6000); context.setDefaultNavigationTimeout(10000);
    await context.route('**/*', route => {
      if (route.request().url().startsWith(origin + '/')) return route.continue();
      evidence.errors.push(`Blocked non-fixture request: ${route.request().url()}`); return route.abort();
    });
    context.on('page', page => page.on('pageerror', error => evidence.errors.push(error.message)));
    for (const [name, task] of [['recorder scenarios', homeChecks], ['settings scenarios', settingsChecks], ['new game scenarios', newGameChecks], ['first launch scenario', firstUseChecks], ['device setup scenarios', deviceSetupChecks], ['window scenarios', windowSelectionChecks], ['vocabulary scenarios', vocabularyChecks], ['update scenarios', updateChecks], ['desk scenarios', deskChecks], ['review scenarios', reviewChecks]]) {
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

// ---------------------------------------------------------------- version and updates (设置 → 通用 → 版本与更新)
async function updateChecks(context,origin){
  const page=await mainPage(context,origin);await page.waitForFunction(()=>!document.querySelector('#recordButton').disabled);
  const base={current_version:'0.6.0-preview.3',state:'idle',latest_version:null,include_prerelease:false,can_install:false,install_blockers:[],review_count:0};
  const updates=async value=>{await patchSnapshot(page,{updates:{...base,...value},closing:false});await page.evaluate(()=>poll());};
  const openUpdates=async()=>{await openSettings(page,'general');await page.locator('#updateGroup').scrollIntoViewIfNeeded();};
  await check('updates absent on older bridge: safe panel, no automatic requests and stable main CTA',async()=>{
    const initial=await box(page,'#recordButton');await openUpdates();
    assert.equal(await page.locator('#updateCheck').isDisabled(),true);assert.equal(await page.locator('#updateCurrent').textContent(),'尚未获取');
    assert.equal((await calls(page,'update_action')).length,0);await page.keyboard.press('Escape');await sheet(page).waitFor({state:'hidden'});
    const after=await box(page,'#recordButton');assert.deepEqual(after,initial);
    assert.equal(await page.locator('#settingsButton').evaluate(n=>n.classList.contains('badge')),false);
    await updates({});assert.equal(await page.locator('#updateCurrent').textContent(),'v0.6.0-preview.3');
    assert.deepEqual(await box(page,'#recordButton'),initial);await screen(page,'updates-home-720x600');
  });
  await check('startup availability is a badge on the gear, the 通用 tab and the update heading, without a modal or capture interruption',async()=>{
    await updates({state:'available',latest_version:'0.7.0'});
    assert.equal(await page.locator('#settingsButton').evaluate(n=>n.classList.contains('badge')),true);
    assert.equal(await page.locator('#settingsButton').getAttribute('title'),'设置 · 有新版本 v0.7.0');
    assert.equal(await page.locator('#settingsButton').getAttribute('aria-label'),'设置 · 有新版本 v0.7.0');
    assert.equal(await page.locator('#tabGeneral').evaluate(n=>n.classList.contains('badge')),true);
    assert.equal(await page.locator('#updateGroup').evaluate(n=>n.classList.contains('badge-text')),true);
    assert.equal(await sheet(page).isVisible(),false);
    assert.equal(await page.locator('#recordButton').isEnabled(),true);
    assert.equal((await calls(page,'update_action')).length,0);
    await screen(page,'updates-startup-available');await updates({});
    assert.equal(await page.locator('#settingsButton').evaluate(n=>n.classList.contains('badge')),false);
    assert.equal(await page.locator('#settingsButton').getAttribute('title'),'设置');
  });
  await check('stable is default and opening the panel does not check; explicit check and cancel use bridge',async()=>{
    await openUpdates();assert.equal(await page.locator('#updateChannel').inputValue(),'stable');
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
    assert.equal(await page.evaluate(()=>window.__badRelease),undefined);
    await page.locator('#updateRelease').click();assert.equal((await calls(page,'update_action')).at(-1).args[0].action,'open_release');
    await screen(page,'updates-available-light');
  });
  await check('switching channel is explicit, requires a fresh check and never saves recording presets',async()=>{
    const count=(await calls(page,'update_action')).length;
    await page.locator('#updateChannel').selectOption('preview');assert.equal((await calls(page,'update_action')).length,count);
    assert.equal(await page.locator('#updateDownload').isDisabled(),true);
    assert.equal(await page.locator('#sheetMessage').innerText(),'','the channel is not a pending settings edit');
    await page.evaluate(()=>poll());assert.equal(await page.locator('#updateChannel').inputValue(),'preview');
    await page.locator('#updateCheck').click();assert.deepEqual((await calls(page,'update_action')).at(-1).args,[{action:'check',include_prerelease:true}]);
    assert.equal((await calls(page,'save_preset')).length+(await calls(page,'save_general')).length,0);await page.locator('#updateCancel').click();
  });
  await check('download progress is determinate when sized, cancellable and leaves recording available',async()=>{
    await updates({state:'available',latest_version:'0.7.0',total_bytes:251658240,notes:'改进时间轴拖动与操作记录的可读性。'});
    await page.locator('#updateDownload').click();await page.waitForFunction(()=>document.querySelector('#updateStatus').textContent==='正在下载更新');
    assert.equal((await calls(page,'update_action')).at(-1).args[0].action,'download');
    await updates({state:'downloading',latest_version:'0.7.0',downloaded_bytes:100663296,total_bytes:251658240,notes:'改进时间轴拖动与操作记录的可读性。'});
    assert.equal(await page.locator('#updateProgress').evaluate(n=>n.value),40);
    assert.equal(await page.locator('#recordButton').isDisabled(),false);await screen(page,'updates-downloading-light');
    await page.locator('#wizardCancel').click();await sheet(page).waitFor({state:'hidden'});assert.equal(await page.locator('#recordButton').isEnabled(),true);
    await openUpdates();assert.equal(await page.locator('#updateProgress').evaluate(n=>n.value),40);
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
    await assertInsideViewport(page,'#sheet');
    assert.equal(await page.locator('#sheet').evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);assert.equal(await page.locator('#wizardBody').evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);
    await page.locator('#updateRecoveryValue').scrollIntoViewIfNeeded();await assertInsideViewport(page,'#updateRecoveryValue');await screen(page,'updates-recovery-file-720x600');
  });
  await check('dark update panel scrolls inside the 720×600 window with a reachable footer and no overflow',async()=>{
    await page.locator('#wizardCancel').click();await sheet(page).waitFor({state:'hidden'});await theme(page,'dark');
    await updates({state:'ready',latest_version:'0.7.0',current_version:'0.6.0-preview.3',can_install:false,review_count:3,install_blockers:['还有场次正在整理或排队，请等待完成。'],notes:Array.from({length:25},(_,i)=>(i+1)+'. 合成测试更新说明：保留原有资料库与录制设置。').join('\n')});
    await noHorizontalOverflow(page);await screen(page,'updates-home-dark-720x600');await openSettings(page,'general');
    await assertInsideViewport(page,'#sheet');await assertInsideViewport(page,'.sheet-foot');
    assert.equal(await page.locator('#sheet').evaluate(n=>n.scrollWidth<=n.clientWidth+1),true);
    await page.locator('#wizardBody').hover();await page.mouse.wheel(0,1200);await page.waitForFunction(()=>document.querySelector('#wizardBody').scrollTop>0);
    await page.locator('#updateInstall').scrollIntoViewIfNeeded();await assertInsideViewport(page,'#updateInstall');
    assert.ok((await box(page,'#updateInstall')).y+(await box(page,'#updateInstall')).height<=(await box(page,'.sheet-foot')).y+1,'install button is not under the footer');
    await screen(page,'updates-dark-720x600');
    await page.keyboard.press('Escape');await sheet(page).waitFor({state:'hidden'});
    await theme(page,'light');
  });
  await page.close();
}
