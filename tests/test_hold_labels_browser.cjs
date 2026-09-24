'use strict';

/** Real headless Edge rendering of the production review template and assets.
 * Synthetic video/input/transcript/bridge only; never records user devices.
 * Run: node tests/test_hold_labels_browser.cjs (PLAYWRIGHT_MODULE may be set).
 * Evidence defaults to work/hold-labels; override with TAR_HOLD_OUTPUT.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const output = path.resolve(process.env.TAR_HOLD_OUTPUT || path.join(root, 'work', 'hold-labels'));
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const media = fs.readFileSync(path.join(root, 'docs/prototypes/input-review/demo.mp4'));
const intervals = [
  { id: 'w-held', device: 'keyboard', code: 'W', kind: 'button', start: .4, end: 26 },
  { id: 'dpad-up', device: 'xbox', code: 'DPadUp', kind: 'button', start: .6, end: .68 },
  { id: 'mouse-motion', device: 'mouse', code: 'MouseMove', kind: 'motion', direction: '↗', value: .4, start: .8, end: 25 },
  { id: 'e-held', device: 'keyboard', code: 'E', kind: 'button', start: 1, end: 26 },
  { id: 'dpad-down', device: 'xbox', code: 'DPadDown', kind: 'button', start: 1, end: 1.08 },
  { id: 'lt-first', device: 'xbox', code: 'LT', kind: 'trigger', value: .12, start: 1.2, end: 1.24 },
  { id: 'lt-rise-1', device: 'xbox', code: 'LT', kind: 'trigger', value: .32, start: 1.24, end: 1.28 },
  { id: 'lt-rise-2', device: 'xbox', code: 'LT', kind: 'trigger', value: .62, start: 1.28, end: 1.36 },
  { id: 'lt-held', device: 'xbox', code: 'LT', kind: 'trigger', value: 1, start: 1.36, end: 25.6 },
  { id: 'ps-l2-held', device: 'dualsense', code: 'L2', kind: 'trigger', value: 1, start: 1.6, end: 23.8 },
  { id: 'shift-tap', device: 'keyboard', code: 'ShiftLeft', kind: 'button', start: 2, end: 2.18 },
  { id: 'menu-tap', device: 'xbox', code: 'Menu', kind: 'button', start: 2.01, end: 2.19 },
  { id: 'options-tap', device: 'dualsense', code: 'Options', kind: 'button', start: 2.02, end: 2.21 },
  { id: 'mouse-tap', device: 'mouse', code: 'MouseLeft', kind: 'button', start: 2.03, end: 2.16 },
  { id: 'lt-release', device: 'xbox', code: 'LT', kind: 'trigger', value: .2, start: 25.6, end: 25.65 },
];
const data = {
  title: '长按标签与键位网格 · 合成验收', game: '合成输入', created: '2026-09-24T12:00:00',
  desktop: true, test: true, video: '/demo.mp4', revision: 'holds-1',
  segments: [{ start: 4, end: 6, text: '这是合成原话，便于对照标签位置；不含真实录制内容。' }],
  transcription: { state: 'ready' },
  inputs: { version: 1, state: 'complete', duration: 32, timebase: 'video_seconds', intervals, gaps: [] },
};
const sources = Object.fromEntries(['player.html', 'ui/review.js', 'ui/review.css'].map(file => [file, read(file)]));
const values = {
  TITLE: data.title, DATA: JSON.stringify(data), CSS: sources['ui/review.css'], JS: sources['ui/review.js'],
  PLYR_CSS: read('ui/vendor/plyr/plyr.css'), PLYR_JS: read('ui/vendor/plyr/plyr.min.js'),
  PLYR_SVG: read('ui/vendor/plyr/plyr.svg'), LICENSE: 'Synthetic hold label browser acceptance',
};
const html = sources['player.html'].replace(/%%([A-Z_]+)%%/g, (_, key) => values[key]);
const report = {
  scope: 'Production DOM/CSS in headless Edge with synthetic media and input. Geometry, hit-test paint order, scrolling and real video playback; no native capture or installation acceptance.',
  started_at: new Date().toISOString(), checks: [], screenshots: [], errors: [],
  source_sha256: Object.fromEntries(Object.entries(sources).map(([name, source]) =>
    [name, crypto.createHash('sha256').update(source).digest('hex')])),
};
let browser, origin;
const server = http.createServer((request, response) => {
  if (request.url === '/favicon.ico') { response.writeHead(204); response.end(); return; }
  if (request.url === '/demo.mp4') {
    response.setHeader('Content-Type', 'video/mp4'); response.setHeader('Accept-Ranges', 'bytes');
    const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range || '');
    if (range) {
      const start = +range[1], end = Math.min(range[2] ? +range[2] : media.length - 1, media.length - 1);
      if (start > end) { response.writeHead(416, { 'Content-Range': `bytes */${media.length}` }); response.end(); return; }
      response.writeHead(206, { 'Content-Range': `bytes ${start}-${end}/${media.length}`, 'Content-Length': end - start + 1 });
      response.end(media.subarray(start, end + 1)); return;
    }
    response.setHeader('Content-Length', media.length); response.end(media); return;
  }
  if (request.url !== '/') { response.writeHead(404); response.end(); return; }
  response.setHeader('Content-Type', 'text/html; charset=utf-8'); response.end(html);
});
const selectors = {
  lt: '[data-input-id="lt-first"] .hold-label[data-held-start][data-held-end]',
  w: '[data-input-id="w-held"] .hold-label[data-held-start][data-held-end]',
  e: '[data-input-id="e-held"] > .bar-glyph',
  l2: '[data-input-id="ps-l2-held"] > .bar-glyph',
};
const ranges = { lt: [1.36, 25.6], w: [.4, 26], e: [1, 26], l2: [1.6, 23.8] };
const labels = { lt: 'LT', w: 'W', e: 'E', l2: 'L2' };

async function settle(page) { await page.evaluate(async () => { for (let i = 0; i < 3; i++) await new Promise(requestAnimationFrame); }); }
function near(actual, expected, description, tolerance = 1) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${description}: ${actual} vs ${expected}`);
}
async function seek(page, seconds) {
  await page.locator('video').evaluate((video, value) => { video.currentTime = value; }, seconds);
  await page.waitForFunction(value => { const video = document.querySelector('video');
    return !video.seeking && video.readyState >= 2 && Math.abs(video.currentTime - value) < .03;
  }, seconds); await settle(page);
}
async function playback(page) {
  return page.locator('video').evaluate(video => ({ time: video.currentTime, paused: video.paused,
    rate: video.playbackRate, events: [...window.__mediaEvents] }));
}
async function map(page) {
  return page.evaluate(() => {
    const timeline = document.querySelector('#inputTimeline').getBoundingClientRect();
    const horizontal = document.querySelector('.timeline-horizontal-scroll').getBoundingClientRect();
    const ticks = [...document.querySelectorAll('.timeline-ruler .time-tick')].slice(0, 2);
    const second = node => node.textContent.trim().split(':').reduce((total, value) => total * 60 + Number(value), 0);
    const scale = (ticks[1].getBoundingClientRect().top - ticks[0].getBoundingClientRect().top) / (second(ticks[1]) - second(ticks[0]));
    const start = second(ticks[0]) - (ticks[0].getBoundingClientRect().top - timeline.top) / scale;
    return { top: timeline.top, bottom: timeline.bottom, height: timeline.height,
      left: horizontal.left, right: horizontal.right, scale, start };
  });
}
async function viewAt(page, time) {
  const before = await map(page);
  await page.mouse.move(before.right - 16, before.top + 110);
  await page.mouse.wheel(0, (time - before.start) * before.scale);
  await settle(page); await page.locator('#title').hover(); await settle(page);
  const after = await map(page), expected = Math.max(0, Math.min(32 - after.height / after.scale, time));
  near(after.start, expected, 'Content wheel reaches requested visible time', .03); return after;
}
async function zoomTo(page, scale) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const before = await map(page); if (Math.abs(before.scale - scale) < .02) return before;
    const delta = Math.max(-240, Math.min(240, -Math.log(scale / before.scale) / .0025));
    await page.mouse.move(before.left + 15, before.top + 90); await page.mouse.wheel(0, delta); await settle(page);
  }
  const after = await map(page); near(after.scale, scale, 'Zoom reaches requested scale', .03); return after;
}
async function screenshot(page, name) {
  const filename = name + '.png'; await page.screenshot({ path: path.join(output, filename) }); report.screenshots.push(filename);
}
async function measureLabel(page, key) {
  const selector = selectors[key]; assert.equal(await page.locator(selector).count(), 1, `${key} has exactly one label`);
  return page.locator(selector).evaluate(element => {
    const bar = element.closest('.key-bar'), rect = element.getBoundingClientRect(), style = getComputedStyle(element);
    return { text: element.textContent.trim(), rect: rect.toJSON(), bar: bar.getBoundingClientRect().toJSON(),
      display: style.display, visibility: style.visibility, opacity: Number(style.opacity), color: style.color,
      start: element.dataset.heldStart == null ? Number(bar.dataset.start) : Number(element.dataset.heldStart),
      end: element.dataset.heldEnd == null ? Number(bar.dataset.end) : Number(element.dataset.heldEnd),
      hovered: bar.matches(':hover'), hidden: element.hidden, barClass: bar.className };
  });
}
async function assertPaintedLabel(page, key, { sticky = true } = {}) {
  const label = await measureLabel(page, key), timeline = await map(page), [start, end] = ranges[key];
  assert.equal(label.text, labels[key]); assert.equal(label.hidden, false); assert.notEqual(label.display, 'none');
  assert.notEqual(label.visibility, 'hidden'); assert.ok(label.opacity > 0);
  near(label.start, start, `${key} original start`, .0001); near(label.end, end, `${key} original end`, .0001);
  const startY = timeline.top + (start - timeline.start) * timeline.scale;
  const endY = timeline.top + (end - timeline.start) * timeline.scale;
  assert.ok(label.rect.top >= startY - 1 && label.rect.bottom <= endY + 1, `${key} label remains inside its actual hold`);
  if (sticky) near(label.rect.top, Math.max(startY, Math.min(timeline.top, endY - label.rect.height)), `${key} top follows visible hold`, 2);
  assert.ok(label.rect.top >= timeline.top - 1 && label.rect.bottom <= timeline.bottom + 1, `${key} label is fully visible`);
  const painted = await page.locator(selectors[key]).evaluate(element => {
    // Pointer-events do not affect paint/layout. Temporarily enable hit testing
    // for label and fill alike: otherwise a covering pointer-events:none fill
    // could wrongly appear harmless in elementFromPoint. No z-index is changed.
    const bar = element.closest('.key-bar'), nodes = [element, ...bar.querySelectorAll('.held-section,.bar-duration')];
    const saved = nodes.map(node => [node, node.style.getPropertyValue('pointer-events'), node.style.getPropertyPriority('pointer-events')]);
    try {
      nodes.forEach(node => node.style.setProperty('pointer-events', 'auto', 'important'));
      const rect = element.getBoundingClientRect(), x = rect.left + rect.width / 2, y = rect.top + rect.height / 2;
      const hit = document.elementFromPoint(x, y), stack = document.elementsFromPoint(x, y);
      return { topIsLabel: hit === element || element.contains(hit), top: hit?.className || hit?.nodeName,
        stack: stack.slice(0, 7).map(node => ({ tag: node.tagName, class: node.className,
          zIndex: getComputedStyle(node).zIndex, background: getComputedStyle(node).backgroundColor })),
        x, y, fill: bar.querySelector('.held-section') ? getComputedStyle(bar.querySelector('.held-section')).backgroundColor : getComputedStyle(bar).backgroundColor };
    } finally { for (const [node, value, priority] of saved) value ? node.style.setProperty('pointer-events', value, priority) : node.style.removeProperty('pointer-events'); }
  });
  assert.equal(painted.topIsLabel, true, `${key} glyph paints above its fill: ${JSON.stringify(painted)}`);
  assert.notEqual(label.color, painted.fill, `${key} text differs from the fill color`);
  return { label, painted, timeline };
}
async function grid(page) {
  return page.evaluate(() => ({
    heads: [...document.querySelectorAll('.timeline-column-headings > span')].map(el => el.getBoundingClientRect().toJSON()),
    rows: [...document.querySelectorAll('.key-bar[data-channel="other"]')].map(el => ({
      id: el.dataset.inputId, lane: Number(el.dataset.lane), rect: el.getBoundingClientRect().toJSON(),
    })),
    scroll: document.querySelector('.timeline-horizontal-scroll').scrollLeft,
    overflow: document.querySelector('.timeline-horizontal-scroll').scrollWidth - document.querySelector('.timeline-horizontal-scroll').clientWidth,
  }));
}
function uniformGrid(result) {
  const expected = ['e-held', 'lt-first', 'ps-l2-held', 'shift-tap', 'menu-tap', 'options-tap', 'mouse-tap'];
  for (const id of expected) assert.ok(result.rows.some(row => row.id === id), `Grid includes ${id}`);
  const rows = result.rows, width = rows[0].rect.width;
  for (const row of rows) near(row.rect.width, width, `Uniform key width ${row.id}`, .2);
  const lanes = [...new Map(rows.map(row => [row.lane, row])).values()].sort((a, b) => a.lane - b.lane);
  assert.ok(lanes.length >= 7, 'Fixture exercises at least seven simultaneous columns');
  const step = (lanes[1].rect.left - lanes[0].rect.left) / (lanes[1].lane - lanes[0].lane);
  assert.ok(step > width, 'Columns have a real separating gap');
  for (const row of rows) near(row.rect.left, lanes[0].rect.left + (row.lane - lanes[0].lane) * step, `Aligned key lane ${row.id}`);
  near(lanes[0].rect.left, result.heads[5].left + 4, 'Key grid aligns to its heading');
  return { width, step, result };
}

async function fresh() {
  const context = await browser.newContext({ viewport: { width: 1920, height: 900 }, reducedMotion: 'reduce' });
  const page = await context.newPage(); page.setDefaultTimeout(8000);
  page.on('pageerror', error => report.errors.push(error.stack || error.message));
  await page.addInitScript(snapshot => {
    window.__mediaEvents = []; window.__snapshot = snapshot;
    window.pywebview = { api: { ready: async () => ({ ok: true }), get_layout: async () => ({ ok: true, data: {} }),
      save_layout: async () => ({ ok: true }), get_snapshot: async known => ({ ok: true,
        data: known === window.__snapshot.revision ? { unchanged: true, revision: known } : structuredClone(window.__snapshot) }) } };
  }, structuredClone(data));
  try {
    await page.goto(origin + '/');
    await page.waitForFunction(() => document.querySelector('video').readyState >= 2 && document.querySelector('[data-input-id="lt-first"]'));
    await page.locator('video').evaluate(video => { video.pause();
      for (const event of ['seeking', 'play', 'pause', 'ratechange']) video.addEventListener(event, () => window.__mediaEvents.push(event)); });
    await seek(page, .1);
    if (await page.locator('#follow').getAttribute('aria-pressed') === 'true') await page.locator('#follow').click();
    await page.locator('#title').hover(); await page.evaluate(() => { window.__mediaEvents = []; });
    return { context, page };
  } catch (error) { await context.close(); throw error; }
}
async function check(name, task) {
  let context, page; const item = { name, pass: false };
  try { ({ context, page } = await fresh()); item.details = await task(page); item.pass = true; }
  catch (error) { item.error = error.stack || String(error); console.error(`FAIL ${name}: ${item.error}`);
    if (page) try { await screenshot(page, name + '-FAILED'); } catch {} }
  finally { if (context) await context.close(); }
  report.checks.push(item);
}

async function main() {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ channel: 'msedge', headless: true });

  await check('sampled-trigger-hold-name-paints-above-warm-fill-without-hover', async page => {
    const result = await assertPaintedLabel(page, 'lt');
    assert.equal(result.label.hovered, false); assert.ok(result.label.barClass.includes('activity-band'));
    assert.equal(await page.locator('[data-input-id="lt-first"] .held-section[data-held-id="lt-held"]').count(), 1);
    const fill = await page.locator('[data-held-id="lt-held"]').boundingBox();
    near(fill.height, (25.6 - 1.36) * result.timeline.scale, 'Warm fill preserves the actual stable sample duration');
    await screenshot(page, 'trigger-label-above-fill'); return { ...result, fill };
  });

  await check('keyboard-and-ps5-long-holds-are-labelled-but-shift-tap-is-not-a-hold', async page => {
    const results = {};
    for (const key of ['w', 'e', 'l2']) { results[key] = await assertPaintedLabel(page, key); assert.equal(results[key].label.hovered, false); }
    assert.equal(await page.locator('[data-input-id="w-held"] > .bar-glyph').count(), 1, 'Current direction glyph is retained beside the fixed hold name');
    assert.equal(await page.locator('[data-input-id="shift-tap"]').evaluate(el => el.classList.contains('long-press')), false);
    assert.equal(await page.locator('[data-input-id="shift-tap"] .hold-label').count(), 0);
    assert.equal((await page.locator('[data-input-id="shift-tap"] .bar-glyph').textContent()).trim(), 'Shift');
    await screenshot(page, 'keyboard-ps5-and-short-shift'); return results;
  });

  await check('scroll-pins-labels-to-visible-hold-top-without-seeking-video', async page => {
    const before = await playback(page), initial = {};
    for (const key of Object.keys(selectors)) initial[key] = await assertPaintedLabel(page, key);
    const timeline = await viewAt(page, 8), scrolled = {};
    for (const key of Object.keys(selectors)) {
      scrolled[key] = await assertPaintedLabel(page, key);
      near(scrolled[key].label.rect.top, timeline.top, `${key} stays at visible top`, 2);
      assert.ok(scrolled[key].label.bar.top < timeline.top, 'The original record top is outside the viewport');
    }
    const after = await playback(page); near(after.time, before.time, 'Browsing does not seek', .01);
    assert.equal(after.paused, true); assert.deepEqual(after.events, []);
    await screenshot(page, 'sticky-labels-after-scroll'); return { initial, scrolled, before, after };
  });

  await check('zoom-and-trailing-edge-never-float-labels-outside-their-real-holds', async page => {
    const before = await playback(page), zoomed = [], tails = [];
    for (const scale of [32, 120, 240]) {
      await zoomTo(page, scale); await viewAt(page, 6);
      zoomed.push({ scale, labels: await Promise.all(Object.keys(selectors).map(key => assertPaintedLabel(page, key))) });
    }
    for (const start of [25.4, 25.58, 25.72, 26.05]) {
      const timeline = await viewAt(page, start), labelsAtTail = {};
      for (const key of ['lt', 'w', 'e']) {
        if (!(await page.locator(selectors[key]).count())) { labelsAtTail[key] = { virtualized: true }; continue; }
        const label = await measureLabel(page, key), [heldStart, heldEnd] = ranges[key];
        const startY = timeline.top + (heldStart - timeline.start) * timeline.scale;
        const endY = timeline.top + (heldEnd - timeline.start) * timeline.scale;
        if (!label.hidden && label.display !== 'none') {
          assert.ok(label.rect.top >= startY - 1 && label.rect.bottom <= endY + 1, `${key} never extends below its actual release`);
          if (heldEnd <= timeline.start) assert.ok(label.rect.bottom <= timeline.top + 1, `${key} released label cannot float at the viewport top`);
        }
        labelsAtTail[key] = label;
      }
      tails.push({ timeline, labels: labelsAtTail });
    }
    const after = await playback(page); near(after.time, before.time, 'Zoom and tail browsing preserve playhead', .01);
    assert.deepEqual(after.events, []); await screenshot(page, 'labels-near-release-edge'); return { zoomed, tails, before, after };
  });

  await check('natural-playback-follow-keeps-long-hold-names-at-visible-top', async page => {
    await seek(page, 18);
    await page.locator('#follow').click();
    await page.locator('video').evaluate(video => { video.playbackRate = 2; });
    await page.locator('.plyr__controls [data-plyr=play]').click();
    await page.waitForFunction(() => !document.querySelector('video').paused && window.__mediaEvents.includes('play') && document.querySelector('video').currentTime > 18.3);
    await page.evaluate(() => { window.__mediaEvents = []; });
    const before = await playback(page);
    await page.waitForFunction(time => document.querySelector('video').currentTime > time + .7, before.time);
    await settle(page);
    const results = {};
    for (const key of Object.keys(selectors)) results[key] = await assertPaintedLabel(page, key);
    const after = await playback(page); assert.equal(after.paused, false); assert.equal(after.rate, 2); assert.deepEqual(after.events, []);
    assert.ok(after.time > before.time); assert.ok(results.lt.timeline.start > 10, 'Natural follow has moved beyond the original record top');
    await screenshot(page, 'long-hold-labels-following-playback'); return { before, after, labels: results };
  });

  await check('all-other-key-columns-share-one-width-through-zoom-and-horizontal-browsing', async page => {
    const baseline = uniformGrid(await grid(page));
    const dedicated = baseline.result.heads.slice(2, 5).map(rect => rect.width), views = [];
    await page.setViewportSize({ width: 1440, height: 900 }); await settle(page);
    for (const scale of [64, 120, 32]) {
      await zoomTo(page, scale); await viewAt(page, 0);
      await page.locator('.timeline-horizontal-scroll').evaluate(el => { el.scrollLeft = 0; }); await settle(page);
      const left = uniformGrid(await grid(page)); assert.ok(left.result.overflow > 0, 'Narrow fixture requires horizontal browsing');
      near(left.width, baseline.width, 'Zoom does not change the key cell width');
      left.result.heads.slice(2, 5).forEach((rect, index) => near(rect.width, dedicated[index], 'Dedicated track width is preserved'));
      await page.locator('.timeline-horizontal-scroll').evaluate(el => { el.scrollLeft = el.scrollWidth; }); await settle(page);
      const right = uniformGrid(await grid(page)); assert.ok(right.result.scroll > 0);
      near(right.width, baseline.width, 'Horizontal browsing retains uniform width');
      right.result.heads.slice(2, 5).forEach((rect, index) => near(rect.width, dedicated[index], 'Fixed direction/pointing/D-pad track width is unchanged'));
      views.push({ scale, left, right });
    }
    await screenshot(page, 'uniform-key-columns-horizontal'); return { baseline, dedicated, views };
  });

  await check('minimum-zoom-half-second-fixed-holds-never-cover-following-inputs', async page => {
    const shortHolds = [
      { id: 'short-w', device: 'keyboard', code: 'W', kind: 'button', start: 3, end: 3.501 },
      { id: 'next-w', device: 'keyboard', code: 'W', kind: 'button', start: 3.521, end: 3.6 },
      { id: 'short-dpad', device: 'xbox', code: 'DPadDown', kind: 'button', start: 5, end: 5.501 },
      { id: 'next-dpad', device: 'xbox', code: 'DPadRight', kind: 'button', start: 5.521, end: 5.601 },
    ];
    await page.evaluate(intervals => {
      window.__snapshot.inputs = { version: 1, state: 'complete', duration: 32, intervals, gaps: [] };
      window.__snapshot.revision = 'short-fixed-holds';
    }, shortHolds);
    await page.waitForFunction(() => document.querySelector('[data-input-id="short-w"] .hold-label')
      && document.querySelector('[data-input-id="short-dpad"] .hold-label'));
    await zoomTo(page, 12); await viewAt(page, 0);
    const timeline = await map(page), before = await playback(page), evidence = [];
    near(timeline.scale, 12, 'Minimum timeline scale', .01);
    for (const id of ['short-w', 'short-dpad']) {
      const physical = shortHolds.find(item => item.id === id);
      const next = shortHolds.find(item => item.id === (id === 'short-w' ? 'next-w' : 'next-dpad'));
      const selector = `[data-input-id="${id}"] .hold-label`;
      assert.equal(await page.locator(selector).count(), 1);
      const header = await page.locator(selector).evaluate(element => ({
        rect: element.getBoundingClientRect().toJSON(), start: Number(element.dataset.heldStart),
        end: Number(element.dataset.heldEnd), overflow: getComputedStyle(element).overflow,
        hidden: element.hidden, bar: element.closest('.key-bar').getBoundingClientRect().toJSON(),
      }));
      const startY = timeline.top + (physical.start - timeline.start) * timeline.scale;
      const endY = timeline.top + (physical.end - timeline.start) * timeline.scale;
      const nextY = timeline.top + (next.start - timeline.start) * timeline.scale;
      near(header.start, physical.start, `${id} actual start`, .00001);
      near(header.end, physical.end, `${id} actual release`, .00001);
      assert.equal(header.hidden, false); assert.equal(header.overflow, 'hidden');
      // A one-pixel border inset is valid; padding must not extend the bottom
      // past the actual hold or into the following physical press.
      near(header.rect.top, startY, `${id} label starts at the physical press`, 1.05);
      near(header.rect.height, .501 * 12, `${id} label is cropped to six pixels rather than padded to 28`, .03);
      assert.ok(header.rect.bottom <= endY + .05, `${id} label bottom cannot exceed the hold release: ${JSON.stringify({ header, startY, endY, nextY })}`);
      assert.ok(header.rect.bottom < nextY, `${id} leaves the next input uncovered`);
      const hit = await page.locator(selector).evaluate((element, point) => {
        const saved = element.style.getPropertyValue('pointer-events');
        const priority = element.style.getPropertyPriority('pointer-events');
        try {
          element.style.setProperty('pointer-events', 'auto', 'important');
          const rect = element.getBoundingClientRect();
          const target = document.elementFromPoint(rect.left + rect.width / 2, point);
          return { previousLabelCoversNext: target === element || element.contains(target),
            topElement: target?.className || target?.nodeName };
        } finally { saved ? element.style.setProperty('pointer-events', saved, priority) : element.style.removeProperty('pointer-events'); }
      }, nextY + .25);
      assert.equal(hit.previousLabelCoversNext, false, 'Actual hit testing confirms the prior header is not over the next input');
      evidence.push({ id, header, startY, endY, nextY, hit });
    }
    const after = await playback(page); near(after.time, before.time, 'Boundary inspection does not seek', .01);
    assert.deepEqual(after.events, []);
    await screenshot(page, 'half-second-fixed-holds-at-12px');
    const detail = 'half-second-fixed-holds-at-12px-detail.png';
    await page.locator('#inputTimelinePanel').screenshot({ path: path.join(output, detail) }); report.screenshots.push(detail);
    return { timeline, labels: evidence, before, after };
  });

  await check('first-quote-hover-opens-left-of-speech-track-and-resize-clamps', async page => {
    const quote = page.locator('#timelineSpeech [data-quote="0"]');
    const before = await playback(page), anchor = await quote.boundingBox();
    await quote.hover();
    assert.equal(await page.locator('#quotePopover').isVisible(), true);
    const initial = await page.locator('#quotePopover').boundingBox();
    assert.ok(anchor.x > initial.width + 24, 'Fixture provides enough space to the left of the speech track');
    near(initial.x + initial.width, anchor.x - 12, 'Popover right edge sits just left of the speech track');
    assert.ok(initial.x >= 0 && initial.y >= 0);
    await screenshot(page, 'quote-hover-left-of-track');
    await quote.click();
    await page.setViewportSize({ width: 560, height: 540 }); await settle(page);
    assert.equal(await page.locator('#quotePopover').isVisible(), true);
    const small = await page.evaluate(() => {
      const popover = document.querySelector('#quotePopover').getBoundingClientRect();
      const close = document.querySelector('#quoteClose').getBoundingClientRect();
      return { rect: popover.toJSON(), width: innerWidth, height: innerHeight,
        closeReachable: !!document.elementFromPoint(close.x + close.width / 2, close.y + close.height / 2)?.closest('#quoteClose') };
    });
    assert.ok(small.rect.left >= 0 && small.rect.top >= 0 && small.rect.right <= small.width && small.rect.bottom <= small.height);
    assert.equal(small.closeReachable, true);
    const after = await playback(page); near(after.time, before.time, 'Hover and resize preserve playhead', .01);
    assert.deepEqual(after.events, []); await screenshot(page, 'left-quote-clamped-after-resize');
    return { anchor, initial, small, before, after };
  });
}

main().catch(error => { report.errors.push(error.stack || String(error)); console.error(error); }).finally(async () => {
  if (browser) await browser.close();
  if (server.listening) await new Promise(resolve => server.close(resolve));
  report.finished_at = new Date().toISOString();
  report.passed = report.checks.length === 8 && report.checks.every(item => item.pass) && report.errors.length === 0;
  fs.mkdirSync(output, { recursive: true }); fs.writeFileSync(path.join(output, 'acceptance.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2)); if (!report.passed) process.exitCode = 1;
});
