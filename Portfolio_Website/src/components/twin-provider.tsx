"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";

type Submit = (question: string) => void;

type TwinContextValue = {
  /** Mobile drawer state. */
  open: boolean;
  setOpen: (open: boolean) => void;
  /** Desktop dock state. */
  collapsed: boolean;
  toggleDock: () => void;
  /** Opens the assistant and sends a question to it. */
  ask: (question: string) => void;
  /** The chat registers its submit handler here so any button on the page can drive it. */
  registerSubmit: (submit: Submit | null) => void;
};

const TwinContext = createContext<TwinContextValue | null>(null);

export function TwinProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const submitRef = useRef<Submit | null>(null);

  const registerSubmit = useCallback((submit: Submit | null) => {
    submitRef.current = submit;
  }, []);

  const ask = useCallback((question: string) => {
    setOpen(true);
    setCollapsed(false);
    submitRef.current?.(question);
  }, []);

  const toggleDock = useCallback(() => {
    // Docked on wide screens, drawer on narrow ones; each keeps its own state.
    if (window.matchMedia("(min-width: 1100px)").matches) setCollapsed((current) => !current);
    else setOpen((current) => !current);
  }, []);

  const value = useMemo(
    () => ({ open, setOpen, collapsed, toggleDock, ask, registerSubmit }),
    [open, collapsed, toggleDock, ask, registerSubmit],
  );

  return <TwinContext.Provider value={value}>{children}</TwinContext.Provider>;
}

export function useTwin() {
  const value = useContext(TwinContext);
  if (!value) throw new Error("useTwin must be used inside TwinProvider");
  return value;
}
