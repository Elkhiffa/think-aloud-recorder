'use strict';

/** Production review DOM/CSS in real headless Edge; synthetic media/input only.
 * Run: node tests/test_device_recent_browser.cjs (PLAYWRIGHT_MODULE may be set).
 * Evidence: work/device-recent, or TAR_DEVICE_RECENT_OUTPUT. Never captures input.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const output = path.resolve(process.env.TAR_DEVICE_RECENT_OUTPUT || path.join(root, 'work/device-recent'));
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const media = fs.readFileSync(path.join(root, 'docs/prototypes/input-review/demo.mp4'));
const intervals = [];
function interval(device, code, start, end, extra = {}) {
  intervals.push({ id: `${device}-${code}-${start}`, device, code, kind: 'button', start, end, ...extra });
}
// A separate, labelled synthetic hold keeps the device panel visible after the
// keys under test expire. It never overlaps any of the controls asserted below.
interval('keyboard', 'Space', .1, 31);
for (const [device, code, extra] of [
  ['keyboard', 'KeyW', {}], ['keyboard', 'F13', {}],
  ['mouse', 'MouseLeft', {}], ['mouse', 'MouseX1', {}],
  ['mouse', 'MouseMove', { kind: 'motion', value: .6, direction: '↗' }],
  ['xbox', 'A', {}], ['xbox', 'Menu', {}],
  ['xbox', 'LT', { kind: 'trigger', value: .65 }],
  ['xbox', 'LeftStick', { kind: 'axis', value: .7, x: .7, y: 0, direction: '→' }],
  ['dualsense', 'Cross', {}], ['dualsense', 'Options', {}],
  ['dualsense', 'L2', { kind: 'trigger', value: .8 }],
  ['dualsense', 'RightStick', { kind: 'axis', value: .6, x: 0, y: -.6, direction: '↑' }],
]) interval(device, code, 1, 2, extra);
for (const [device, code] of [['keyboard', 'KeyE'], ['mouse', 'MouseRight'], ['xbox', 'B'], ['dualsense', 'Circle']])
  interval(device, code, 1.3, 3.25);
interval('keyboard', 'KeyQ', 6, 6.2);
interval('keyboard', 'KeyQ', 6.8, 7.4);
interval('dualsense', 'Cross', 13, 13.5);
interval('xbox', 'A', 14, 14.5);
interval('keyboard', 'KeyE', 15, 15.5);
const fixture = {
  title: '设备按下与松开渐淡 · 合成验收', game: '合成输入', test: true, desktop: true,
  created: '2026-09-24T15:00:00', revision: 'device-recent-1', video: '/demo.mp4',
  segments: [{ start: 1, end: 4, text: '合成设备高亮验收，不包含实际按键或私人录音。' }],
  transcription: { state: 'ready' },
  inputs: { version: 1, state: 'complete', duration: 32, timebase: 'video_seconds', intervals, gaps: [] },
};
const sources = Object.fromEntries(['player.html', 'ui/review.js', 'ui/review.css'].map(file => [file, read(file)]));
const substitutions = {
  TITLE: fixture.title, DATA: JSON.stringify(fixture), CSS: sources['ui/review.css'], JS: sources['ui/review.js'],
  PLYR_CSS: read('ui/vendor/plyr/plyr.css'), PLYR_JS: read('ui/vendor/plyr/plyr.min.js'),
  PLYR_SVG: read('ui/vendor/plyr/plyr.svg'), LICENSE: 'Synthetic device recent browser acceptance',
};
const html = sources['player.html'].replace(/%%([A-Z_]+)%%/g, (_, name) => substitutions[name]);
const report = {
  scope: 'Actual production DOM, CSS/computed paint colors and HTML video clock in headless Edge. Synthetic bridge, media and device intervals. No native WebView2/OBS/device capture acceptance.',
  started_at: new Date().toISOString(), checks: [], screenshots: [], errors: [],
  source_sha256: Object.fromEntries(Object.entries(sources).map(([file, source]) =>
    [file, crypto.createHash('sha256').update(source).digest('hex')])),
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

function near(actual, expected, message, tolerance = .002) {
  assert.ok(Number.isFinite(actual) && Math.abs(actual - expected) <= tolerance,
    `${message}: actual=${actual}, expected=${expected}, tolerance=${tolerance}`);
}
async function settle(page) {
  await page.evaluate(async () => { for (let i = 0; i < 3; i++) await new Promise(requestAnimationFrame); });
}
async function seek(page, time) {
  await page.locator('video').evaluate((video, value) => { video.pause(); video.currentTime = value; }, time);
  await page.waitForFunction(value => { const video = document.querySelector('video');
    return !video.seeking && video.readyState >= 2 && Math.abs(video.currentTime - value) < .01;
  }, time);
  await settle(page);
}
async function select(page, device) { await page.locator('#deviceSelect').selectOption(device); await settle(page); }
async function screenshot(page, name) {
  const extra = page.locator('#deviceView .device-extra');
  if (await extra.count() && await extra.isVisible()) {
    const extraBox = await extra.boundingBox(), stateBox = await page.locator('#inputState').boundingBox();
    assert.ok(extraBox && stateBox, `${name}: extra keys and footer have rendered geometry`);
    assert.ok(extraBox.y + extraBox.height <= stateBox.y + .5,
      `${name}: extra keys overlap footer: bottom=${extraBox.y + extraBox.height}, footerTop=${stateBox.y}`);
  }
  const filename = `${name}.png`;
  await page.screenshot({ path: path.join(output, filename) }); report.screenshots.push(filename);
}
function selector(code, extra = false) { return `#deviceView [${extra ? 'data-extra-code' : 'data-control'}="${code}"]`; }
async function control(page, code, extra = false) {
  const locator = page.locator(selector(code, extra));
  const count = await locator.count();
  assert.ok(count <= 1, `One representation per control ${code}, found ${count}`);
  if (!count) return null;
  return locator.evaluate(el => {
    const style = getComputedStyle(el), rootStyle = getComputedStyle(document.documentElement);
    const raw = el instanceof SVGElement ? style.fill : style.backgroundColor;
    // Canvas resolves browser color-mix()/color(srgb ...) into actual sRGB bytes;
    // class names/custom properties alone are insufficient color evidence.
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    const rgba = color => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = color; ctx.fillRect(0, 0, 1, 1);
      return [...ctx.getImageData(0, 0, 1, 1).data]; };
    const color = rgba(raw), surface = rgba(rootStyle.getPropertyValue('--surface'));
    const alpha = color[3] / 255 * Number(style.opacity);
    return { active: el.classList.contains('active'), recent: el.classList.contains('recent'),
      strength: Number.parseFloat(style.getPropertyValue('--input-strength')),
      intensity: style.getPropertyValue('--input-intensity').trim(),
      color: raw, rgba: color, opacity: Number(style.opacity), accent: rgba(rootStyle.getPropertyValue('--accent')),
      activeKey: rgba(rootStyle.getPropertyValue('--active-key')),
      // A common surface backdrop makes changes in either fill or opacity
      // comparable. This is computed CSS paint evidence, not pixel sampling.
      composite: color.slice(0, 3).map((value, i) => value * alpha + surface[i] * (1 - alpha)),
      time: document.querySelector('video').currentTime, paused: document.querySelector('video').paused,
      theme: document.documentElement.dataset.theme,
      rect: el.getBoundingClientRect().toJSON(), display: style.display, visibility: style.visibility };
  });
}
function strength(result, expected, label, { extra = false, tolerance = .002 } = {}) {
  if (!result) { assert.ok(extra && expected === 0, `${label} unexpectedly missing`); return; }
  near(result.strength, expected, `${label} video-driven strength`, tolerance);
  assert.match(result.intensity, /%$/, `${label} intensity is a CSS percentage`);
  near(parseFloat(result.intensity), expected * 100, `${label} percentage matches strength`, tolerance * 100);
  assert.equal(result.active, expected === 1, `${label} active class`);
  assert.equal(result.recent, expected > 0 && expected < 1, `${label} recent class`);
}
function distance(a, b) { return Math.hypot(...a.map((value, i) => value - b[i])); }
function themeRed(result, label) {
  assert.ok(result.rect.width > 0 && result.rect.height > 0, `${label} has rendered geometry`);
  assert.notEqual(result.display, 'none'); assert.notEqual(result.visibility, 'hidden');
  // Dark theme intentionally has separate text-accent and key-fill reds. Use
  // the semantic key token and independently reject a non-red active palette.
  assert.ok(result.activeKey[0] > result.activeKey[1] * 1.25 && result.activeKey[0] > result.activeKey[2] * 1.25,
    `${label} theme key color is red, not neutral or another hue`);
  near(distance(result.rgba.slice(0, 3), result.activeKey.slice(0, 3)), 0, `${label} actual fill is theme key red`, 2);
  near(result.opacity, 1, `${label} full-strength opacity`);
}
const groups = [
  { name: 'keyboard', device: 'keyboard', targets: [['W'], ['F13', true]], secondary: 'E' },
  { name: 'mouse', device: 'keyboard', targets: [['MouseLeft'], ['MouseMove'], ['MouseX1', true]], secondary: 'MouseRight' },
  { name: 'xbox', device: 'xbox', targets: [['A'], ['LT'], ['LeftStick'], ['Menu', true]], secondary: 'B' },
  { name: 'dualsense', device: 'dualsense', targets: [['Cross'], ['L2'], ['RightStick'], ['Options', true]], secondary: 'Circle' },
];
async function fresh() {
  // Normal motion preference deliberately catches unwanted wall-clock CSS fades.
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'no-preference' });
  const page = await context.newPage(); page.setDefaultTimeout(8000);
  page.on('pageerror', error => report.errors.push(error.stack || error.message));
  await page.addInitScript(snapshot => {
    window.pywebview = { api: { ready: async () => ({ ok: true }),
      get_layout: async () => ({ ok: true, data: {} }), save_layout: async () => ({ ok: true }),
      get_snapshot: async known => ({ ok: true, data: known === snapshot.revision
        ? { unchanged: true, revision: known } : structuredClone(snapshot) }) } };
  }, fixture);
  try {
    await page.goto(origin + '/');
    await page.waitForFunction(() => document.querySelector('video').readyState >= 2 && document.querySelector('[data-input-id]'));
    await seek(page, .2);
    await page.locator('[data-input-mode="device"]').click(); await settle(page);
    return { context, page };
  } catch (error) { await context.close(); throw error; }
}
async function check(name, task) {
  const item = { name, pass: false }; let context, page;
  try { ({ context, page } = await fresh()); item.details = await task(page); item.pass = true; }
  catch (error) { item.error = error.stack || String(error); console.error(`FAIL ${name}: ${item.error}`);
    if (page) try { await screenshot(page, `${name}-FAILED`); } catch {} }
  finally { if (context) await context.close(); }
  report.checks.push(item);
}

async function main() {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch({ channel: 'msedge', headless: true });

  for (const group of groups) await check(`${group.name}-real-color-linear-release-and-expiry`, async page => {
    await select(page, group.device);
    const samples = [];
    for (const time of [1.5, 2, 2.5, 3, 3.9, 4.001]) {
      await seek(page, time);
      const expected = time < 2 ? 1 : Math.max(0, .7 * (1 - (time - 2) / 2));
      const controls = {};
      for (const [code, extra = false] of group.targets) {
        controls[code] = await control(page, code, extra);
        strength(controls[code], expected, `${group.name}/${code} at ${time}`, { extra });
        if (time === 1.5) themeRed(controls[code], `${group.name}/${code}`);
      }
      samples.push({ time, expected, controls });
      if ([1.5, 2, 3, 4.001].includes(time)) await screenshot(page, `${group.name}-${time}-seconds`);
    }
    for (const [code] of group.targets) {
      const active = samples[0].controls[code]; let previous = -1;
      for (const sample of samples.slice(1, -1)) {
        const measured = distance(sample.controls[code].composite, active.composite);
        assert.ok(measured > previous + .5, `${group.name}/${code} actual CSS paint fades continuously: ${previous} -> ${measured}`);
        previous = measured;
      }
    }
    await seek(page, 4.1);
    const separate = await control(page, group.secondary);
    strength(separate, .7 * (1 - .85 / 2), `${group.name} later key has independent expiry`);
    await seek(page, 5.251);
    strength(await control(page, group.secondary), 0, `${group.name} later key eventually expires`);
    return { samples, separate };
  });

  await check('retap-restores-full-theme-red-and-restarts-its-own-release-clock', async page => {
    await select(page, 'keyboard'); const samples = [];
    for (const [time, expected] of [[6.1, 1], [6.5, .595], [6.9, 1], [7.4, .7], [8.4, .35], [9.401, 0]]) {
      await seek(page, time); const result = await control(page, 'Q');
      strength(result, expected, `Q repeat tap at ${time}`); if (expected === 1) themeRed(result, 'Q repeat tap');
      samples.push(result);
    }
    await screenshot(page, 'retap-expired'); return samples;
  });

  await check('pause-freezes-strength-and-css-color-beyond-two-wall-seconds', async page => {
    await select(page, 'xbox'); await seek(page, 2.5);
    const before = await control(page, 'A'), extraBefore = await control(page, 'Menu', true);
    strength(before, .525, 'paused A');
    await page.waitForTimeout(2400); await settle(page);
    const after = await control(page, 'A'), extraAfter = await control(page, 'Menu', true);
    for (const [first, last] of [[before, after], [extraBefore, extraAfter]]) {
      assert.equal(last.paused, true); near(last.time, first.time, 'paused video time', .0001);
      near(last.strength, first.strength, 'paused strength', .00001);
      assert.deepEqual(last.rgba, first.rgba, 'paused actual fill remains unchanged');
      near(last.opacity, first.opacity, 'paused opacity', .00001);
    }
    await screenshot(page, 'paused-after-2400ms-wall-time'); return { before, after, extraBefore, extraAfter };
  });

  await check('backward-and-forward-seeks-rebuild-state-without-future-highlights', async page => {
    const samples = [];
    for (const group of groups) {
      await select(page, group.device);
      for (const [time, expected] of [[1.5, 1], [3, .35], [.2, 0], [3.5, .175], [10, 0]]) {
        await seek(page, time);
        for (const [code, extra = false] of group.targets) {
          const result = await control(page, code, extra);
          strength(result, expected, `${group.name}/${code} seek ${time}`, { extra });
          samples.push({ group: group.name, code, time, result });
        }
      }
    }
    await screenshot(page, 'seek-after-all-releases'); return samples;
  });

  await check('real-playback-advances-fade-and-rate-uses-video-seconds', async page => {
    await select(page, 'keyboard'); await seek(page, 1.8);
    await page.locator('video').evaluate(async video => { video.muted = true; await video.play(); });
    await page.waitForFunction(() => document.querySelector('video').currentTime >= 2.35);
    await page.locator('video').evaluate(video => video.pause()); await settle(page);
    const first = await control(page, 'W');
    strength(first, .7 * (1 - (first.time - 2) / 2), 'actual playback fade', { tolerance: .02 });
    await page.locator('video').evaluate(async video => { video.playbackRate = 2; await video.play(); });
    await page.waitForFunction(() => document.querySelector('video').currentTime >= 4.05);
    await page.locator('video').evaluate(video => video.pause()); await settle(page);
    const expired = await control(page, 'W'), independent = await control(page, 'E');
    strength(expired, 0, '2x playback expired primary key');
    strength(independent, .7 * (1 - (independent.time - 3.25) / 2), '2x playback separate key', { tolerance: .02 });
    await screenshot(page, 'real-playback-after-primary-expiry'); return { first, expired, independent };
  });

  await check('device-switching-auto-selection-and-both-themes-preserve-video-state', async page => {
    const measurements = [];
    for (const theme of ['light', 'dark']) {
      if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('#themeButton').click();
      for (const group of groups) {
        await select(page, group.device); await seek(page, 1.5);
        const active = {}, recent = {};
        for (const [code, extra = false] of group.targets) {
          active[code] = await control(page, code, extra);
          strength(active[code], 1, `${theme}/${group.name}/${code} active`);
          themeRed(active[code], `${theme}/${group.name}/${code}`);
        }
        await seek(page, 3);
        for (const [code, extra = false] of group.targets) {
          recent[code] = await control(page, code, extra);
          strength(recent[code], .35, `${theme}/${group.name}/${code} switch rebuilds release`);
          assert.ok(distance(active[code].composite, recent[code].composite) > 2, 'Recent fill actually differs in this theme');
        }
        measurements.push({ theme, device: group.name, active, recent });
        await screenshot(page, `${theme}-${group.name}-recent`);
      }
    }
    await select(page, 'auto');
    for (const [time, diagram, code] of [[13.2, '.controller.dualsense', 'Cross'], [14.2, '.controller.xbox', 'A'], [15.2, '.keyboard', 'E']]) {
      await seek(page, time); assert.equal(await page.locator(`#deviceView ${diagram}`).count(), 1);
      strength(await control(page, code), 1, `automatic device at ${time}`);
    }
    return measurements;
  });
}

main().catch(error => { report.errors.push(error.stack || String(error)); console.error(error); }).finally(async () => {
  if (browser) await browser.close();
  if (server.listening) await new Promise(resolve => server.close(resolve));
  report.finished_at = new Date().toISOString();
  report.passed = report.checks.length === 9 && report.checks.every(item => item.pass) && report.errors.length === 0;
  fs.mkdirSync(output, { recursive: true });
  fs.writeFileSync(path.join(output, 'acceptance.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ passed: report.passed, checks: report.checks.map(({ name, pass }) => ({ name, pass })), errors: report.errors, output }, null, 2));
  if (!report.passed) process.exitCode = 1;
});
