"use client";

import { useState, type FormEvent } from "react";
import { sendChatMessage } from "@/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

interface ChatSidebarProps {
  token: string;
  onBoardChanged: () => void;
}

export function ChatSidebar({ token, onBoardChanged }: ChatSidebarProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setSending(true);

    try {
      const reply = await sendChatMessage(token, text);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
      onBoardChanged();
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, something went wrong reaching the assistant." },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <aside className="flex w-80 shrink-0 flex-col border-l border-line bg-surface">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold text-ink">AI Assistant</h2>
        <p className="text-xs text-muted">
          Ask it to create, edit, or move cards, or rename a column.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        <div className="flex flex-col gap-3">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user"
                  ? "self-end bg-accent-solid text-white"
                  : "self-start bg-raised text-ink"
              }`}
            >
              {m.content}
            </div>
          ))}
          {sending && (
            <div className="self-start rounded-lg bg-raised px-3 py-2 text-sm text-muted">
              Thinking...
            </div>
          )}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 border-t border-line p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask the assistant..."
          aria-label="Chat message"
          disabled={sending}
          className="flex-1 rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink outline-none focus:border-accent-blue disabled:opacity-60"
        />
        <button
          type="submit"
          disabled={sending}
          className="rounded-md bg-accent-solid px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-solid-hover disabled:opacity-60"
        >
          Send
        </button>
      </form>
    </aside>
  );
}
