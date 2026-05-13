import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { LatencySnapshot } from "../types";

const THRESHOLDS: Record<string, [number, number]> = {
  STT:   [200, 300],
  LLM:   [150, 250],
  TTS:   [350, 500],
  TOTAL: [600, 800],
};

function valueColor(key: string, ms: number): string {
  const [warn, crit] = THRESHOLDS[key] ?? [600, 800];
  if (ms < warn) return "#00ff88";
  if (ms < crit) return "#ffaa00";
  return "#ff4444";
}

function MetricCard({
  label,
  value,
  target,
  metricKey,
}: {
  label: string;
  value?: number;
  target: string;
  metricKey: string;
}) {
  const ms = value ?? 0;
  const color = ms > 0 ? valueColor(metricKey, ms) : "#444444";
  const display = ms > 0 ? `${Math.round(ms)}` : "--";

  return (
    <div className="relative flex flex-col overflow-hidden rounded-lg border border-[#181818] bg-[#0a0a0a] p-4 transition-all duration-150 hover:border-[#252525]">
      {/* Stage label */}
      <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-[#2e2e2e]">
        {label}
      </span>

      {/* Value */}
      {ms > 0 ? (
        <span
          className="mt-1 font-mono text-5xl font-bold leading-none tabular-nums"
          style={{ color }}
        >
          {display}
          <span className="ml-0.5 font-mono text-base font-normal text-[#333]">ms</span>
        </span>
      ) : (
        <span className="mt-1 font-mono text-4xl leading-none tabular-nums text-[#252525]">
          {display}
        </span>
      )}

      {/* Target */}
      <span className="mt-2 font-mono text-[9px] text-[#2a2a2a]">{target}</span>

      {/* Bottom bar */}
      <div
        className="absolute bottom-0 left-0 right-0 h-0.5 transition-colors duration-500"
        style={{ background: ms > 0 ? color : "#141414" }}
      />
    </div>
  );
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-[#1e1e1e] bg-[#0a0a0a] px-3 py-2 font-mono text-xs shadow-lg">
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex gap-3">
          <span style={{ color: p.color }}>{p.name}</span>
          <span className="text-text">{Math.round(p.value)}ms</span>
        </div>
      ))}
    </div>
  );
}

export function LatencyDashboard({ snapshots }: { snapshots: LatencySnapshot[] }) {
  const latest = snapshots.at(-1);
  const chartData = snapshots.slice(-20).map((s, i) => ({ ...s, i: i + 1 }));
  const isLive = snapshots.length > 0;

  return (
    <div className="relative overflow-hidden rounded-lg border border-[#1a1a1a] bg-[#0d0d0d]">
      {/* Scan-line overlay */}
      <div className="scan-overlay" />

      <div className="relative z-10 p-5">
        {/* Header */}
        <div className="mb-5 flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full bg-green"
            style={{ animation: "blink 1s step-end infinite" }}
          />
          <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-[#2e2e2e]">
            Live Latency
          </span>
          {isLive && (
            <span className="ml-auto rounded border border-[#1e1e1e] bg-[#0a0a0a] px-2 py-0.5 font-mono text-[9px] text-[#3a3a3a]">
              {snapshots.length} turns
            </span>
          )}
        </div>

        {/* 4 metric cards */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard label="STT"       value={latest?.stt_ms}              target="target <200ms" metricKey="STT"   />
          <MetricCard label="LLM"       value={latest?.llm_first_token_ms}  target="target <150ms" metricKey="LLM"   />
          <MetricCard label="TTS"       value={latest?.tts_first_audio_ms}  target="target <350ms" metricKey="TTS"   />
          <MetricCard label="Total"     value={latest?.tts_first_audio_ms}  target="target <600ms" metricKey="TOTAL" />
        </div>

        {/* Chart */}
        <div className="mt-5 h-[180px]">
          {chartData.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2">
              <div className="font-mono text-xs text-muted tracking-widest">
                ● WAITING FOR FIRST TURN
              </div>
              <div className="font-sans text-xs text-textdim">
                Start a conversation to see live latency data
              </div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -8 }}>
                <XAxis dataKey="i" hide />
                <YAxis
                  tick={{ fill: "#444", fontSize: 10, fontFamily: "JetBrains Mono" }}
                  axisLine={false}
                  tickLine={false}
                  width={36}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={600} stroke="#ff4444" strokeDasharray="3 3" strokeOpacity={0.4} />
                <ReferenceLine y={200} stroke="#00ff88" strokeDasharray="3 3" strokeOpacity={0.2} />
                <Line
                  type="monotone" dataKey="stt_ms" name="STT"
                  stroke="#00ff88" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }}
                />
                <Line
                  type="monotone" dataKey="llm_first_token_ms" name="LLM"
                  stroke="#00aaff" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }}
                />
                <Line
                  type="monotone" dataKey="tts_first_audio_ms" name="TTS"
                  stroke="#ffaa00" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }}
                />
                <Line
                  type="monotone" dataKey="total_ms" name="Total"
                  stroke="#ffffff" strokeWidth={2} dot={false} activeDot={{ r: 3 }} strokeOpacity={0.5}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Legend */}
        <div className="mt-3 flex flex-wrap gap-4">
          {[
            { label: "STT",   color: "#00ff88" },
            { label: "LLM",   color: "#00aaff" },
            { label: "TTS",   color: "#ffaa00" },
            { label: "Total", color: "rgba(255,255,255,0.5)" },
          ].map(({ label, color }) => (
            <div key={label} className="flex items-center gap-1.5">
              <div className="h-0.5 w-4" style={{ background: color }} />
              <span className="font-mono text-[10px] text-textdim">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
