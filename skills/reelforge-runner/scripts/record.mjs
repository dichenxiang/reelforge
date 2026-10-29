#!/usr/bin/env node
/**
 * 无人值守录屏：Playwright 打开 wvp 的 ?auto=1，按 SPACE 自动播完并录制。
 *
 *   node record.mjs --url "http://localhost:5174/?auto=1" \
 *     --duration 42 --out out/final.mp4 [--audio out/narration.mp3] \
 *     [--size 1920x1080] [--fps 30] [--keep]
 *
 * 注意：Playwright 只录画面，不录系统声音。
 * 需要声音就先用 mix_audio.py 拼一条旁白轨，用 --audio 传进来做混流；
 * 要严格音画同步，仍建议人在电脑前用 OBS 录（见 SKILL.md）。
 */
import { chromium } from 'playwright';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname, resolve } from 'node:path';

function arg(name, def = '') {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 ? process.argv[i + 1] : def;
}
const flag = (name) => process.argv.includes(`--${name}`);

const url = arg('url');
const duration = Number(arg('duration', '30'));
const out = resolve(arg('out', 'out/final.mp4'));
const size = arg('size', '1920x1080').split('x').map(Number);
const fps = Number(arg('fps', '30'));
const audio = arg('audio', '');
if (!url) {
  console.error('用法: node record.mjs --url <url> --duration <秒> --out <mp4> [--audio bgm.mp3]');
  process.exit(1);
}

const tmp = mkdtempSync(join(tmpdir(), 'reelforge-rec-'));
const ctx = await chromium.launchPersistentContext(join(tmp, 'profile'), {
  viewport: { width: size[0], height: size[1] },
  recordVideo: { dir: tmp, size: { width: size[0], height: size[1] } },
  args: ['--hide-scrollbars', '--force-device-scale-factor=1'],
});

const page = await ctx.newPage();
console.log(`[record] 打开 ${url}`);
await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
await page.waitForTimeout(1500);
await page.keyboard.press('Space');
console.log(`[record] 开始录制，预计 ${duration}s`);
await page.waitForTimeout((duration + 2) * 1000);
const video = page.video();
await ctx.close();

const src = video ? await video.path() : '';
if (!src || !existsSync(src)) {
  console.error('[record] 没拿到录制文件');
  process.exit(1);
}

mkdirSync(dirname(out), { recursive: true });
const ff = process.env.FFMPEG || 'ffmpeg';
const args = ['-nostdin', '-y', '-v', 'error', '-i', src];
if (audio) args.push('-i', resolve(audio));
args.push('-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', String(fps));
if (audio) args.push('-c:a', 'aac', '-b:a', '192k', '-shortest');
args.push(out);

const r = spawnSync(ff, args, { stdio: 'inherit' });
if (!flag('keep')) rmSync(tmp, { recursive: true, force: true });
if (r.status !== 0) process.exit(r.status || 1);
console.log(`[record] 完成：${out}`);
