'use strict';

/** Real rendered review UI and real browser-encoded video metadata. All media,
 * transcript and native bridge responses are synthetic; this is not native
 * WebView2, packaged-app or OBS acceptance. Uses installed Edge, no downloads.
 * Run: node tests/test_review_aspect_browser.cjs
 * Set PLAYWRIGHT_MODULE if needed; TAR_ASPECT_OUTPUT defaults to work/review-aspect.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const output = path.resolve(process.env.TAR_ASPECT_OUTPUT || path.join(root, 'work', 'review-aspect'));
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const sources = { wide: [960, 540], ultrawide: [1280, 540], portrait: [540, 960] };
const media = new Map();
const evidence = { scope: 'Real Edge geometry with synthetic videos and native bridge only. No native window or user installation validation.', checks: [], screenshots: [], errors: [] };
let origin;

function html(params) {
  const key = params.get('source') || 'wide';
  const data = { title: '合成比例验证 · ' + key, created: '2026-09-22T10:30:00', desktop: params.get('portable') !== '1', test: true,
    video: `/media/${key}?delay=${Number(params.get('delay')) || 0}`,
    segments: Array.from({ length: 60 }, (_, i) => ({ start: i, end: i + .95, text: `合成测试原话 ${i + 1}：逐字稿独立滚动，视频的位置和尺寸应当保持稳定。` })) };
  const values = { TITLE: data.title, DATA: JSON.stringify(data), CSS: read('ui/review.css'), JS: read('ui/review.js'),
    PLYR_CSS: read('ui/vendor/plyr/plyr.css'), PLYR_JS: read('ui/vendor/plyr/plyr.min.js'), PLYR_SVG: read('ui/vendor/plyr/plyr.svg'), LICENSE: 'Synthetic source-aspect browser fixture' };
  return read('player.html').replace(/%%([A-Z_]+)%%/g, (_, key) => values[key]);
}
const server = http.createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1');
  if (url.pathname === '/fixture') { response.setHeader('Content-Type', 'text/html'); response.end('<!doctype html><title>Synthetic aspect video generator</title>'); return; }
  if (url.pathname === '/review') { response.setHeader('Content-Type', 'text/html; charset=utf-8'); response.end(html(url.searchParams)); return; }
  const body = media.get(url.pathname.replace('/media/', ''));
  if (!body) { response.writeHead(404); response.end(); return; }
  const send = () => {
    response.setHeader('Content-Type', 'video/webm'); response.setHeader('Accept-Ranges', 'bytes');
    const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range || '');
    if (range) {
      const start = Number(range[1]), end = Math.min(range[2] ? Number(range[2]) : body.length - 1, body.length - 1);
      if (start > end) { response.writeHead(416, { 'Content-Range': `bytes */${body.length}` }); response.end(); return; }
      response.writeHead(206, { 'Content-Range': `bytes ${start}-${end}/${body.length}`, 'Content-Length': end - start + 1 });
      response.end(body.subarray(start, end + 1)); return;
    }
    response.setHeader('Content-Length', body.length); response.end(body);
  };
  setTimeout(send, Number(url.searchParams.get('delay')) || 0);
});

async function makeMedia(browser) {
  const page = await browser.newPage();
  try {
    await page.goto(origin + '/fixture');
    for (const [key, [width, height]] of Object.entries(sources)) {
      const bytes = await page.evaluate(async ({ width, height }) => {
        const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height; document.body.append(canvas);
        const context = canvas.getContext('2d'), stream = canvas.captureStream(0), track = stream.getVideoTracks()[0], chunks = [];
        const mimeType = ['video/webm;codecs=vp8', 'video/webm'].find(type => MediaRecorder.isTypeSupported(type));
        assertSupported();
        function assertSupported() { if (!mimeType || !track.requestFrame) throw new Error('Installed browser cannot encode a synthetic video.'); }
        const recorder = new MediaRecorder(stream, { mimeType });
        recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
        const stopped = new Promise(resolve => { recorder.onstop = resolve; });
        function draw(frame) {
          context.fillStyle = '#252b29'; context.fillRect(0, 0, width, height);
          context.strokeStyle = '#ece7dc'; context.lineWidth = 4; context.strokeRect(10, 10, width - 20, height - 20);
          context.fillStyle = '#ece7dc'; context.font = 'bold 28px sans-serif'; context.fillText('SYNTHETIC VIDEO', 30, 70);
          context.font = '24px sans-serif'; context.fillText(`${width} x ${height}`, 30, 110);
          context.fillStyle = '#b64b37'; context.fillRect(30, 145, 30 + frame * 18, 8);
        }
        draw(0); const started = new Promise(resolve => { recorder.onstart = resolve; }); recorder.start(); await started;
        for (let frame = 1; frame <= 12; frame++) { draw(frame); track.requestFrame(); await new Promise(resolve => setTimeout(resolve, 70)); }
        recorder.stop(); await stopped; stream.getTracks().forEach(track => track.stop()); canvas.remove();
        return Array.from(new Uint8Array(await new Blob(chunks, { type: mimeType }).arrayBuffer()));
      }, { width, height });
      assert.ok(bytes.length > 1000, `Encoded ${key} fixture has frames`); media.set(key, Buffer.from(bytes));
    }
  } finally { await page.close(); }
}
async function check(name, task) {
  try { evidence.checks.push({ name, pass: true, details: await task() }); }
  catch (error) { evidence.checks.push({ name, pass: false, error: error.stack }); console.error(`FAIL ${name}: ${error.stack}`); }
}
async function settle(page) { await page.evaluate(async () => { for (let i = 0; i < 6; i++) await new Promise(requestAnimationFrame); }); }
async function geometry(page) {
  return page.evaluate(() => {
    const rect = selector => document.querySelector(selector).getBoundingClientRect().toJSON();
    const video = document.querySelector('video'), pane = document.querySelector('#videoPane'), layout = document.querySelector('.review-layout');
    const number = value => parseFloat(value) || 0, style = getComputedStyle(layout), paneStyle = getComputedStyle(pane);
    const slot = rect('.video-slot'), file = rect('.file-card'), input = rect('#inputPanel'), copy = rect('#copySplit');
    const fileVisible = getComputedStyle(document.querySelector('.file-card')).display !== 'none';
    return { viewport: { width: innerWidth, height: innerHeight }, video: rect('video'), slot, pane: rect('#videoPane'), text: rect('#transcriptPane'), lines: rect('#lines'), file,
      source: [video.videoWidth, video.videoHeight], orientation: document.querySelector('#reviewSplitter').getAttribute('aria-orientation'),
      available: layout.getBoundingClientRect().width - number(style.paddingLeft) - number(style.paddingRight) - number(style.getPropertyValue('--splitter-size')),
      input, copy, header: rect('.review-header'), fileVisible, gap: number(paneStyle.rowGap), objectFit: getComputedStyle(video).objectFit,
      reservedHeight: input.height + (fileVisible ? file.height : 0) + number(paneStyle.rowGap) * (fileVisible ? 2 : 1),
      documentScroll: document.scrollingElement.scrollTop, documentWidth: document.documentElement.scrollWidth,
      status: document.querySelector('#status').textContent, lineScroll: document.querySelector('#lines').scrollTop };
  });
}
const close = (a, b, label, tolerance = 1) => assert.ok(Math.abs(a - b) <= tolerance, `${label}: ${a} vs ${b}`);
function ratioCheck(g) {
  close(g.slot.width,g.input.width,'video and recent operations share one width');close(g.slot.width,g.pane.width,'player occupies left pane');assert.ok(g.slot.height<=g.pane.height-g.reservedHeight+1,'player respects available height');
  close(g.video.width, g.slot.width, 'video width matches its slot'); close(g.video.height, g.slot.height, 'video height matches its slot');
  close(g.slot.y, g.pane.y, 'slot is top-aligned'); assert.equal(g.objectFit, 'contain');
  assert.ok(g.file.bottom <= g.pane.bottom + 1, 'file controls remain in their pane');
  assert.ok(g.input.bottom <= g.pane.bottom + 1, 'operation panel remains within its pane');
  assert.ok(g.input.top >= g.slot.bottom, 'operation panel stays below the video');
  assert.ok(g.copy.left >= g.header.left - 1 && g.copy.right <= g.header.right + 1 && g.copy.top >= g.header.top - 1 && g.copy.bottom <= g.header.bottom + 1, 'copy controls remain in the header');
  assert.ok(g.copy.bottom <= g.slot.top, 'copy controls never cover the video');
  assert.ok(g.documentWidth <= g.viewport.width + 1, 'no document horizontal overflow');
}
function fittedCheck(g) {
  ratioCheck(g);
  assert.ok(g.text.width>=279,'right pane retains header and at least ruler plus two lanes');
}
async function screen(page, name) { await page.screenshot({ path: path.join(output, name + '.png'), animations: 'disabled' }); evidence.screenshots.push(name + '.png'); }
async function openPage(context, source, options = {}) {
  const page = await context.newPage();
  await page.addInitScript(({ saved, late }) => {
    localStorage.setItem('experience-review-layout-v1', JSON.stringify(saved));
    window.__aspectCalls = [];
    window.pywebview = { api: {
      get_layout: async () => { if (late) await new Promise(resolve => { window.__releaseLayout = resolve; }); return { ok: true, data: saved }; },
      save_layout: async (...args) => { window.__aspectCalls.push({ method: 'save_layout', args }); return { ok: true }; },
      ready: async (...args) => { window.__aspectCalls.push({ method: 'ready', args }); return { ok: true }; }
    } };
  }, { saved: options.saved || { columns: .24, rows: .54 }, late: options.late || false });
  await page.goto(`${origin}/review?source=${source}&delay=${options.delay || 0}&portable=${options.portable ? 1 : 0}`, { waitUntil: 'domcontentloaded' });
  if (!options.skipReady) await page.waitForFunction(() => document.querySelector('video').readyState >= 1);
  await settle(page); return page;
}
async function run(context) {
  for (const source of Object.keys(sources)) {
    await check(`${source}: first-open width at least 900 and contain preserves source pixels; stale ratio ignored`, async () => {
      const page = await openPage(context, source);
      try {
        const g = await geometry(page); assert.deepEqual(g.source, sources[source]); fittedCheck(g);
        assert.ok(g.pane.width>=899,'first-open video width is at least 900 when space allows');close(g.viewport.width, 1440, 'fixed outer width'); close(g.viewport.height, 900, 'fixed outer height');
        assert.ok(Math.abs(g.pane.width / g.available - .24) > .02, 'source fit overrides the saved split');
        await screen(page, `${source}-1240x900`);
        const before = g.slot;
        await page.locator('#lines').hover(); await page.mouse.wheel(0, 500);
        await page.waitForFunction(() => document.querySelector('#lines').scrollTop > 0);
        const after = await geometry(page);
        for (const key of ['x', 'y', 'width', 'height']) close(before[key], after.slot[key], `scroll leaves slot.${key}`);
        assert.equal(after.documentScroll, 0); assert.equal(await page.locator('#follow').getAttribute('aria-pressed'), 'false');
        return g;
      } finally { await page.close(); }
    });
  }
  await check('late saved layout response and portable saved preference cannot override source fit', async () => {
    const page = await openPage(context, 'portrait', { late: true, saved: { columns: .8, rows: .54 } });
    try {
      const before = await geometry(page); await page.evaluate(() => window.__releaseLayout()); await settle(page);
      const after = await geometry(page); fittedCheck(after); close(before.pane.width, after.pane.width, 'late preference retains source fit');
    } finally { await page.close(); }
    const portable = await openPage(context, 'wide', { portable: true, saved: { columns: .3, rows: .54 } });
    try { const g = await geometry(portable); fittedCheck(g); return g; } finally { await portable.close(); }
  });
  await check('manual drag survives metadata and resize; double click and Enter restore adaptive source fit', async () => {
    const page = await openPage(context, 'wide');
    try {
      const splitter = await page.locator('#reviewSplitter').boundingBox();
      await page.mouse.move(splitter.x + splitter.width / 2, splitter.y + 100); await page.mouse.down();
      await page.mouse.move(splitter.x + splitter.width / 2 - 200, splitter.y + 100, { steps: 8 }); await page.mouse.up(); await settle(page);
      const dragged = await geometry(page), share = dragged.pane.width / dragged.available;
      assert.ok(share < .7, 'drag changes the initial width'); ratioCheck(dragged);
      await page.evaluate(() => { document.querySelector('video').src = '/media/portrait'; });
      await page.waitForFunction(() => document.querySelector('video').videoWidth === 540); await settle(page);
      const changedSource = await geometry(page); ratioCheck(changedSource);
      close(changedSource.pane.width, dragged.pane.width, 'real replacement metadata preserves manual split');
      const sizes = [];let previousWidth=dragged.pane.width;
      for (const size of [{ width: 1440, height: 840 }, { width: 1050, height: 700 }, { width: 1240, height: 900 }]) {
        await page.setViewportSize(size); await settle(page); const g = await geometry(page); ratioCheck(g);
        close(g.pane.width,Math.min(previousWidth,g.available-280),'right pane absorbs resize before left shrinks');previousWidth=g.pane.width;sizes.push(g);
      }
      await page.locator('#reviewSplitter').dblclick(); await settle(page); fittedCheck(await geometry(page));
      await page.locator('#reviewSplitter').press('ArrowLeft'); await settle(page);
      assert.ok((await geometry(page)).pane.width < (await geometry(page)).available - 225);
      await page.locator('#reviewSplitter').press('Enter'); await settle(page); fittedCheck(await geometry(page));
      await page.setViewportSize({ width: 1440, height: 840 }); await settle(page); fittedCheck(await geometry(page));
      return { dragged, sizes };
    } finally { await page.close(); }
  });
  await check('a user adjustment before metadata is retained once real metadata arrives', async () => {
    const page = await openPage(context, 'portrait', { delay: 900, skipReady: true });
    try {
      assert.equal(await page.locator('video').evaluate(video => video.videoWidth), 0);
      await page.locator('#reviewSplitter').press('ArrowRight'); const before = await geometry(page);
      await page.waitForFunction(() => document.querySelector('video').readyState >= 1); await settle(page);
      const after = await geometry(page); ratioCheck(after); close(after.pane.width, before.pane.width, 'early user adjustment retained');
      await page.locator('#reviewSplitter').press('Enter'); await settle(page); fittedCheck(await geometry(page));
      return after;
    } finally { await page.close(); }
  });
  await check('portrait controls and reserved input panel settle across compact breakpoints without resize oscillation', async () => {
    const page = await openPage(context, 'portrait'), samples = [];
    try {
      for (let height = 650; height <= 880; height += 10) {
        await page.setViewportSize({ width: 1000, height }); await settle(page);
        const g = await geometry(page); fittedCheck(g);
        const frames = await page.evaluate(async () => {
          const values = []; for (let i = 0; i < 10; i++) { await new Promise(requestAnimationFrame); values.push(document.querySelector('#videoPane').getBoundingClientRect().width); } return values;
        });
        assert.ok(Math.max(...frames) - Math.min(...frames) < .5, 'consecutive rendered frames stay stable');
        if (height === 700) await screen(page, 'portrait-wrapped-controls-1000x700');
        samples.push({ height, paneWidth: g.pane.width, slotWidth: g.slot.width, slotHeight: g.slot.height, inputHeight: g.input.height, reservedHeight: g.reservedHeight });
      }
      assert.ok(new Set(samples.map(sample => sample.inputHeight)).size > 1, 'test crosses the real compact operation-panel breakpoint');
      const before = await geometry(page);
      for (const mode of ['collapsed', 'device', 'keys']) {
        await page.locator(`[data-input-mode="${mode}"]`).click(); await settle(page);
        const after = await geometry(page); fittedCheck(after);
        for (const key of ['x','y','width','height']) close(before.slot[key], after.slot[key], `input mode ${mode} preserves slot.${key}`);
      }
      return samples;
    } finally { await page.close(); }
  });
  await check('compact stacked layout retains source ratio, readable transcript and independent scrolling', async () => {
    const result = [];
    for (const source of ['wide', 'portrait']) {
      const page = await openPage(context, source);
      try {
        await page.setViewportSize({ width: 560, height: 540 }); await settle(page); const before = await geometry(page); ratioCheck(before);
        assert.equal(before.orientation, 'horizontal'); assert.ok(before.lines.height >= 32);
        assert.ok(before.text.y >= before.pane.bottom, 'transcript stacks below video');
        for (const control of ['play', 'mute', 'fullscreen']) {
          const button = await page.locator(`.plyr__controls [data-plyr="${control}"]`).boundingBox();
          assert.ok(button && button.x >= before.slot.x - 1 && button.x + button.width <= before.slot.right + 1
            && button.y >= before.slot.y - 1 && button.y + button.height <= before.slot.bottom + 1, `${control} remains usable in the source-ratio slot`);
        }
        await page.locator('#lines').hover(); await page.mouse.wheel(0, 500); await page.waitForFunction(() => document.querySelector('#lines').scrollTop > 0);
        const after = await geometry(page); for (const key of ['x', 'y', 'width', 'height']) close(before.slot[key], after.slot[key], `compact scroll slot.${key}`);
        await page.locator('#reviewSplitter').press('ArrowDown'); await settle(page); ratioCheck(await geometry(page));
        await page.locator('#reviewSplitter').press('Enter'); await settle(page); await screen(page, `${source}-stacked-560x540`); result.push(before);
      } finally { await page.close(); }
    }
    return result;
  });
  await check('missing metadata retains bounded saved-column fallback', async () => {
    const page = await openPage(context, 'missing', { skipReady: true, saved: { columns: .4, rows: .54 } });
    try {
      const g = await geometry(page); assert.deepEqual(g.source, [0, 0]); close(g.pane.width,Math.min(900,g.available-280),'bounded first-open target',1);
      assert.equal(await page.locator('.video-slot').evaluate(node => node.classList.contains('source-aspect')), false); return g;
    } finally { await page.close(); }
  });
}
async function main() {
  fs.mkdirSync(output, { recursive: true }); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  const browser = await chromium.launch({ headless: true, channel: process.env.TAR_UI_CHANNEL || 'msedge' });
  try {
    await makeMedia(browser);
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    context.setDefaultTimeout(6000);
    context.on('page', page => page.on('pageerror', error => evidence.errors.push(error.message)));
    await context.route('**/*', route => {
      if (route.request().url().startsWith(origin + '/')) return route.continue();
      evidence.errors.push('Unexpected non-fixture request: ' + route.request().url()); return route.abort();
    });
    await run(context); await check('no browser exceptions or external requests', () => assert.deepEqual(evidence.errors, [])); await context.close();
  } finally { await browser.close(); server.close(); }
  evidence.passed = evidence.checks.every(check => check.pass);
  fs.writeFileSync(path.join(output, 'acceptance.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({ passed: evidence.passed, checks: evidence.checks.length, failures: evidence.checks.filter(check => !check.pass), output }, null, 2));
  if (!evidence.passed) process.exitCode = 1;
}
main().catch(error => { console.error(error.stack); server.close(); process.exitCode = 1; });
