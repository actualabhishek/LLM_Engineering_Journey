import { MicVAD } from "@ricky0123/vad-web";
import { encodeWav } from "./wav-encoder";

const SAMPLE_RATE = 16000;

export async function createVad(
  onSpeechStart: () => void,
  onUtterance: (wav: Blob) => void
) {
  const vad = await MicVAD.new({
    baseAssetPath: "/",
    onnxWASMBasePath: "/",
    onSpeechStart,
    onSpeechEnd: (audio: Float32Array) => {
      onUtterance(encodeWav(audio, SAMPLE_RATE));
    },
  });

  return {
    start: () => vad.start(),
    pause: () => vad.pause(),
    destroy: () => vad.destroy(),
  };
}
