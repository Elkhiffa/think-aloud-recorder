'use strict';

/** Production review template, JavaScript and CSS in installed headless Edge.
 * All media, transcript and bridge responses are synthetic. This does not
 * exercise native WebView2, recording devices or the user's installation.
 * Run: node tests/test_quote_popover_browser.cjs
 * Set PLAYWRIGHT_MODULE when needed. Output: work/quote-popover (or TAR_QUOTE_OUTPUT).
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const output = path.resolve(process.env.TAR_QUOTE_OUTPUT || path.join(root, 'work', 'quote-popover'));
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const media = fs.readFileSync(path.join(root, 'docs/prototypes/input-review/demo.mp4'));
const fixture = {
  title: '固定原话 · 合成验收', session_name: '固定原话 · 合成验收', game: '合成示例',
  created: '2026-09-24T10:00:00', desktop: true, test: true, video: '/demo.mp4',
  vault_path: 'D:\\synthetic\\library', revision: 'fixture-1', transcription: { state: 'ready' },
  segments: [
    { start: 1.2, end: 2.5, text: '这里是一段用于选择与拖动验收的合成原话。只有拖动上方时间标题才应移动浮层，选择这段正文时应当保留文本选区。' },
    { start: 3.2, end: 4.4, text: '第二段合成原话：点击后更新全文，同时保留我刚刚调整好的浮层位置。' },
    { start: 15, end: 17.5, text: '远处的合成原话，用于确认浏览其他时间段不会让已固定的内容消失。' },
  ],
  inputs: { version: 1, state: 'complete', duration: 32, timebase: 'video_seconds', gaps: [], intervals: [
    { id: 'fixture-w', device: 'keyboard', code: 'W', kind: 'button', start: .5, end: 6.5 },
    { id: 'fixture-e', device: 'keyboard', code: 'E', kind: 'button', start: 2.8, end: 2.95 },
    { id: 'fixture-q', device: 'keyboard', code: 'Q', kind: 'button', start: 4.8, end: 5 },
  ] },
};
const values = {
  TITLE: fixture.title, DATA: JSON.stringify(fixture), CSS: read('ui/review.css'), JS: read('ui/review.js'),
  PLYR_CSS: read('ui/vendor/plyr/plyr.css'), PLYR_JS: read('ui/vendor/plyr/plyr.min.js'),
  PLYR_SVG: read('ui/vendor/plyr/plyr.svg'), LICENSE: 'Synthetic quote popover acceptance',
};
const html = read('player.html').replace(/%%([A-Z_]+)%%/g, (_, name) => values[name]);
const evidence = {
  scope: 'Synthetic production UI in headless Microsoft Edge; actual pointer events, selection, video playback and snapshot polling. No native window, OBS or user-data validation.',
  started_at: new Date().toISOString(), checks: [], screenshots: [], errors: [],
  source_sha256: Object.fromEntries(['player.html', 'ui/review.js', 'ui/review.css'].map(file =>
    [file, crypto.createHash('sha256').update(read(file)).digest('hex')])),
};
let browser, origin;
const server = http.createServer((request, response) => {
  if (request.url === '/favicon.ico') { response.writeHead(204); response.end(); return; }
  if (request.url === '/demo.mp4') {
    response.setHeader('Content-Type', 'video/mp4'); response.setHeader('Accept-Ranges', 'bytes');
    const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers.range || '');
    if (range) {
      const start = Number(range[1]), end = Math.min(range[2] ? Number(range[2]) : media.length - 1, media.length - 1);
      if (start > end) { response.writeHead(416, { 'Content-Range': `bytes */${media.length}` }); response.end(); return; }
      response.writeHead(206, { 'Content-Range': `bytes ${start}-${end}/${media.length}`, 'Content-Length': end - start + 1 });
      response.end(media.subarray(start, end + 1)); return;
    }
    response.setHeader('Content-Length', media.length); response.end(media); return;
  }
  if (request.url !== '/') { response.writeHead(404); response.end(); return; }
  response.setHeader('Content-Type', 'text/html; charset=utf-8'); response.end(html);
});

async function settle(page) {
  await page.evaluate(async () => { for (let i = 0; i < 3; i++) await new Promise(requestAnimationFrame); });
}
async function seek(page, time) {
  await page.locator('video').evaluate((video, seconds) => { video.currentTime = seconds; }, time);
  await page.waitForFunction(seconds => {
    const video = document.querySelector('video');
    return !video.seeking && video.readyState >= 2 && Math.abs(video.currentTime - seconds) < .03;
  }, time);
  await settle(page);
}
async function playback(page) {
  return page.locator('video').evaluate(video => ({
    time: video.currentTime, paused: video.paused, rate: video.playbackRate,
    events: [...window.__mediaEvents], wall: performance.now(),
  }));
}
async function clearMediaEvents(page) { await page.evaluate(() => { window.__mediaEvents = []; }); }
async function box(page) { return page.locator('#quotePopover').boundingBox(); }
function closeTo(actual, expected, label, tolerance = 1) {
  assert.ok(Math.abs(actual - expected) <= tolerance, `${label}: ${actual} vs ${expected}`);
}
function samePosition(actual, expected) {
  assert.ok(actual && expected, 'Popover has a visible bounding box');
  closeTo(actual.x, expected.x, 'Popover left'); closeTo(actual.y, expected.y, 'Popover top');
}
async function assertPinned(page, text = fixture.segments[0].text) {
  assert.equal(await page.locator('#quotePopover').isVisible(), true, 'Pinned quote remains visible');
  assert.equal(await page.locator('#quoteText').textContent(), text, 'Pinned content is retained');
}
async function pin(page, index = 0) {
  await page.locator(`#timelineSpeech [data-quote="${index}"]`).click();
  await assertPinned(page, fixture.segments[index].text);
}
async function dragTo(page, left, top) {
  const before = await box(page), heading = await page.locator('.quote-popover-heading').boundingBox();
  assert.ok(before && heading, 'Quote heading is visible before dragging');
  const x = heading.x + Math.min(35, heading.width / 3), y = heading.y + heading.height / 2;
  await page.mouse.move(x, y); await page.mouse.down();
  await page.mouse.move(x + left - before.x, y + top - before.y, { steps: 12 });
  await page.mouse.up(); await settle(page);
  return box(page);
}
async function dragPointerTo(page, x, y) {
  const heading = await page.locator('.quote-popover-heading').boundingBox();
  await page.mouse.move(heading.x + 25, heading.y + heading.height / 2); await page.mouse.down();
  await page.mouse.move(x, y, { steps: 14 }); await page.mouse.up(); await settle(page);
}
async function insideViewport(page) {
  const geometry = await page.evaluate(() => {
    const rect = selector => document.querySelector(selector).getBoundingClientRect().toJSON();
    const close = rect('#quoteClose');
    return { popover: rect('#quotePopover'), close, width: innerWidth, height: innerHeight,
      reachable: document.elementFromPoint(close.left + close.width / 2, close.top + close.height / 2)?.closest('#quoteClose') != null };
  });
  for (const [name, rect] of [['popover', geometry.popover], ['close', geometry.close]]) {
    assert.ok(rect.left >= -1 && rect.top >= -1 && rect.right <= geometry.width + 1 && rect.bottom <= geometry.height + 1,
      `${name} stays within the viewport: ${JSON.stringify(rect)}`);
  }
  assert.equal(geometry.reachable, true, 'Close button is reachable by pointer');
  return geometry;
}
async function screenshot(page, name) {
  const filename = name + '.png'; await page.screenshot({ path: path.join(output, filename) });
  evidence.screenshots.push(filename); return filename;
}

async function freshPage() {
  // Every check gets independent storage, focus, media, bridge and timeline state.
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const page = await context.newPage(); page.setDefaultTimeout(8000);
  page.on('pageerror', error => evidence.errors.push(error.stack || error.message));
  await page.addInitScript(snapshot => {
    window.__snapshot = snapshot; window.__snapshotCalls = []; window.__mediaEvents = [];
    window.pywebview = { api: {
      ready: async () => ({ ok: true }), get_layout: async () => ({ ok: true, data: {} }),
      save_layout: async () => ({ ok: true }),
      get_snapshot: async known => {
        window.__snapshotCalls.push({ known, revision: window.__snapshot.revision });
        return { ok: true, data: known === window.__snapshot.revision
          ? { unchanged: true, revision: known } : structuredClone(window.__snapshot) };
      },
      copy_path: async () => ({ ok: true }), open_folder: async () => ({ ok: true }),
      open_document: async () => ({ ok: true }),
    } };
  }, structuredClone(fixture));
  try {
    await page.goto(origin + '/');
    await page.waitForFunction(() => document.querySelector('video').readyState >= 2
      && document.querySelectorAll('#timelineSpeech [data-quote]').length >= 2
      && window.__snapshotCalls.length > 0);
    await page.locator('video').evaluate(video => {
      video.pause(); video.playbackRate = 1.25;
      for (const type of ['seeking', 'play', 'pause', 'ratechange'])
        video.addEventListener(type, () => window.__mediaEvents.push(type));
    });
    await seek(page, 3.5);
    if (await page.locator('#follow').getAttribute('aria-pressed') === 'true') await page.locator('#follow').click();
    await clearMediaEvents(page);
    return { context, page };
  } catch (error) { await context.close(); throw error; }
}
async function check(name, task) {
  let context, page;
  const entry = { name, pass: false };
  try {
    ({ context, page } = await freshPage());
    const errorsBefore = evidence.errors.length;
    entry.details = await task(page);
    assert.equal(evidence.errors.length, errorsBefore, 'No browser exception during this check');
    entry.pass = true;
  } catch (error) {
    entry.error = error.stack || String(error); console.error(`FAIL ${name}: ${entry.error}`);
    if (page) { try { entry.failure_screenshot = await screenshot(page, name + '-FAILED'); } catch {} }
  } finally { if (context) await context.close(); }
  evidence.checks.push(entry);
}

async function main() {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ channel: 'msedge', headless: true });

  await check('hover-is-transient-and-does-not-seek', async page => {
    const before = await playback(page);
    await page.locator('#timelineSpeech [data-quote="0"]').hover(); await assertPinned(page);
    await screenshot(page, 'hover-preview');
    await page.locator('#title').hover();
    assert.equal(await page.locator('#quotePopover').isHidden(), true, 'Unpinned hover leaves no fixed quote');
    const after = await playback(page);
    closeTo(after.time, before.time, 'Hover leaves time unchanged', .01);
    assert.equal(after.paused, true); assert.deepEqual(after.events, []);
    return { before, after };
  });

  await check('click-pins-with-only-explicit-close-control', async page => {
    const before = await playback(page); await pin(page);
    await page.locator('#title').hover(); await assertPinned(page);
    assert.equal(await page.locator('#quotePopover button').count(), 1);
    assert.equal(await page.locator('#quoteClose').isVisible(), true);
    const text = await page.locator('#quotePopover').textContent();
    assert.ok(!text.includes('已固定') && !text.includes('定位到此处'));
    const after = await playback(page); closeTo(after.time, before.time, 'Pin does not seek', .01);
    assert.equal(after.paused, before.paused); assert.deepEqual(after.events, []);
    return { before, after, geometry: await insideViewport(page) };
  });

  await check('heading-drag-preserves-paused-media-and-user-position', async page => {
    await pin(page); await clearMediaEvents(page);
    const before = await playback(page), original = await box(page);
    const moved = await dragTo(page, 280, 170);
    assert.ok(Math.abs(moved.x - original.x) > 100, 'Heading drag actually moves the popover');
    closeTo(moved.x, 280, 'User chosen left'); closeTo(moved.y, 170, 'User chosen top');
    const after = await playback(page); closeTo(after.time, before.time, 'Drag does not seek', .01);
    assert.equal(after.paused, true); assert.equal(after.rate, before.rate); assert.deepEqual(after.events, []);
    assert.equal(await page.locator('#inputTimeline').evaluate(el => el.classList.contains('is-scrubbing')), false);
    await page.locator('#title').hover(); samePosition(await box(page), moved); await assertPinned(page);
    await screenshot(page, 'pinned-dragged'); return { original, moved, before, after };
  });

  await check('heading-drag-preserves-playing-media-and-speed', async page => {
    await pin(page); await dragTo(page, 300, 180);
    await page.locator('.plyr__controls [data-plyr=play]').click();
    // paused flips synchronously, before the browser dispatches the play event.
    // Establish playback first so that its queued startup event is not wrongly
    // attributed to the later popover drag.
    await page.waitForFunction(() => !document.querySelector('video').paused
      && window.__mediaEvents.includes('play') && document.querySelector('video').readyState >= 3);
    await settle(page);
    await clearMediaEvents(page); const before = await playback(page);
    await dragTo(page, 430, 270); const after = await playback(page);
    assert.equal(after.paused, false); assert.equal(after.rate, before.rate); assert.deepEqual(after.events, []);
    assert.ok(after.time >= before.time, 'Playback keeps progressing');
    const expectedElapsed = (after.wall - before.wall) / 1000 * before.rate;
    closeTo(after.time - before.time, expectedElapsed, 'Time advances naturally, without a seek', .25);
    await assertPinned(page); await screenshot(page, 'drag-while-playing'); return { before, after };
  });

  await check('body-text-selection-never-drags-or-seeks', async page => {
    await pin(page); await dragTo(page, 280, 170); await clearMediaEvents(page);
    const before = await box(page), mediaBefore = await playback(page);
    const points = await page.locator('#quoteText').evaluate(element => {
      const text = element.firstChild;
      const char = offset => { const range = document.createRange(); range.setStart(text, offset); range.setEnd(text, offset + 1); return range.getBoundingClientRect(); };
      const first = char(0), last = char(8);
      window.getSelection().removeAllRanges();
      return { x1: first.left + 1, y1: first.top + first.height / 2, x2: last.right - 1, y2: last.top + last.height / 2 };
    });
    await page.mouse.move(points.x1, points.y1); await page.mouse.down();
    await page.mouse.move(points.x2, points.y2, { steps: 10 }); await page.mouse.up(); await settle(page);
    const selected = await page.evaluate(() => ({ text: getSelection().toString(),
      inside: document.querySelector('#quoteText').contains(getSelection().anchorNode)
        && document.querySelector('#quoteText').contains(getSelection().focusNode) }));
    assert.ok(selected.text.length >= 4, `Actual pointer selection contains text: ${JSON.stringify(selected)}`);
    assert.equal(selected.inside, true); samePosition(await box(page), before);
    const after = await playback(page); closeTo(after.time, mediaBefore.time, 'Selecting text does not seek', .01);
    assert.equal(after.paused, true); assert.deepEqual(after.events, []); await assertPinned(page);
    await screenshot(page, 'body-selection'); return { selected, before, after };
  });

  await check('outside-escape-scroll-seek-tabs-and-polling-retain-pin', async page => {
    await pin(page); const position = await dragTo(page, 280, 170), checkpoints = [];
    const retained = async action => { await settle(page); await assertPinned(page); samePosition(await box(page), position); checkpoints.push(action); };
    await page.locator('#title').click(); await retained('outside click');
    await page.keyboard.press('Escape'); await retained('Escape');
    const timeline = await page.locator('#inputTimeline').boundingBox();
    await page.mouse.move(timeline.x + timeline.width - 18, timeline.y + 110); await page.mouse.wheel(0, 280);
    await retained('content wheel');
    const scale = await page.locator('#timelineScale').textContent();
    const horizontal = await page.locator('.timeline-horizontal-scroll').boundingBox();
    await page.mouse.move(horizontal.x + 15, timeline.y + 110); await page.mouse.wheel(0, -180);
    await page.waitForFunction(value => document.querySelector('#timelineScale').textContent !== value, scale);
    await retained('ruler zoom');
    await seek(page, 12); await retained('video seek');
    await page.locator('#transcriptTab').click(); await retained('transcript tab');
    await page.locator('#inputTab').click(); await retained('input tab');
    await page.evaluate(() => {
      window.__snapshot.title = '收到轮询快照 · 合成验收'; window.__snapshot.session_name = window.__snapshot.title;
      window.__snapshot.segments[2].text = '另一个时间段更新了转写，不应关闭已经固定的原话。';
      window.__snapshot.revision = 'polling-change';
    });
    await page.waitForFunction(() => document.querySelector('#title').textContent === '收到轮询快照 · 合成验收');
    await retained('changed snapshot');
    const count = await page.evaluate(() => window.__snapshotCalls.length);
    await page.waitForFunction(count => window.__snapshotCalls.length > count
      && window.__snapshotCalls.at(-1).known === 'polling-change', count);
    await retained('unchanged periodic snapshot');
    await screenshot(page, 'persistent-after-polling');
    return { position, checkpoints, snapshotCalls: await page.evaluate(() => window.__snapshotCalls) };
  });

  await check('hover-does-not-replace-pin-but-another-click-does-without-reposition', async page => {
    await pin(page); const position = await dragTo(page, 280, 170);
    const before = await playback(page);
    await page.locator('#timelineSpeech [data-quote="1"]').hover(); await assertPinned(page);
    samePosition(await box(page), position);
    await page.locator('#timelineSpeech [data-quote="1"]').click(); await assertPinned(page, fixture.segments[1].text);
    samePosition(await box(page), position);
    const after = await playback(page); closeTo(after.time, before.time, 'Quote replacement does not seek', .01);
    assert.equal(after.paused, true); assert.deepEqual(after.events, []);
    const time = await page.locator('#quoteTime').textContent(); assert.ok(time.includes('03.2') && time.includes('04.4'));
    await screenshot(page, 'different-quote-same-position'); return { position, time, before, after };
  });

  await check('drag-clamps-to-every-edge-and-close-stays-reachable', async page => {
    await pin(page); const bounds = [], viewport = page.viewportSize();
    for (const [x, y] of [[1, 1], [viewport.width - 1, 1], [viewport.width - 1, viewport.height - 1], [1, viewport.height - 1]]) {
      await dragPointerTo(page, x, y); await assertPinned(page); bounds.push(await insideViewport(page));
    }
    await screenshot(page, 'clamped-bottom-left'); return { bounds };
  });

  await check('shrinking-window-clamps-long-quote-and-keeps-close-visible', async page => {
    const longText = '这是合成的长原话，用于检查缩小窗口后正文可滚动、顶部关闭按钮仍可操作。'.repeat(36);
    await page.evaluate(text => {
      window.__snapshot.segments[0].text = text; window.__snapshot.revision = 'long-quote';
    }, longText);
    await page.waitForFunction(text => document.querySelector('#lines .segment-text').textContent === text, longText);
    await page.locator('#timelineSpeech [data-quote="0"]').click(); await assertPinned(page, longText);
    await dragPointerTo(page, 1439, 899);
    const bounds = [await insideViewport(page)];
    for (const viewport of [{ width: 980, height: 720 }, { width: 560, height: 540 }]) {
      await page.setViewportSize(viewport); await settle(page); await assertPinned(page, longText);
      bounds.push(await insideViewport(page));
    }
    const body = await page.locator('#quoteText').boundingBox();
    await page.mouse.move(body.x + 30, Math.min(body.y + 70, 400)); await page.mouse.wheel(0, 800); await settle(page);
    const afterScroll = await insideViewport(page); await assertPinned(page, longText);
    await screenshot(page, 'long-quote-small-window');
    await page.locator('#quoteClose').click(); assert.equal(await page.locator('#quotePopover').isHidden(), true);
    return { bounds, afterScroll };
  });

  await check('explicit-close-clears-pin-and-hover-returns-to-transient', async page => {
    await pin(page); await dragTo(page, 280, 170);
    await page.locator('#quoteClose').click(); assert.equal(await page.locator('#quotePopover').isHidden(), true);
    assert.equal(await page.locator('#timelineSpeech .pinned').count(), 0);
    await page.locator('#timelineSpeech [data-quote="1"]').hover(); await assertPinned(page, fixture.segments[1].text);
    await page.locator('#title').hover(); assert.equal(await page.locator('#quotePopover').isHidden(), true);
    await page.locator('#timelineSpeech [data-quote="1"]').click(); await assertPinned(page, fixture.segments[1].text);
    await page.locator('#quoteClose').click(); assert.equal(await page.locator('#quotePopover').isHidden(), true);
    return { explicitCloseAndTransientHover: true };
  });
}

main().catch(error => {
  evidence.errors.push(error.stack || String(error)); console.error(error);
}).finally(async () => {
  if (browser) await browser.close();
  if (server.listening) await new Promise(resolve => server.close(resolve));
  evidence.finished_at = new Date().toISOString();
  evidence.passed = evidence.checks.length === 10 && evidence.checks.every(item => item.pass) && evidence.errors.length === 0;
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, 'acceptance.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify(evidence, null, 2));
  if (!evidence.passed) process.exitCode = 1;
});
