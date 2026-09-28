export function createPlaybackQueue(onPlayingChange?: (playing: boolean) => void) {
  const queue: Blob[] = [];
  let current: HTMLAudioElement | null = null;

  function playNext() {
    const blob = queue.shift();
    if (!blob) {
      onPlayingChange?.(false);
      return;
    }
    onPlayingChange?.(true);
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    current = audio;
    audio.addEventListener("ended", () => {
      URL.revokeObjectURL(url);
      current = null;
      playNext();
    });
    audio.play();
  }

  return {
    enqueue(blob: Blob) {
      queue.push(blob);
      if (!current) playNext();
    },
    stop() {
      queue.length = 0;
      if (current) {
        current.pause();
        current = null;
      }
      onPlayingChange?.(false);
    },
  };
}
