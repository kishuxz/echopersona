import { useEffect, useRef } from "react";
import type { TranscriptItem } from "../types";

export function ConversationLog({ items, draft }: { items: TranscriptItem[]; draft: string }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, draft]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border bg-surface shadow-card">
      {/* Header */}
      <div className="border-b border-border px-4 py-3">
        <span className="font-sans text-[11px] font-medium uppercase tracking-[0.2em] text-muted">
          Transcript
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {items.length === 0 && !draft ? (
          <div className="flex h-full min-h-[120px] items-center justify-center">
            <p className="font-sans text-sm text-muted">Conversation will appear here</p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {items.map((item, index) => (
              <div key={`${item.role}-${index}`}>
                {item.role === "user" ? (
                  /* User message — right-aligned, near-black */
                  <div className="flex flex-col items-end gap-1">
                    <span className="font-mono text-[10px] text-muted">
                      You
                    </span>
                    <div className="max-w-[85%] rounded-2xl bg-accent px-4 py-2.5">
                      <p className="font-sans text-sm leading-relaxed text-white">{item.text}</p>
                    </div>
                  </div>
                ) : (
                  /* Persona message — left-aligned, cream */
                  <div className="flex flex-col gap-1">
                    <span className="font-mono text-[10px] text-muted">
                      Persona
                    </span>
                    <div className="max-w-[85%] rounded-2xl bg-cream px-4 py-2.5">
                      <p className="font-sans text-sm leading-relaxed text-text">{item.text}</p>
                    </div>
                  </div>
                )}
              </div>
            ))}

            {draft && (
              <div className="flex flex-col gap-1">
                <span className="font-mono text-[10px] text-muted">
                  Persona
                </span>
                <div className="max-w-[85%] rounded-2xl bg-cream px-4 py-2.5">
                  <p className="font-sans text-sm leading-relaxed text-text">
                    {draft}
                    <span className="blink ml-0.5 text-green">▌</span>
                  </p>
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
