// Split Zhuque Fangsong (SIL OFL 1.1) into unicode-range woff2 chunks for self-hosted web use.
// Run: npm run fonts   (writes public/fonts/zhuque/result.css + chunks)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { fontSplit } from 'cn-font-split';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..', '..');
const src = path.join(root, 'data', 'raw', 'fonts', 'zhuque', 'ZhuqueFangsong-Regular.ttf');
const out = path.resolve(here, '..', 'public', 'fonts', 'zhuque');

if (!fs.existsSync(src)) {
  console.error(`missing ${src}; download ZhuqueFangsong from https://github.com/TrionesType/zhuque/releases`);
  process.exit(1);
}
fs.rmSync(out, { recursive: true, force: true });
const input = new Uint8Array(fs.readFileSync(src));
await fontSplit({
  input,
  outDir: out,
  css: { fontFamily: 'Zhuque Fangsong', fontWeight: '400', fontStyle: 'normal', fontDisplay: 'swap' },
  testHtml: false,
  reporter: false,
  silent: true,
});
const license = path.join(root, 'data', 'raw', 'fonts', 'OFL-Zhuque.txt');
if (fs.existsSync(license)) fs.copyFileSync(license, path.join(out, 'OFL.txt'));
const files = fs.readdirSync(out);
console.log(`Zhuque Fangsong split into ${files.filter((f) => f.endsWith('.woff2')).length} woff2 chunks -> ${out}`);
