#!/usr/bin/env python3
"""Measure the current Claude Code session's context size and prompt-cache economics.

Reads the session transcript (~/.claude/projects/*/<session-id>.jsonl), takes the
usage of the last main-chain assistant turn, and prints what a long break would cost
with a cold cache versus compacting first.

The floor a /compact cannot go below (system prompt, tool definitions, re-injected
AGENTS.md / memory / skill listings) is measured, not assumed. Sources, best first:
  1. own-compact    this session's last compact: the first real turn after it
  2. project-compact recent compacts in the same project folder: turn after - postTokens
  3. first-turns    median first-turn context of recent sessions in the folder
  4. default        DEFAULT_BASELINE
The context right after a compact is baseline + summary (compact_boundary postTokens).

Usage: away_check.py [session-id]   (default: $CLAUDE_CODE_SESSION_ID, else newest transcript)
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone
from statistics import median

# $/MTok — claude-api skill price table cached 2026-10-06. Update here when prices change.
# (input, output, cache_read)
PRICES = {
    "claude-fable-5-1": (10.00, 50.00, 0.25),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
WRITE_1H, WRITE_5M = 2.0, 1.25          # cache write multipliers on base input
DEFAULT_BASELINE = 75_000                # fallback floor; this workspace measured ~70-81K (2026-10-28)
DEFAULT_SUMMARY = 15_000                 # fallback compact summary (postTokens)
COMPACT_OUTPUT_TOKENS = 10_000           # summary + thinking emitted by the compact turn
PING_OUTPUT_TOKENS = 1_500               # output + thinking of one idle keep-alive turn (unmeasured)
PING_GROWTH_TOKENS = 2_500               # context each keep-alive turn adds (written to cache)
PING_INTERVAL_MIN = 55                   # just under the 1h TTL
RECENT_TRANSCRIPTS = 40                  # how many recent transcripts in the folder to sample


def find_transcript(session_id):
    root = os.path.expanduser("~/.claude/projects")
    if session_id:
        hits = glob.glob(os.path.join(root, "*", session_id + ".jsonl"))
        if hits:
            return hits[0]
        sys.exit(f"transcript for session {session_id} not found under {root}")
    hits = glob.glob(os.path.join(root, "*", "*.jsonl"))
    if not hits:
        sys.exit("no transcripts found")
    return max(hits, key=os.path.getmtime)


def input_ctx(u):
    return (u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
            + u.get("cache_creation_input_tokens", 0))


def scan(path):
    """Main-chain assistant turns and compact boundaries, in file order.

    Yields ("turn", rec, usage) or ("compact", rec, metadata). Synthetic turns with no
    input (error stubs, carried-over placeholders) are skipped.
    """
    with open(path, encoding="utf-8") as f:
        for line in f:
            if '"usage"' not in line and '"compact_boundary"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("isSidechain"):
                continue
            if rec.get("subtype") == "compact_boundary":
                yield "compact", rec, rec.get("compactMetadata") or {}
                continue
            msg = rec.get("message") or {}
            u = msg.get("usage")
            if msg.get("role") == "assistant" and u and input_ctx(u) > 0:
                yield "turn", rec, u


def session_state(path):
    """Last turn, cache TTL, own last compact, and the first turn's cache read.

    The TTL comes from the most recent usage.cache_creation split (1h vs 5m), which
    already reflects plan, API key and over-quota downgrades. None if never recorded.
    """
    sid = os.path.basename(path)[:-len(".jsonl")]
    last, ttl, first_read, own_compact, pending = None, None, None, None, None
    for kind, rec, data in scan(path):
        if kind == "compact":
            pending = data
            continue
        last = rec
        if first_read is None:
            first_read = data.get("cache_read_input_tokens", 0)
        split = data.get("cache_creation") or {}
        if split.get("ephemeral_1h_input_tokens"):
            ttl = 60
        elif split.get("ephemeral_5m_input_tokens"):
            ttl = 5
        if pending is not None:
            # A boundary copied from a parent session still marks a real compact; keep the latest.
            own_compact = (input_ctx(data), pending.get("postTokens") or DEFAULT_SUMMARY,
                           rec.get("sessionId") == sid)
            pending = None
    if last is None:
        sys.exit("no assistant usage found in transcript")
    return last, ttl, first_read or 0, own_compact


def project_samples(path):
    """Baseline and summary samples from recent transcripts in the same folder."""
    folder = os.path.dirname(path)
    files = sorted(glob.glob(os.path.join(folder, "*.jsonl")), key=os.path.getmtime)
    bases, summaries, firsts, seen = [], [], [], set()
    for f in files[-RECENT_TRANSCRIPTS:]:
        sid = os.path.basename(f)[:-len(".jsonl")]
        pending, first_done = None, False
        for kind, rec, data in scan(f):
            own = rec.get("sessionId") == sid
            if kind == "compact":
                pending = data if own else None      # copied boundaries are counted in their own file
                continue
            if not first_done:
                first_done = True
                if own:
                    firsts.append(input_ctx(data))
            if pending is not None and rec.get("uuid") not in seen:
                seen.add(rec.get("uuid"))
                post = pending.get("postTokens")
                if post:
                    bases.append(input_ctx(data) - post)
                    summaries.append(post)
                pending = None
    return bases, summaries, firsts


def other_session_active(path, ttl):
    """Minutes since the newest other transcript in the folder was written."""
    folder = os.path.dirname(path)
    others = [f for f in glob.glob(os.path.join(folder, "*.jsonl")) if f != path]
    if not others:
        return None
    newest = max(os.path.getmtime(f) for f in others)
    return (datetime.now().timestamp() - newest) / 60


def price_for(model):
    for key in sorted(PRICES, key=len, reverse=True):
        if model and model.startswith(key):
            return key, PRICES[key]
    return "claude-opus-5-5 (fallback)", PRICES["claude-opus-5-5"]


def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CLAUDE_CODE_SESSION_ID")
    path = find_transcript(session_id)
    rec, ttl, first_read, own_compact = session_state(path)
    ttl_known = ttl is not None
    ttl = ttl or 5                       # unknown: assume the shorter TTL
    msg, u = rec["message"], rec["message"]["usage"]
    ctx = input_ctx(u) + u.get("output_tokens", 0)

    # Floor after a compact: baseline + summary
    bases, summaries, firsts = project_samples(path)
    summary = int(median(summaries)) if summaries else DEFAULT_SUMMARY
    if own_compact:
        post_ctx, summary = own_compact[0], own_compact[1]
        baseline, src = post_ctx - summary, "own-compact"
    elif bases:
        baseline, src = int(median(bases)), f"project-compact, median of {len(bases)}"
    elif firsts:
        baseline, src = int(median(firsts)), f"first-turns, median of {len(firsts)}"
    else:
        baseline, src = DEFAULT_BASELINE, "default, estimate"
    post_ctx = baseline + summary
    convo = max(ctx - baseline, 0)

    ts = datetime.fromisoformat(rec["timestamp"].replace("Z", "+00:00"))
    idle_min = (datetime.now(timezone.utc) - ts).total_seconds() / 60

    model_key, (inp, out, read) = price_for(msg.get("model"))
    m = 1_000_000
    w = inp * (WRITE_1H if ttl == 60 else WRITE_5M)
    cold = ctx * w / m
    warm = ctx * read / m
    compact = ctx * read / m + COMPACT_OUTPUT_TOKENS * out / m + post_ctx * w / m
    # context size above which compacting before a break beats a cold resume
    breakeven = (COMPACT_OUTPUT_TOKENS * out + post_ctx * w) / (w - read)
    ping = ctx * read / m + PING_OUTPUT_TOKENS * out / m + PING_GROWTH_TOKENS * w / m
    ping_every = min(PING_INTERVAL_MIN, ttl - 1)
    ping_hours = cold / ping * ping_every / 60

    # The shared prefix (system prompt, tools) may still be warm from another session.
    shared = min(first_read, ctx)
    other_idle = other_session_active(path, ttl)

    print(f"transcript        {path}")
    print(f"model             {msg.get('model')}  (prices: {model_key})")
    print(f"effort            {os.environ.get('CLAUDE_EFFORT', 'unknown')}")
    print(f"context tokens    {ctx:,}")
    print(f"baseline          {baseline:,}  ({src})")
    print(f"conversation part {convo:,}  (context - baseline; what a compact can remove)")
    print(f"after compact     ~{post_ctx:,}  (baseline + ~{summary // 1000}K summary)")
    print(f"last request      {ts.astimezone().strftime('%Y-%m-%d %H:%M')}  ({idle_min:.0f} min ago)")
    ttl_src = "from last cache write" if ttl_known else "NO DATA, assuming 5 min"
    left = ttl - idle_min
    state = f"warm, {left:.0f} min left" if left > 0 else "COLD"
    print(f"cache TTL         {ttl} min ({ttl_src})")
    print(f"cache now         {state}")
    print(f"resume, warm      ${warm:.2f}")
    print(f"resume, cold      ${cold:.2f}  ({ttl} min TTL write)")
    if shared and other_idle is not None:
        shared_cold = (ctx - shared) * w / m + shared * read / m
        when = f"another session here wrote {other_idle:.0f} min ago"
        print(f"  shared prefix   ~{shared // 1000}K; if still warm from another session, cold resume"
              f" ~${shared_cold:.2f} (estimate; {when})")
    print(f"compact first     ~${compact:.2f}  (compact turn + re-cache ~{post_ctx // 1000}K)")
    print(f"break-even        ~{breakeven / 1000:.0f}K tokens total"
          f" (~{max(breakeven - baseline, 0) / 1000:.0f}K conversation part)")
    print(f"saving if compact ~${max(cold - compact, 0):.2f} on the first turn back")
    print(f"keep-alive ping   ~${ping:.2f} each, every {ping_every} min; cheaper than a cold resume"
          f" for gaps under ~{ping_hours:.0f}h (estimate, not recommended)")


if __name__ == "__main__":
    main()
