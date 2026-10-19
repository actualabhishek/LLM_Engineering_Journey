"use client";

import type { ReactNode } from "react";
import { DigitalTwin } from "./digital-twin";
import { TwinProvider, useTwin } from "./twin-provider";

function Frame({ children, email }: { children: ReactNode; email: string }) {
  const { open, setOpen, collapsed, toggleDock } = useTwin();

  return (
    <div className="frame" data-collapsed={collapsed} data-open={open}>
      <header className="topbar">
        <a href="#top" className="wordmark"><span aria-hidden="true">AS</span>Abhishek Suman</a>
        <nav aria-label="Sections">
          <a href="#work">Work</a>
          <a href="#capabilities">Skills</a>
          <a href="#experience">Experience</a>
        </nav>
        <div className="topbar-actions">
          <a className="plain" href={`mailto:${email}`}>Contact</a>
          <button type="button" className="assistant-toggle" onClick={toggleDock} aria-expanded={open || !collapsed}>
            Ask the Twin
          </button>
        </div>
      </header>

      <div className="body">
        <main className="main" id="top">{children}</main>
        <aside className="dock" aria-label="Digital Twin assistant">
          <DigitalTwin />
        </aside>
        <button type="button" className="scrim" aria-label="Close assistant" tabIndex={-1} onClick={() => setOpen(false)} />
      </div>

      <button type="button" className="fab" onClick={() => setOpen(true)}>Ask the Twin</button>
    </div>
  );
}

export function AppShell({ children, email }: { children: ReactNode; email: string }) {
  return (
    <TwinProvider>
      <Frame email={email}>{children}</Frame>
    </TwinProvider>
  );
}
