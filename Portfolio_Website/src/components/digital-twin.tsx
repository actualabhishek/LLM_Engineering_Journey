"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTwin } from "./twin-provider";

type Message = { role: "visitor" | "twin"; content: string };

const MAX_LENGTH = 1200;
const starters = [
  "What kind of GenAI systems are you building?",
  "How does networking inform your AI work?",
  "Tell me about your RAG projects.",
  "Which projects did you build without Claude Code?",
];

const FAILURE = "I couldn’t answer that just now. Please try again shortly.";

export function DigitalTwin() {
  const { setOpen, toggleDock, registerSubmit } = useTwin();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const send = useCallback(async (raw: string) => {
    const message = raw.trim();
    if (!message || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setInput("");
    setMessages((current) => [...current, { role: "visitor", content: message }, { role: "twin", content: "" }]);

    const setReply = (update: (previous: string) => string) =>
      setMessages((current) => current.map((item, index) => (index === current.length - 1 ? { ...item, content: update(item.content) } : item)));

    try {
      const response = await fetch("/api/twin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });

      if (!response.ok || !response.body) {
        const data = (await response.json().catch(() => ({}))) as { error?: string };
        setReply(() => data.error ?? FAILURE);
        return;
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ") || line === "data: [DONE]") continue;
          try {
            const payload = JSON.parse(line.slice(6)) as { choices?: { delta?: { content?: string } }[] };
            const delta = payload.choices?.[0]?.delta?.content;
            if (delta) setReply((previous) => previous + delta);
          } catch {
            // Provider metadata chunks are not JSON we care about.
          }
        }
      }
      setReply((previous) => previous || FAILURE);
    } catch {
      setReply(() => "I couldn’t connect just now. Check your connection and try again.");
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, []);

  // Let buttons elsewhere on the page send a question to this chat.
  useEffect(() => {
    registerSubmit((question) => void send(question));
    return () => registerSubmit(null);
  }, [registerSubmit, send]);

  // Keep the newest message in view while it streams.
  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTo({ top: node.scrollHeight });
  }, [messages]);

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(input);
    }
  }

  function clearChat() {
    if (busyRef.current) return;
    setMessages([]);
    setInput("");
    inputRef.current?.focus();
  }

  const remaining = MAX_LENGTH - input.length;

  return (
    <div className="twin">
      <header className="twin-head">
        <div>
          <h2>Digital Twin</h2>
          <p className="twin-status"><i aria-hidden="true" /> Grounded in my resume and repo</p>
        </div>
        <div className="twin-tools">
          {messages.length > 0 && <button type="button" className="quiet" onClick={clearChat} disabled={busy}>Clear</button>}
          <button type="button" className="quiet dock-only" onClick={toggleDock} aria-label="Collapse assistant">Hide</button>
          <button type="button" className="quiet drawer-only" onClick={() => setOpen(false)} aria-label="Close assistant">Close</button>
        </div>
      </header>

      <div className="twin-scroll" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="twin-empty">
            <p>I’m an AI version of Abhishek. Ask about my career, skills, or any project in this portfolio and I’ll answer in my own voice.</p>
            <ul className="starters" aria-label="Suggested questions">
              {starters.map((starter) => (
                <li key={starter}><button type="button" onClick={() => void send(starter)}>{starter}</button></li>
              ))}
            </ul>
          </div>
        ) : (
          <ol className="thread" aria-live="polite">
            {messages.map((message, index) => {
              const waiting = message.role === "twin" && !message.content && busy && index === messages.length - 1;
              return (
                <li key={index} className={`turn ${message.role}`}>
                  <span className="turn-author">{message.role === "visitor" ? "You" : "Abhishek"}</span>
                  {message.role === "visitor" ? (
                    <p>{message.content}</p>
                  ) : waiting ? (
                    <p className="typing" role="status">Reading the relevant context</p>
                  ) : (
                    <div className="markdown"><Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown></div>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <label className="sr-only" htmlFor="twin-question">Your question</label>
        <textarea
          id="twin-question"
          ref={inputRef}
          rows={2}
          value={input}
          maxLength={MAX_LENGTH}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask about a project, a skill, or my career"
        />
        <div className="composer-bar">
          <span className={remaining < 100 ? "hint warn" : "hint"}>{remaining < 100 ? `${remaining} characters left` : "Enter to send, Shift+Enter for a new line"}</span>
          <button type="submit" className="send" disabled={busy || !input.trim()}>{busy ? "Answering" : "Send"}</button>
        </div>
        <p className="scope">Scoped to my professional work. Messages are safety checked and rate limited.</p>
      </form>
    </div>
  );
}
