"use client";

import { useEffect, useRef, useState } from "react";
import { CaptionList } from "@/components/CaptionList";
import { SummaryCard } from "@/components/SummaryCard";
import { Logo } from "@/components/Logo";
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
    setError(null);

    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const name = err instanceof DOMException ? err.name : "";
      if (name === "NotFoundError" || name === "OverconstrainedError") {
        setError("No microphone found. Please connect one and try again.");
      } else if (name === "NotAllowedError" || name === "SecurityError") {
        setError("Microphone access was blocked. Please allow it for this site and try again.");
      } else {
        setError("Could not access the microphone. Please try again.");
      }
      return;
    }

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

  const orbPulseClass =
    status === "listening" ? "orb-listening" : status === "speaking" ? "orb-speaking" : "";

  return (
    <div className="flex flex-1 flex-col items-center px-4">
      <div className="flex flex-col items-center gap-3 mt-10 mb-8">
        <Logo size={64} />
        <h1 className="font-serif text-3xl font-semibold text-parchment">Velvet Vista Hotel</h1>
      </div>

      {!started ? (
        <button
          onClick={handleStart}
          className="w-48 h-48 rounded-full border-2 border-gold text-parchment font-medium hover:border-gold-bright transition-colors"
          style={{
            background: "radial-gradient(circle at center, var(--velvet-deep) 0%, var(--velvet) 100%)",
          }}
        >
          Start
        </button>
      ) : (
        <div
          className={`w-48 h-48 rounded-full border-2 border-gold ${orbPulseClass}`}
          style={{
            background: "radial-gradient(circle at center, var(--velvet-deep) 0%, var(--velvet) 100%)",
          }}
        />
      )}

      <div className="flex flex-col items-center gap-1 mt-5 text-center">
        {started && (
          <p className="text-parchment/80">{status === "speaking" ? "Speaking…" : "Listening…"}</p>
        )}
        {!started && (
          <p className="text-parchment/60 text-sm max-w-xs">
            An AI assistant will process this conversation.
          </p>
        )}
      </div>

      {error && <p className="text-error text-sm mt-3">{error}</p>}

      <CaptionList captions={captions} />

      <div className="w-full max-w-xl space-y-3 pb-8">
        {cards.map((card, i) => (
          <SummaryCard key={i} card={card} />
        ))}
      </div>
    </div>
  );
}
