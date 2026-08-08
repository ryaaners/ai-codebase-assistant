import { useEffect, useRef, useState } from "react";
import { ArrowUp, FileCode2, Loader2, Sparkles } from "lucide-react";
import type { ChatMessage, CitationOut } from "@/types";

interface Props {
  messages: ChatMessage[];
  loading: boolean;
  onSend: (question: string) => void;
  onCitationClick: (citation: CitationOut) => void;
}

const SUGGESTIONS = [
  "Where is user authentication implemented?",
  "Explain how the main request flow works.",
  "What would break if I changed the database layer?",
];

export default function ChatPanel({ messages, loading, onSend, onCitationClick }: Props) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  function submit(text?: string) {
    const question = (text ?? input).trim();
    if (!question || loading) return;
    onSend(question);
    setInput("");
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div className="flex size-10 items-center justify-center rounded-full bg-accent-soft text-accent-text">
              <Sparkles className="size-5" />
            </div>
            <p className="max-w-xs text-sm text-text-muted">
              Ask anything about how this codebase works — answers are grounded in the
              parsed call graph, not guesses.
            </p>
            <div className="flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => submit(s)}
                  className="rounded-full border border-border px-3.5 py-1.5 text-xs text-text-muted transition-colors hover:border-accent/40 hover:text-text"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : ""}>
            <div
              className={
                m.role === "user"
                  ? "max-w-[85%] rounded-2xl rounded-br-sm bg-surface-raised px-4 py-2.5 text-[13.5px] text-text"
                  : "max-w-full text-[13.5px] leading-relaxed text-text"
              }
            >
              <p className="whitespace-pre-wrap">{m.text}</p>
              {m.mode === "extractive" && (
                <p className="mt-1.5 text-xs italic text-text-faint">
                  Showing raw search results — no LLM configured for this deployment.
                </p>
              )}
              {m.citations && m.citations.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {m.citations.slice(0, 6).map((c, i) => (
                    <button
                      key={i}
                      onClick={() => onCitationClick(c)}
                      className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 font-mono text-[11px] text-text-muted transition-colors hover:border-accent/40 hover:text-accent-text"
                    >
                      <FileCode2 className="size-3" />
                      {c.symbol_name}
                      <span className="text-text-faint">:{c.start_line}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 text-xs text-text-faint">
            <Loader2 className="size-3.5 animate-spin" /> Searching the codebase…
          </div>
        )}
      </div>

      <div className="border-t border-border-soft p-4">
        <div className="flex items-end gap-2 rounded-xl border border-border bg-surface px-3 py-2 focus-within:border-accent/50">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Ask about this codebase…"
            rows={1}
            className="max-h-32 flex-1 resize-none bg-transparent py-1.5 text-[13.5px] text-text placeholder:text-text-faint focus:outline-none"
          />
          <button
            onClick={() => submit()}
            disabled={!input.trim() || loading}
            className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent text-bg transition-opacity disabled:opacity-30"
            aria-label="Send"
          >
            <ArrowUp className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
