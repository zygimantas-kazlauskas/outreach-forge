# Prompt-tuning log

Each iteration: one variable, one-line hypothesis, re-run on the 3 demo
targets (~$0.50), keep or revert on actual improvement vs. baseline.
Runs captured in this directory; raw LLM logs in backend/logs/ (gitignored).

## Baseline (baseline.md) — $0.50

Findings, ranked:
1. **Template convergence (Writer):** 3/3 emails shared one skeleton — pivot
   paragraph always started "An AI voice receptionist...", CTA always
   "Worth a 15-minute call this week to see how it [maps to/would fit] your
   setup?" (the prompt's example CTA leaking into output).
2. **Critic fabricates ungrounded specifics in rewrites:** replaced a flagged
   generic phrase with "calendar integration is typically live within a day"
   — a checkable claim found nowhere in the spec or research.
3. **Critic spam scan reads the wrong text:** flagged "literally" in
   spam_and_ai_tells when the word only appears in the researcher's hook
   (context), not the email.
4. (not fixed) Writer makes soft cost-coverage claims with no pricing in spec.
5. (not fixed) Subject lines uniformly "BusinessName: detail".

## Iteration 1 — writer pivot/CTA variance (iter1_writer_variance.md) — $0.50, KEEP

Hypothesis: convergence comes from prompt-example anchoring; banning verbatim
anchor reuse at the pivot paragraph and CTA (opener formula explicitly
preserved) diversifies the batch without quality loss.

Result: pivot starts now vary across the batch; CTA wording varies; openers
unchanged (their-own-words → consequence); lengths 118/132/128; no
fabrications. KEPT.

New finding: convergence pressure moved to the CRITIC — it scored all 3 CTAs
"weak" (baseline: all pass) and rewrote two toward a house pattern ("Does 15
minutes Thursday or Friday work..."), and applied the 15-minute friction
threshold inconsistently (cut one 20-minute ask, kept another). Candidate
iteration 4.
