#!/usr/bin/env node
// Uploads a local image file to Cloudinary and prints the resulting secure_url.
// Usage: node upload_cloudinary.mjs "<local-file-path>"
// Requires either CLOUDINARY_URL=cloudinary://<key>:<secret>@<cloud_name>
// or CLOUDINARY_CLOUD_NAME + CLOUDINARY_API_KEY + CLOUDINARY_API_SECRET.

import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';

const [, , filePath] = process.argv;
if (!filePath) {
  console.error('Usage: node upload_cloudinary.mjs "<local-file-path>"');
  process.exit(1);
}

function resolveCreds() {
  if (process.env.CLOUDINARY_URL) {
    const m = process.env.CLOUDINARY_URL.match(/^cloudinary:\/\/([^:]+):([^@]+)@(.+)$/);
    if (!m) {
      console.error('CLOUDINARY_URL is malformed. Expected cloudinary://<key>:<secret>@<cloud_name>');
      process.exit(1);
    }
    return { apiKey: m[1], apiSecret: m[2], cloudName: m[3] };
  }
  const { CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET } = process.env;
  if (CLOUDINARY_CLOUD_NAME && CLOUDINARY_API_KEY && CLOUDINARY_API_SECRET) {
    return { apiKey: CLOUDINARY_API_KEY, apiSecret: CLOUDINARY_API_SECRET, cloudName: CLOUDINARY_CLOUD_NAME };
  }
  console.error('No Cloudinary credentials found (CLOUDINARY_URL or CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET).');
  process.exit(1);
}

const { apiKey, apiSecret, cloudName } = resolveCreds();

const timestamp = Math.floor(Date.now() / 1000);
const folder = process.env.CLOUDINARY_FOLDER || 'postflow';
const paramsToSign = `folder=${folder}&timestamp=${timestamp}`;
const signature = createHash('sha1').update(paramsToSign + apiSecret).digest('hex');

const fileBuffer = readFileSync(filePath);
const form = new FormData();
form.append('file', new Blob([fileBuffer]), basename(filePath));
form.append('api_key', apiKey);
form.append('timestamp', String(timestamp));
form.append('folder', folder);
form.append('signature', signature);

const res = await fetch(`https://api.cloudinary.com/v1_1/${cloudName}/image/upload`, {
  method: 'POST',
  body: form,
});

if (!res.ok) {
  const text = await res.text().catch(() => '');
  console.error(`Cloudinary upload error ${res.status}: ${text}`);
  process.exitCode = 1;
} else {
  const data = await res.json();
  if (!data.secure_url) {
    console.error('No secure_url in Cloudinary response.');
    console.error(JSON.stringify(data).slice(0, 2000));
    process.exitCode = 1;
  } else {
    console.log(data.secure_url);
  }
}
