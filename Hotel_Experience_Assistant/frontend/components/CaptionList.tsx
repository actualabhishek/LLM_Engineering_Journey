"use client";

import { useEffect, useRef } from "react";
import type { Caption } from "@/lib/websocket";

export function CaptionList({ captions }: { captions: Caption[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [captions.length]);

  return (
    <div
      data-testid="captions"
      className="flex-1 w-full max-w-xl overflow-y-auto space-y-3 py-4"
    >
      {captions.map((caption, i) => {
        const isGuest = caption.role === "guest";
        const speakerChanged = i === 0 || captions[i - 1].role !== caption.role;

        return (
          <div key={i} className={isGuest ? "flex flex-col items-end" : "flex flex-col items-start"}>
            {!isGuest && speakerChanged && (
              <span className="font-serif italic text-gold text-sm mb-1 px-1">Divya</span>
            )}
            <p
              className={
                isGuest
                  ? "bg-wine text-parchment rounded-lg px-4 py-2 max-w-[85%]"
                  : "bg-velvet-deep text-parchment border-l-2 border-gold rounded-r-lg px-4 py-2 max-w-[85%]"
              }
            >
              {caption.text}
            </p>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
}
