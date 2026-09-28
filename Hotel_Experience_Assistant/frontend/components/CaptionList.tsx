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
      className="flex-1 w-full max-w-xl overflow-y-auto space-y-2 py-4"
    >
      {captions.map((caption, i) => (
        <p
          key={i}
          className={
            caption.role === "guest"
              ? "text-right text-blue-700"
              : "text-left text-gray-800"
          }
        >
          {caption.text}
        </p>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
