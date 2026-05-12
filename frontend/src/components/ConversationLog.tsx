import { useEffect, useRef } from "react";
import type { TranscriptItem } from "../types";

export function ConversationLog({ items, draft }: { items: TranscriptItem[]; draft: string }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, draft]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-border bg-surface">
      {/* Header */}
      <div className="border-b border-border px-4 py-3">
        <span className="font-mono text-[10px] uppercase tracking-widest text-textdim">
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
          <div className="flex flex-col gap-3">
            {items.map((item, index) => (
              <div key={`${item.role}-${index}`}>
                {item.role === "user" ? (
                  /* User message */
                  <div className="flex flex-col items-end gap-0.5">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-textdim">
                      You
                    </span>
                    <div className="max-w-[85%] rounded-lg bg-bg/70 px-3 py-2">
                      <p className="font-sans text-sm leading-relaxed text-text">{item.text}</p>
                    </div>
                  </div>
                ) : (
                  /* Assistant message */
                  <div className="flex flex-col gap-0.5">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-green">
                      Persona
                    </span>
                    <p className="font-sans text-sm leading-relaxed text-text">{item.text}</p>
                  </div>
                )}
              </div>
            ))}

            {draft && (
              <div className="flex flex-col gap-0.5">
                <span className="font-mono text-[10px] uppercase tracking-widest text-green">
                  Persona
                </span>
                <p className="font-sans text-sm leading-relaxed text-text">
                  {draft}
                  <span className="blink ml-0.5 text-green">▌</span>
                </p>
              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}
      </div>
    </div>
  );
}
