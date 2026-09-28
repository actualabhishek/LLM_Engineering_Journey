"use client";

import { useEffect, useRef, useState } from "react";
import { CaptionList } from "@/components/CaptionList";
import { SummaryCard } from "@/components/SummaryCard";
import { connect, type Caption, type Card } from "@/lib/websocket";
import { createPlaybackQueue } from "@/lib/playback";
import { createVad } from "@/lib/vad";

type Status = "idle" | "listening" | "speaking";

export default function Home() {
  const [started, setStarted] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const vadRef = useRef<Awaited<ReturnType<typeof createVad>> | null>(null);
  const clientRef = useRef<ReturnType<typeof connect> | null>(null);

  useEffect(() => {
    return () => {
      vadRef.current?.destroy();
      clientRef.current?.close();
    };
  }, []);

  async function handleStart() {
    setStarted(true);
    const playback = createPlaybackQueue((playing) =>
      setStatus(playing ? "speaking" : "listening")
    );

    const client = connect(
      (caption) => setCaptions((prev) => [...prev, caption]),
      (blob) => playback.enqueue(blob),
      (card) => setCards((prev) => [...prev, card]),
      (message) => setError(message)
    );
    clientRef.current = client;

    const vad = await createVad(
      () => {
        playback.stop();
        setStatus("listening");
      },
      (wav) => client.sendUtterance(wav)
    );
    vadRef.current = vad;
    vad.start();
  }

  return (
    <div className="flex flex-1 flex-col items-center px-4">
      <h1 className="text-3xl font-semibold mt-8 mb-4">Hotel Experience Assistant</h1>

      {!started ? (
        <>
          <button
            onClick={handleStart}
            className="rounded-full bg-blue-600 text-white px-8 py-3 text-lg font-medium"
          >
            Start
          </button>
          <p className="text-gray-500 text-sm mt-3 max-w-xs text-center">
            An AI assistant will process this conversation.
          </p>
        </>
      ) : (
        <p className="text-gray-600 mb-4">{status === "speaking" ? "Speaking…" : "Listening…"}</p>
      )}

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <CaptionList captions={captions} />

      <div className="w-full max-w-xl space-y-3 pb-8">
        {cards.map((card, i) => (
          <SummaryCard key={i} card={card} />
        ))}
      </div>
    </div>
  );
}
