import { useEffect, useRef } from "react";
import type { TranscriptItem } from "../types";

interface ConversationLogProps {
  items: TranscriptItem[];
  draft: string;
  personaName?: string;
  lastResponseMs?: number | null;
  hasVoice?: boolean;
  storyCount?: number;
}

export function ConversationLog({
  items,
  draft,
  personaName,
  lastResponseMs,
  hasVoice,
  storyCount,
}: ConversationLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, draft]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b border-border px-5 py-3.5">
        <span className="font-sans text-[11px] font-medium uppercase tracking-[0.2em] text-muted">
          Conversation
        </span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {items.length === 0 && !draft ? (
          <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-3">
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none" className="text-border">
              <path d="M20 4C11.163 4 4 10.268 4 18c0 3.867 1.71 7.36 4.478 9.898L7 36l8.82-3.528A18.08 18.08 0 0 0 20 32c8.837 0 16-6.268 16-14S28.837 4 20 4z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <p className="font-sans text-sm text-muted text-center">
              {personaName
                ? `Hold the mic button to speak with ${personaName}`
                : "Start a session and hold the mic button to speak"}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-5">
            {items.map((item, index) => (
              <div key={`${item.role}-${index}`}>
                {item.role === "user" ? (
                  <div className="flex flex-col items-end gap-1">
                    <span className="font-mono text-[10px] text-muted">You</span>
                    <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5">
                      <p className="font-sans text-sm leading-relaxed text-white">{item.text}</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-1">
                    <span className="font-mono text-[10px] text-muted">{personaName ?? "Persona"}</span>
                    <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-cream px-4 py-2.5">
                      <p className="font-sans text-sm leading-relaxed text-text">{item.text}</p>
                    </div>
                  </div>
                )}
              </div>
            ))}

            {draft && (
              <div className="flex flex-col gap-1">
                <span className="font-mono text-[10px] text-muted">{personaName ?? "Persona"}</span>
                <div className="max-w-[80%] rounded-2xl rounded-bl-sm bg-cream px-4 py-2.5">
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

      {/* Stats bar — last response */}
      <div className="border-t border-border px-5 py-2.5 flex items-center gap-3 flex-wrap">
        <span className="font-mono text-[10px] text-muted">
          {lastResponseMs != null
            ? `Last response: ${(lastResponseMs / 1000).toFixed(1)}s`
            : "Waiting for first response…"}
        </span>
        {hasVoice && (
          <span className="font-mono text-[10px] text-muted">· Voice: cloned</span>
        )}
        {storyCount != null && storyCount > 0 && (
          <span className="font-mono text-[10px] text-muted">
            · Memory: {storyCount} {storyCount === 1 ? "story" : "stories"}
          </span>
        )}
      </div>
    </div>
  );
}
