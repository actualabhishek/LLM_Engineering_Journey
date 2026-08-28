#!/usr/bin/env node
// Generates one image via a Gemini image model, routed through OpenRouter's
// dedicated Image API, and writes it to disk.
// Usage: node generate_image.mjs "<prompt text>" "<output-file-path.png>"
// Requires OPENROUTER_API_KEY in the environment.

const [, , prompt, outPath] = process.argv;

if (!prompt || !outPath) {
  console.error('Usage: node generate_image.mjs "<prompt>" "<output-file-path>"');
  process.exit(1);
}

const apiKey = process.env.OPENROUTER_API_KEY;
if (!apiKey) {
  console.error('OPENROUTER_API_KEY is not set.');
  process.exit(1);
}

const model = process.env.OPENROUTER_IMAGE_MODEL || 'google/gemini-2.5-flash-image';
const aspectRatio = process.env.OPENROUTER_IMAGE_ASPECT_RATIO || '16:9';
const resolution = process.env.OPENROUTER_IMAGE_RESOLUTION || '2K';
const quality = process.env.OPENROUTER_IMAGE_QUALITY || 'high';

const res = await fetch('https://openrouter.ai/api/v1/images', {
  method: 'POST',
  headers: {
    Authorization: `Bearer ${apiKey}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    model,
    prompt,
    n: 1,
    aspect_ratio: aspectRatio,
    resolution,
    quality,
  }),
});

if (!res.ok) {
  const text = await res.text().catch(() => '');
  console.error(`OpenRouter image API error ${res.status}: ${text}`);
  process.exitCode = 1;
} else {
  const data = await res.json();
  const image = data?.data?.[0];

  if (!image?.b64_json) {
    console.error('No image data in OpenRouter response.');
    console.error(JSON.stringify(data).slice(0, 2000));
    process.exitCode = 1;
  } else {
    const buffer = Buffer.from(image.b64_json, 'base64');
    const { writeFileSync } = await import('node:fs');
    writeFileSync(outPath, buffer);
    console.log(outPath);
  }
}
