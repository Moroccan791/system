#!/usr/bin/env python3
"""Block a clip before it is cut, not after it is posted.

The 2 Bears brief is mostly a list of things that get a *whole clip* rejected:
slurs, sexual content, suicide phrasing, drug how-tos, accusations about named
people, brand disses, guns, and anything touching Hitler/Nazi/Holocaust. A
clip that needs the taboo line for its punchline cannot be saved by cutting
around it, so the guard runs at **selection** time - a banned moment
disqualifies every candidate window that overlaps it - and again on the
finished cut.

Severity:

    block  the window is unusable
    warn   usable, but needs a human read before it ships
    text   hard-blocked in titles, captions and on-screen text specifically,
           because the brief bans these words in text even where the same
           word in speech might be survivable

The lexicon is data, not code: it lives in the campaign's `lexicon.json`, so a
different client's list can replace it without touching this file.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Fallback lexicon - deliberately short and extendable. The point is the
#: mechanism, and every campaign should ship its own list.
DEFAULT = {
    "categories": {
        "slur": {"severity": "block", "text": True, "terms": []},
        "sexual": {"severity": "block", "text": True, "terms": [
            "incest", "molest", "pedo", "underage", "blowjob", "handjob",
            "anal", "orgasm", "ejaculat", "porn", "masturbat", "erection",
            "dildo", "vibrator", "cum", "nude", "naked", "sex tape"]},
        "self_harm": {"severity": "block", "text": True, "terms": [
            "suicide", "kill myself", "killing myself", "kill yourself",
            "kys", "self harm", "self-harm", "cut myself", "hang myself",
            "overdose", "unalive"]},
        "drugs": {"severity": "block", "text": True, "terms": [
            "cocaine", "heroin", "meth", "fentanyl", "xanax", "adderall",
            "molly", "ecstasy", "ketamine", "shrooms", "psilocybin",
            "dosage", "milligram", "mg of", "plug for", "score some",
            "took a bump", "on coke", "on pills"]},
        "nazi": {"severity": "block", "text": True, "terms": [
            "hitler", "nazi", "nazis", "holocaust", "gestapo", "third reich",
            "heil", "swastika", "auschwitz", "goebbels", "goering"]},
        "violence": {"severity": "block", "text": True, "terms": [
            "gun", "guns", "pistol", "rifle", "shoot him", "shoot her",
            "shoot you", "kill him", "kill her", "kill you", "stab",
            "murder him", "murder her", "beat the shit"]},
        "accusation": {"severity": "warn", "text": True, "terms": [
            "raped", "rapist", "sexual assault", "beat his wife",
            "beat her", "cheated on", "molester", "abused her", "abused him",
            "groomed", "groomer"]},
        "brand": {"severity": "warn", "text": False, "terms": [
            "mcdonald", "burger king", "wendy", "taco bell", "chick-fil-a",
            "subway", "domino", "pizza hut", "starbucks", "delta",
            "united airlines", "southwest", "american airlines", "tesla",
            "bud light", "pepsi", "coca-cola", "netflix", "spotify"]},
        "politics": {"severity": "warn", "text": False, "terms": [
            "trump", "biden", "harris", "republican", "democrat", "election",
            "congress", "senate", "president", "woke", "antifa", "maga"]},
        "sponsor": {"severity": "warn", "text": False, "terms": [
            "sponsor", "sponsored", "promo code", "coupon code", "this episode is brought",
            "brought to you by", "our friends at", "use code"]},
        "network": {"severity": "warn", "text": False, "terms": [
            "revenue", "contract", "deal with", "per episode", "our deal",
            "the network", "ymh", "your mom's house", "ad revenue", "cpm",
            "sponsorship money"]},
        "divorce": {"severity": "warn", "text": False, "terms": [
            "divorce", "divorced", "marriage", "my ex wife", "my ex husband",
            "prenup", "alimony"]},
        "kids_sexual": {"severity": "block", "text": True, "terms": [
            "baby bit", "the baby", "my kid", "my kids", "children",
            "toddler", "infant", "schoolgirl"]},
    },
    "notes": [
        "kids_sexual is a guard, not a verdict: the brief bans kids and sexual "
        "content in the same frame, so any window hitting both this and the "
        "sexual category is blocked; kids alone is fine.",
        "The transcript cannot see a bleep. Bleeped slurs are banned by this "
        "campaign and must be caught by ear.",
    ],
}


def load_lexicon(campaign_dir: Path | None = None) -> dict:
    path = (campaign_dir / "lexicon.json") if campaign_dir else None
    if path and path.exists():
        data = json.loads(path.read_text())
        merged = json.loads(json.dumps(DEFAULT))
        for name, spec in (data.get("categories") or {}).items():
            base = merged["categories"].get(name, {"severity": "warn", "text": False, "terms": []})
            merged["categories"][name] = {**base, **spec,
                                          "terms": list(dict.fromkeys(
                                              list(base.get("terms", [])) + list(spec.get("terms", []))))}
        if data.get("notes"):
            merged["notes"] = data["notes"]
        return merged
    return DEFAULT


def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9']", "", str(token).lower())


def _matches(haystack: str, term: str) -> bool:
    """Substring match on a normalised string, on word starts.

    `nazi` must hit "nazis" and "nazi's" but not "snazzy"; matching at a token
    start and allowing the term to run to the end of a token does that.
    """
    t = term.lower()
    if " " in t:
        return t in haystack
    return re.search(r"(?<![a-z0-9])" + re.escape(t), haystack) is not None


def scan_text(text: str, *, lexicon: dict | None = None,
              strict: bool = True) -> list[dict]:
    """Check a title, caption or on-screen string.

    `strict` reports only the categories the brief bans in *copy* (slurs,
    Nazi/Hitler references). That is the right default: a podcast title can
    legitimately say "politics", but it can never print a slur.
    """
    hay = " " + re.sub(r"\s+", " ", str(text).lower()) + " "
    hits = []
    for name, spec in (lexicon or DEFAULT)["categories"].items():
        if strict and spec.get("text") is False:
            continue                      # not a text-blocking category
        for term in spec.get("terms", []):
            if _matches(hay, term):
                hits.append({"category": name, "term": term,
                             "severity": spec.get("severity", "warn"),
                             "in_text": bool(spec.get("text"))})
    return hits


def scan_words(words: list[dict], *, lexicon: dict | None = None) -> list[dict]:
    """Per-word scan that keeps the timestamp, so a window can be tested.

    Multi-word terms are checked against a sliding window of the same length,
    so "kill myself" hits even when it is two transcript tokens.
    """
    lex = lexicon or DEFAULT
    hits: list[dict] = []
    toks = [_norm(w.get("text") or w.get("w") or "") for w in words]
    for name, spec in lex["categories"].items():
        for term in spec.get("terms", []):
            parts = [_norm(p) for p in term.split()]
            n = len(parts)
            for i in range(len(toks) - n + 1):
                if all(toks[i + k] and (toks[i + k].startswith(parts[k]) or parts[k] in toks[i + k])
                       for k in range(n)):
                    w0, w1 = words[i], words[i + n - 1]
                    hits.append({
                        "category": name, "term": term,
                        "severity": spec.get("severity", "warn"),
                        "in_text": bool(spec.get("text")),
                        "start": float(w0.get("start", w0.get("at", 0.0))),
                        "end": float(w1.get("end", w1.get("start", 0.0))),
                    })
                    break
    return sorted(hits, key=lambda h: (h["start"], h["category"]))


def window_ok(start: float, end: float, hits: list[dict], *,
              pad: float = 0.6) -> tuple[bool, list[dict]]:
    """Can a clip span this window? Blocked if any *block* hit overlaps it.

    `pad` widens the window: a banned line half a second outside the cut is
    still in the listener's ear by the time the clip ends.
    """
    inside = [h for h in hits
              if h["start"] <= end + pad and h["end"] >= start - pad]
    blocked = [h for h in inside if h["severity"] == "block"]
    return (not blocked), inside


def review_rows(hits: list[dict]) -> list[dict]:
    """A short list for the human: category, term, when."""
    return [{"at": round(h["start"], 2), "category": h["category"],
             "term": h["term"], "severity": h["severity"]} for h in hits]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript", help="transcript json with words")
    ap.add_argument("--campaign", default="two_bears_ep344")
    ap.add_argument("--window", nargs=2, type=float, metavar=("START", "END"))
    ap.add_argument("--text", help="also check a title/caption string")
    args = ap.parse_args()

    lex = load_lexicon(ROOT / "campaigns" / args.campaign)
    words = json.loads(Path(args.transcript).read_text())
    words = words.get("words", words) if isinstance(words, dict) else words
    hits = scan_words(words, lexicon=lex)
    print(f"\nTOPIC GUARD — {len(hits)} hit(s)")
    for h in hits:
        print(f"  {h['start']:7.2f}s  [{h['severity']:5s}] {h['category']:12s} {h['term']}")
    if args.window:
        ok, inside = window_ok(args.window[0], args.window[1], hits)
        print(f"\nwindow {args.window[0]:.2f}-{args.window[1]:.2f}s: "
              f"{'USABLE' if ok else 'BLOCKED'}")
        for h in inside:
            print(f"  overlaps {h['category']} ({h['term']}) at {h['start']:.2f}s")
    if args.text:
        thits = scan_text(args.text, lexicon=lex)
        print(f"\ntext: {len(thits)} hit(s)")
        for h in thits:
            print(f"  [{h['severity']:5s}] {h['category']:12s} {h['term']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
