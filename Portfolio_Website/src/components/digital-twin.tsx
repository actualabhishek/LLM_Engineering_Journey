"use client";

import { FormEvent, useState } from "react";

type Message = { role: "visitor" | "twin"; content: string };

const starters = ["What kind of GenAI systems are you building?", "How does networking inform your AI work?", "Tell me about your RAG projects."];

export function DigitalTwin() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "twin", content: "I’m Abhishek’s Digital Twin. Ask about my engineering background, GenAI work, or portfolio projects." },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);

  function clearChat() {
    if (busy) return;
    setMessages([{ role: "twin", content: "I'm Abhishek's Digital Twin. Ask about my engineering background, GenAI work, or portfolio projects." }]);
    setInput("");
  }

  async function submit(event?: FormEvent, prompted?: string) {
    event?.preventDefault();
    const message = (prompted ?? input).trim();
    if (!message || busy) return;
    setMessages((current) => [...current, { role: "visitor", content: message }, { role: "twin", content: "" }]);
    setInput("");
    setBusy(true);
    try {
      const response = await fetch("/api/twin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      if (response.ok && response.body) {
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
              if (delta) {
                setMessages((current) => current.map((item, index) => index === current.length - 1 ? { ...item, content: `${item.content}${delta}` } : item));
              }
            } catch {
              // Ignore provider metadata chunks.
            }
          }
        }
        return;
      }
      const data = (await response.json()) as { reply?: string; error?: string };
      setMessages((current) => [...current, { role: "twin", content: data.reply ?? data.error ?? "I couldn’t answer that just now. Please try again." }]);
    } catch {
      setMessages((current) => [...current, { role: "twin", content: "I couldn’t connect just now. Please try again shortly." }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section id="twin" className="panel scroll-mt-8 p-5 sm:p-7">
      <div className="mb-5 flex items-start justify-between gap-4 border-b border-white/10 pb-5">
        <div>
          <p className="eyebrow">Live portfolio interface</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-stone-100">Ask the Digital Twin</h2>
        </div>
        <div className="twin-actions"><span className="status"><i /> Online</span><button type="button" className="clear-button" onClick={clearChat} disabled={busy}>Clear chat</button></div>
      </div>

      <div className="space-y-3" aria-live="polite">
        {messages.filter((message) => message.content).map((message, index) => (
          <div key={`${message.role}-${index}`} className={message.role === "visitor" ? "chat visitor" : "chat twin"}>
            <span className="chat-label">{message.role === "visitor" ? "You" : "AS"}</span>
            <p>{message.content}</p>
          </div>
        ))}
        {busy && <div className="chat twin"><span className="chat-label">AS</span><p className="pulse">Thinking through the relevant context…</p></div>}
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        {starters.map((starter) => <button key={starter} onClick={() => submit(undefined, starter)} className="prompt" disabled={busy}>{starter}</button>)}
      </div>
      <form onSubmit={submit} className="mt-5 flex gap-2">
        <label className="sr-only" htmlFor="twin-question">Your question</label>
        <input id="twin-question" value={input} onChange={(event) => setInput(event.target.value)} maxLength={1200} placeholder="Ask a portfolio question…" className="field" />
        <button type="submit" className="button" disabled={busy || !input.trim()}>{busy ? "Sending" : "Send"}</button>
      </form>
      <p className="mt-3 text-xs leading-5 text-stone-500">Scoped to professional experience and project work. The service is rate limited and safety checked.</p>
    </section>
  );
}
