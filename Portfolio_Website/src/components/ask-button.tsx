"use client";

import type { ReactNode } from "react";
import { useTwin } from "./twin-provider";

export function AskButton({ question, className, children }: { question: string; className?: string; children: ReactNode }) {
  const { ask } = useTwin();
  return (
    <button type="button" className={className} onClick={() => ask(question)}>
      {children}
    </button>
  );
}
