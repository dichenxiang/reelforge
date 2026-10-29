#!/usr/bin/env node
/**
 * record_auto.mjs —— 逐拍网页录屏（通用版）
 *
 * 打开任意「按步推进」的网页（wvp / 自建 presentation），点一下开始，
 * 每 40ms 采样当前章节/步，并输出时间戳；成片音频由 mix_timeline.py 贴回。
 *
 * 用法：
 *   node record_auto.mjs --url "http://127.0.0.1:4176/?auto=1" --duration 150 \
 *        --out out/raw.webm --timeline out/timeline.json
 *
 * 可选：
 *   --size 1920x1080        画幅（默认 1920x1080）
 *   --start center|selector 开始方式（默认 center 点画面中心；也可点某个选择器）
 *   --start-selector ".auto-gate"
 *   --chapter-selector ".pb-chapter"  --pip-selector ".pb-pip-on"
 *   --no-marker             不画右下角同步白块（默认画，供 mix_timeline 对齐）
 *   --browser msedge|chromium  默认优先本机 Edge（免下载），回退 playwright chromium
 *
 * 页面没有 .pb-* 元素也能录：时间轴会退化为空样本，mix_timeline 会改为等距切分。
 */
import { chromium } from 'playwright-core';
import { mkdirSync, writeFileSync, mkdtempSync, copyFileSync, renameSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const arg = (n, d = '') => {
  const i = process.argv.indexOf(`--${n}`);
  return i > -1 ? process.argv[i + 1] : d;
};
const has = (n) => process.argv.includes(`--${n}`);

const url = arg('url');
if (!url) {
  console.error('用法: node record_auto.mjs --url <url> --duration <秒> --out <mp4|webm>');
  process.exit(1);
}
const duration = Number(arg('duration', '150'));
const out = arg('out', 'out/raw.webm');
const [W, H] = arg('size', '1920x1080').split('x').map(Number);
const startMode = arg('start', 'center');
const startSelector = arg('start-selector', '.auto-gate');
const chapterSel = arg('chapter-selector', '.pb-chapter');
const pipSel = arg('pip-selector', '.pb-pip-on');
const browserName = arg('browser', 'msedge');
const marker = !has('no-marker');
const tmp = mkdtempSync(join(tmpdir(), 'rf-rec-'));

const launchOpts = {
  headless: true,
  viewport: { width: W, height: H },
  recordVideo: { dir: tmp, size: { width: W, height: H } },
  args: ['--hide-scrollbars', '--force-device-scale-factor=1', '--autoplay-policy=no-user-gesture-required'],
};
let ctx;
try {
  ctx = await chromium.launchPersistentContext(join(tmp, 'profile'), { ...launchOpts, channel: browserName });
} catch (e) {
  console.warn(`[rec] ${browserName} 起不来（${e.message.split('\n')[0]}），回退 playwright chromium`);
  ctx = await chromium.launchPersistentContext(join(tmp, 'profile'), launchOpts);
}

const page = await ctx.newPage();
page.on('console', (m) => { if (m.type() === 'error') console.log('[console]', m.text()); });
page.on('pageerror', (e) => console.log('[pageerror]', e.message));

await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(1500);

const samples = [];
let stop = false;
const poll = (async () => {
  while (!stop) {
    try {
      const s = await page.evaluate(([cs, ps]) => {
        const chs = [...document.querySelectorAll(cs)];
        if (!chs.length) return { ci: -1, step: -1 };
        const ci = chs.findIndex((n) => n.classList.contains('pb-active'));
        const on = chs[ci] ? chs[ci].querySelectorAll(ps).length : -1;
        return { ci, step: on - 1 };
      }, [chapterSel, pipSel]);
      samples.push({ t: Date.now(), ...s });
    } catch { /* page may be closing */ }
    await new Promise((r) => setTimeout(r, 40));
  }
})();

const tStart = Date.now();
if (startMode === 'selector') {
  const el = await page.$(startSelector);
  if (el) await el.click();
  else { console.warn(`[rec] 找不到 ${startSelector}，改为点画面中心`); await page.mouse.click(W / 2, H / 2); }
} else {
  await page.mouse.click(W / 2, H / 2);
}
if (marker) {
  await page.evaluate(() => {
    const d = document.createElement('div');
    d.id = '__sync_mark';
    d.style.cssText = 'position:fixed;right:0;bottom:0;width:160px;height:160px;background:#fff;z-index:2147483647;pointer-events:none';
    document.body.appendChild(d);
    setTimeout(() => d.remove(), 140);
  });
}
console.log(`[rec] start@${tStart} samples=${samples.length} waiting ${duration}s`);
await page.waitForTimeout((duration + 2) * 1000);
stop = true;
await poll;

const video = page.video();
await ctx.close();
const src = video ? await video.path() : '';
if (!src) { console.error('[rec] 没有拿到录制文件'); process.exit(1); }
mkdirSync(join(out, '..'), { recursive: true });
copyFileSync(src, out);
writeFileSync(out.replace(/\.\w+$/, '') + '.timeline.json', JSON.stringify({
  tStart, duration, size: [W, H], marker, samples,
}, null, 1));
console.log(`[rec] video -> ${out}`);
console.log(`[rec] timeline -> ${out.replace(/\.\w+$/, '')}.timeline.json  (${samples.length} samples)`);

// 兼容旧调用：--timeline 指定路径时另存一份
const tl = arg('timeline');
if (tl && tl !== out.replace(/\.\w+$/, '') + '.timeline.json') {
  copyFileSync(out.replace(/\.\w+$/, '') + '.timeline.json', tl);
  console.log(`[rec] timeline copy -> ${tl}`);
}
