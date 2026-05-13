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
  if (ms < warn) return "#16A34A";
  if (ms < crit) return "#D97706";
  return "#DC2626";
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
  const color = ms > 0 ? valueColor(metricKey, ms) : "#A1A1AA";
  const display = ms > 0 ? `${Math.round(ms)}` : "--";

  return (
    <div className="relative flex flex-col overflow-hidden rounded-xl border border-border bg-surface p-4 shadow-card transition-shadow duration-150 hover:shadow-card-hover">
      <span className="font-sans text-[10px] font-medium uppercase tracking-[0.2em] text-muted">
        {label}
      </span>

      {ms > 0 ? (
        <span
          className="mt-1 font-mono text-4xl font-bold leading-none tabular-nums"
          style={{ color }}
        >
          {display}
          <span className="ml-0.5 font-mono text-sm font-normal text-muted">ms</span>
        </span>
      ) : (
        <span className="mt-1 font-mono text-3xl leading-none tabular-nums text-muted">
          {display}
        </span>
      )}

      <span className="mt-2 font-mono text-[9px] text-muted">{target}</span>

      <div
        className="absolute bottom-0 left-0 right-0 h-0.5 transition-colors duration-500"
        style={{ background: ms > 0 ? color : "#E4E4E7" }}
      />
    </div>
  );
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: any[] }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 font-mono text-xs shadow-card-hover">
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
    <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-card">
      <div className="p-5">
        {/* Header */}
        <div className="mb-5 flex items-center gap-2">
          <span
            className="h-2 w-2 rounded-full bg-green"
            style={{ animation: "blink 1s step-end infinite" }}
          />
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">
            Live Latency
          </span>
          {isLive && (
            <span className="ml-auto rounded-full border border-border bg-elevated px-2.5 py-0.5 font-mono text-[10px] text-muted">
              {snapshots.length} turns
            </span>
          )}
        </div>

        {/* 4 metric cards */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetricCard label="STT"   value={latest?.stt_ms}             target="target <200ms" metricKey="STT"   />
          <MetricCard label="LLM"   value={latest?.llm_first_token_ms} target="target <150ms" metricKey="LLM"   />
          <MetricCard label="TTS"   value={latest?.tts_first_audio_ms} target="target <350ms" metricKey="TTS"   />
          <MetricCard label="Total" value={latest?.tts_first_audio_ms} target="target <600ms" metricKey="TOTAL" />
        </div>

        {/* Chart */}
        <div className="mt-5 h-[180px]">
          {chartData.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2">
              <div className="font-mono text-xs tracking-widest text-muted">
                ● WAITING FOR FIRST TURN
              </div>
              <div className="font-sans text-xs text-muted">
                Start a conversation to see live latency data
              </div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -8 }}>
                <XAxis dataKey="i" hide />
                <YAxis
                  tick={{ fill: "#A1A1AA", fontSize: 10, fontFamily: "DM Mono" }}
                  axisLine={false}
                  tickLine={false}
                  width={36}
                />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={600} stroke="#DC2626" strokeDasharray="3 3" strokeOpacity={0.4} />
                <ReferenceLine y={200} stroke="#16A34A" strokeDasharray="3 3" strokeOpacity={0.3} />
                <Line
                  type="monotone" dataKey="stt_ms" name="STT"
                  stroke="#16A34A" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }}
                />
                <Line
                  type="monotone" dataKey="llm_first_token_ms" name="LLM"
                  stroke="#2563EB" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }}
                />
                <Line
                  type="monotone" dataKey="tts_first_audio_ms" name="TTS"
                  stroke="#D97706" strokeWidth={1.5} dot={false} activeDot={{ r: 3 }}
                />
                <Line
                  type="monotone" dataKey="total_ms" name="Total"
                  stroke="#18181B" strokeWidth={2} dot={false} activeDot={{ r: 3 }} strokeOpacity={0.4}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Legend */}
        <div className="mt-3 flex flex-wrap gap-4">
          {[
            { label: "STT",   color: "#16A34A" },
            { label: "LLM",   color: "#2563EB" },
            { label: "TTS",   color: "#D97706" },
            { label: "Total", color: "rgba(24,24,27,0.4)" },
          ].map(({ label, color }) => (
            <div key={label} className="flex items-center gap-1.5">
              <div className="h-0.5 w-4" style={{ background: color }} />
              <span className="font-mono text-[10px] text-muted">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
