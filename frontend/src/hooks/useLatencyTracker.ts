import { useCallback, useState } from "react";
import type { LatencySnapshot } from "../types";

export function useLatencyTracker() {
  const [snapshots, setSnapshots] = useState<LatencySnapshot[]>([]);
  const addSnapshot = useCallback((snapshot: LatencySnapshot) => {
    setSnapshots((current) => [...current.slice(-19), snapshot]);
  }, []);
  return { snapshots, addSnapshot };
}
