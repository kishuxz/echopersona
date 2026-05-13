import { useEffect, useRef } from "react";
import type { TranscriptItem } from "../types";

export function ConversationLog({ items, draft }: { items: TranscriptItem[]; draft: string }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, draft]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-lg border border-[#1a1a1a] bg-[#0d0d0d]">
      {/* Header */}
      <div className="border-b border-[#141414] px-4 py-3">
        <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-[#2e2e2e]">
          Transcript
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {items.length === 0 && !draft ? (
          <div className="flex h-full min-h-[120px] items-center justify-center">
            <p className="font-mono text-xs text-[#222]">Conversation will appear here</p>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {items.map((item, index) => (
              <div key={`${item.role}-${index}`}>
                {item.role === "user" ? (
                  /* User message — right-aligned, subtle blue tint */
                  <div className="flex flex-col items-end gap-1">
                    <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-[#2e2e2e]">
                      You
                    </span>
                    <div className="max-w-[85%] rounded-lg border border-[#0e2240] bg-[#060f1a] px-3 py-2">
                      <p className="font-sans text-sm leading-relaxed text-[#c8d8e8]">{item.text}</p>
                    </div>
                  </div>
                ) : (
                  /* Assistant message — left-aligned, green left accent */
                  <div className="flex flex-col gap-1 border-l-2 border-green/15 pl-3">
                    <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-green/60">
                      Persona
                    </span>
                    <p className="font-sans text-sm leading-relaxed text-[#d0d0d0]">{item.text}</p>
                  </div>
                )}
              </div>
            ))}

            {draft && (
              <div className="flex flex-col gap-1 border-l-2 border-green/15 pl-3">
                <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-green/60">
                  Persona
                </span>
                <p className="font-sans text-sm leading-relaxed text-[#d0d0d0]">
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
