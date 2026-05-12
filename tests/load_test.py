"""
EchoPersona load test.

Simulates N concurrent WebSocket sessions, 3 turns each.
Uses text_turn injection to bypass STT so latency measures LLM+TTS only.

Usage:
    python tests/load_test.py <persona_id>
    python tests/load_test.py <persona_id> --users 50
"""

import argparse
import asyncio
import json
import statistics
import sys
import time

import websockets

TEST_TURNS = [
    "who are you",
    "what do you study",
    "tell me about your dogs",
]

WS_BASE = "ws://localhost:8000"  # overridden by --base CLI arg
TURN_TIMEOUT = 15.0   # seconds to wait for latency_summary per turn
CONNECT_TIMEOUT = 10.0


async def simulate_user(user_id: int, persona_id: str, num_turns: int = 3) -> list[float]:
    """Run one full conversation session and return per-turn total_ms values."""
    uri = f"{WS_BASE}/ws/loadtest_{user_id}?persona_id={persona_id}"
    latencies: list[float] = []

    try:
        async with websockets.connect(
            uri,
            ping_interval=20,
            ping_timeout=10,
            open_timeout=CONNECT_TIMEOUT,
        ) as ws:
            for turn_idx in range(num_turns):
                question = TEST_TURNS[turn_idx % len(TEST_TURNS)]

                await ws.send(json.dumps({"type": "text_turn", "text": question}))

                total_ms: float | None = None
                deadline = time.perf_counter() + TURN_TIMEOUT

                while time.perf_counter() < deadline:
                    remaining = deadline - time.perf_counter()
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                    except asyncio.TimeoutError:
                        break

                    data = json.loads(raw)
                    msg_type = data.get("type")

                    if msg_type == "latency_summary":
                        total_ms = float(data["total_ms"])
                        break
                    if msg_type == "audio_end" and total_ms is None:
                        # latency_summary always follows audio_end; keep draining
                        continue
                    if msg_type == "error":
                        print(f"  [user {user_id}] server error: {data.get('message')}")
                        total_ms = TURN_TIMEOUT * 1000  # penalise as max latency
                        break

                if total_ms is not None:
                    latencies.append(total_ms)
                else:
                    latencies.append(TURN_TIMEOUT * 1000)  # timeout sentinel

                await asyncio.sleep(0.3)  # brief gap between turns

    except Exception as exc:
        print(f"  [user {user_id}] failed: {type(exc).__name__}: {exc}")
        return []

    return latencies


def pct(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = max(0, int(len(s) * p / 100) - 1)
    return s[idx]


async def run_load_test(num_users: int, persona_id: str) -> dict:
    bar = "=" * 52
    print(f"\n{bar}")
    print(f"  EchoPersona Load Test — {num_users} concurrent users")
    print(f"  Persona : {persona_id}")
    print(f"  Turns   : {len(TEST_TURNS)} per user  |  timeout: {TURN_TIMEOUT}s")
    print(f"{bar}")

    t0 = time.perf_counter()
    tasks = [simulate_user(i, persona_id) for i in range(num_users)]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    wall = time.perf_counter() - t0

    all_ms: list[float] = []
    errors = 0
    ok_users = 0

    for r in raw_results:
        if isinstance(r, Exception):
            errors += 1
        elif isinstance(r, list) and r:
            all_ms.extend(r)
            ok_users += 1
        else:
            errors += 1

    print(f"\n  Wall time      : {wall:.1f}s")
    print(f"  Successful     : {ok_users}/{num_users} users")
    print(f"  Errors/timeouts: {errors}")
    print(f"  Turns measured : {len(all_ms)}")

    result = {"users": num_users, "ok": ok_users, "errors": errors, "latencies": all_ms}

    if all_ms:
        p50  = pct(all_ms, 50)
        p75  = pct(all_ms, 75)
        p90  = pct(all_ms, 90)
        p95  = pct(all_ms, 95)
        p99  = pct(all_ms, 99)
        mean = statistics.mean(all_ms)
        mx   = max(all_ms)

        print(f"\n  Latency (total_ms from latency_summary):")
        print(f"    mean : {mean:6.0f}ms")
        print(f"    P50  : {p50:6.0f}ms")
        print(f"    P75  : {p75:6.0f}ms")
        print(f"    P90  : {p90:6.0f}ms")
        print(f"    P95  : {p95:6.0f}ms")
        print(f"    P99  : {p99:6.0f}ms")
        print(f"    max  : {mx:6.0f}ms")

        target = 800
        verdict = "✅ PASS" if p95 < target else "❌ FAIL"
        print(f"\n  {verdict} — P95 {p95:.0f}ms vs {target}ms target")

        result.update({"mean": mean, "p50": p50, "p75": p75,
                        "p90": p90, "p95": p95, "p99": p99, "max": mx})

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("persona_id", help="Persona ID to use for all sessions")
    parser.add_argument("--users", type=int, default=None,
                        help="Run a single N-user test instead of the 10/25/50 ramp")
    parser.add_argument("--base", default=None,
                        help="WebSocket base URL (default: ws://localhost:8000)")
    args = parser.parse_args()

    if args.base:
        global WS_BASE
        WS_BASE = args.base

    ramp = [args.users] if args.users else [10, 25, 50]
    all_results = []

    for n in ramp:
        result = asyncio.run(run_load_test(n, args.persona_id))
        all_results.append(result)
        if n != ramp[-1]:
            print("\n  (pausing 3s before next run…)")
            time.sleep(3)

    if len(all_results) > 1:
        print("\n" + "=" * 52)
        print("  Summary")
        print("=" * 52)
        print(f"  {'Users':>5}  {'P50':>6}  {'P95':>6}  {'P99':>6}  {'Errors':>6}")
        print(f"  {'-'*5}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*6}")
        for r in all_results:
            p50 = f"{r.get('p50', 0):.0f}ms"
            p95 = f"{r.get('p95', 0):.0f}ms"
            p99 = f"{r.get('p99', 0):.0f}ms"
            print(f"  {r['users']:>5}  {p50:>6}  {p95:>6}  {p99:>6}  {r['errors']:>6}")


if __name__ == "__main__":
    main()
