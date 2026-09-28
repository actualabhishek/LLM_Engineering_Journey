export type Caption = { role: "guest" | "assistant"; text: string };
export type Card = { tool: string; data: Record<string, unknown> };

type OnCaption = (caption: Caption) => void;
type OnAudio = (blob: Blob) => void;
type OnCard = (card: Card) => void;
type OnError = (message: string) => void;

export function connect(
  onCaption: OnCaption,
  onAudio: OnAudio,
  onCard: OnCard,
  onError: OnError
) {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${protocol}//${location.host}/ws/voice`);
  ws.binaryType = "blob";

  ws.addEventListener("message", (event) => {
    if (typeof event.data === "string") {
      const message = JSON.parse(event.data);
      switch (message.type) {
        case "caption":
          onCaption({ role: message.role, text: message.text });
          break;
        case "card":
          onCard({ tool: message.tool, data: message.data });
          break;
        case "error":
          onError(message.message);
          break;
      }
    } else {
      onAudio(event.data as Blob);
    }
  });

  return {
    sendUtterance(blob: Blob) {
      if (ws.readyState === WebSocket.OPEN) ws.send(blob);
    },
    close() {
      ws.close();
    },
  };
}
