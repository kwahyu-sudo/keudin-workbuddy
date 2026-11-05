# KeUdin WorkBuddy — Office Agent for Indonesian Official Travel Documents

Submission artifact for the Tencent Cloud Hackathon Indonesia 2026
(Office Agent challenge): an agentic-AI workflow that prepares official
Indonesian government travel documents (*perjalanan dinas*) through the
KeUdin demo API — with a human approval gate before any document is
generated.

## Contents

- `SKILL.md` — the WorkBuddy agent skill: the 6-step workflow (upload and
  parse Surat Tugas/SPD and receipts, show an extraction summary, complete
  missing fields through dialogue, present a final summary, wait for explicit
  human approval, then generate the documents).
- `keudin.py` — a dependency-free (Python standard library only) CLI wrapper
  that maps one command to one skill step.
- `CARA-PAKAI.md` — usage guide for the wrapper (Bahasa Indonesia).

## How it works

WorkBuddy follows `SKILL.md`, calls `keudin.py`, and talks to the KeUdin
demo API at `https://hackeu.akalimitasi.my.id`. The approval gate is
mechanical as well as procedural: `keudin.py approve <id>` only prints the
final summary and stops; the server-side approve endpoint is called only
with `approve <id> --confirm`, after the user has explicitly agreed.

Generated documents (after approval): SPD lembar 1, rincian biaya, rincian
transportasi, daftar nominatif, RPAK.

## Security

- The API key is read only from the `KEUDIN_API_KEY` environment variable.
  It is never printed, never written to a file, and never committed here.
- No real personal data is in this repo: examples use dummy names and
  numbers.

## Note

This repo holds only the agent-facing layer (skill + wrapper). The KeUdin
Python core itself is not included here.
