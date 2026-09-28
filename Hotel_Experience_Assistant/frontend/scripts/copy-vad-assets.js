const fs = require("fs");
const path = require("path");

const publicDir = path.join(__dirname, "..", "public");
const vadDist = path.join(__dirname, "..", "node_modules", "@ricky0123", "vad-web", "dist");
const ortDist = path.join(__dirname, "..", "node_modules", "onnxruntime-web", "dist");

function copyMatching(dir, pattern) {
  for (const name of fs.readdirSync(dir)) {
    if (pattern.test(name)) {
      fs.copyFileSync(path.join(dir, name), path.join(publicDir, name));
    }
  }
}

copyMatching(vadDist, /\.onnx$/);
copyMatching(vadDist, /^vad\.worklet\.bundle\.min\.js$/);
copyMatching(ortDist, /\.(wasm|mjs)$/);

console.log("Copied VAD + onnxruntime-web assets to public/");
