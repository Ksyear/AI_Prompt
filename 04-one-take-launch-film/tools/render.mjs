// Render launch-film.html to video: 60 fps, four sub-frames per frame blended with ffmpeg tmix.
// Each worker page renders one contiguous slice and pipes PNGs into its own ffmpeg; slices are
// concatenated and muxed with the mix.
//
// Usage: node tools/render.mjs [--url http://127.0.0.1:8917/launch-film.html] [--workers 4] [--out film.mp4] [--root .]
// Needs Playwright (with Chrome installed) and ffmpeg. Serve the folder over HTTP first.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { writeFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const HERE = path.resolve(arg('root', path.join(path.dirname(fileURLToPath(import.meta.url)), '..')));
const URL_ = arg('url', 'http://127.0.0.1:8917/launch-film.html');
const WORKERS = +arg('workers', 4), FPS = 60, SUB = 4;
const OUT = path.join(HERE, arg('out', 'film.mp4'));
const TMP = path.join(HERE, 'assets/render');
mkdirSync(TMP, { recursive: true });

const ffmpeg = (args, input) => new Promise((res, rej) => {
  const p = spawn('ffmpeg', args, { stdio: [input ? 'pipe' : 'ignore', 'ignore', 'inherit'] });
  p.on('close', c => (c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`))));
  if (input) input(p.stdin);
});

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--force-color-profile=srgb', '--hide-scrollbars'] });
const open = async () => {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1440 }, deviceScaleFactor: 1 });
  page.on('pageerror', e => console.error('pageerror', e.message));
  await page.goto(`${URL_}?render`, { waitUntil: 'load' });
  await page.evaluate(() => window.ready);
  return page;
};

const first = await open();
const DUR = await first.evaluate(() => window.DUR);
writeFileSync(path.join(HERE, 'sfx-cues.json'), JSON.stringify(await first.evaluate(() => window.SFX)));
const FRAMES = Math.min(Math.round(DUR * FPS), +arg('frames', Infinity));   // --frames limits a test render
const FROM = +arg('from', 0);                       // --from re-renders a tail only
const per = Math.ceil((FRAMES - FROM) / WORKERS);
const started = Date.now();
let done = 0;

async function worker(w, page) {
  const a = FROM + w * per, z = Math.min(FRAMES, a + per);
  const seg = path.join(TMP, `seg${w}.mp4`);
  await ffmpeg(['-v', 'error', '-y', '-f', 'image2pipe', '-framerate', String(FPS * SUB), '-c:v', 'png', '-i', '-',
    // frame k = mean of its four sub-frames (k + (j + .5) / 4) / 60, j = 0..3
    '-vf', `tmix=frames=${SUB},select='eq(mod(n\\,${SUB})\\,${SUB - 1})',setpts=N/${FPS}/TB`,
    '-r', String(FPS), '-c:v', 'libx264', '-preset', 'medium', '-crf', '10', '-pix_fmt', 'yuv420p', seg],
  async stdin => {
    for (let k = a; k < z; k++) {
      for (let j = 0; j < SUB; j++) {
        const t = (k + (j + 0.5) / SUB) / FPS;
        await page.evaluate(t => window.seek(t), t);
        const png = await page.screenshot({ type: 'png', clip: { x: 0, y: 0, width: 1440, height: 1440 } });
        if (!stdin.write(png)) await new Promise(r => stdin.once('drain', r));
      }
      done++;
      if (done % 60 === 0) {
        const s = (Date.now() - started) / 1000;
        console.log(`${done}/${FRAMES - FROM} frames · ${s.toFixed(0)} s · eta ${(s / done * (FRAMES - FROM - done)).toFixed(0)} s`);
      }
    }
    stdin.end();
  });
  return seg;
}

const pages = [first, ...(await Promise.all(Array.from({ length: WORKERS - 1 }, open)))];
const segs = await Promise.all(pages.map((p, w) => worker(w, p)));
await browser.close();

const list = path.join(TMP, 'segments.txt');
writeFileSync(list, segs.map(s => `file '${s}'`).join('\n'));
const video = path.join(TMP, arg('video', 'video.mp4'));
await ffmpeg(['-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list, '-c', 'copy', video]);
console.log(`video: ${FRAMES - FROM} frames in ${((Date.now() - started) / 1000).toFixed(0)} s → ${video}`);
