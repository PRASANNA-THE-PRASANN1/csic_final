/**
 * Download face-api.js models required for layered verification.
 * Run: node scripts/download_models.js
 */
const https = require('https');
const fs = require('fs');
const path = require('path');

const MODELS_DIR = path.join(__dirname, '..', 'public', 'models');
const CDN = 'https://raw.githubusercontent.com/justadudewhohacks/face-api.js/master/weights';

const FILES = [
  // SSD MobileNet v1 — accurate face detection for framing
  'ssd_mobilenetv1_model-shard1',
  'ssd_mobilenetv1_model-shard2',
  'ssd_mobilenetv1_model-weights_manifest.json',
  // Face Landmark 68 Tiny — eye/nose/jaw landmarks for blink + head pose
  'face_landmark_68_tiny_model-shard1',
  'face_landmark_68_tiny_model-weights_manifest.json',
  // Face Expression — smile/neutral classification
  'face_expression_model-shard1',
  'face_expression_model-weights_manifest.json',
];

function download(url, dest) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    https.get(url, (res) => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        download(res.headers.location, dest).then(resolve).catch(reject);
        return;
      }
      res.pipe(file);
      file.on('finish', () => { file.close(); resolve(); });
    }).on('error', (err) => { fs.unlink(dest, () => {}); reject(err); });
  });
}

async function main() {
  fs.mkdirSync(MODELS_DIR, { recursive: true });
  for (const f of FILES) {
    const dest = path.join(MODELS_DIR, f);
    if (fs.existsSync(dest)) {
      console.log(`  ✓ ${f} (exists)`);
      continue;
    }
    const url = `${CDN}/${f}`;
    console.log(`  ↓ ${f}`);
    try {
      await download(url, dest);
      console.log(`  ✓ ${f}`);
    } catch (err) {
      console.error(`  ✗ ${f}: ${err.message}`);
    }
  }
  console.log('\nDone!');
}

main();
