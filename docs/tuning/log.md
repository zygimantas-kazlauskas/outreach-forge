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

## Iteration 2 — critic no-new-facts rule (iter2_critic_no_new_facts.md) — $0.50, KEEP

Hypothesis: the critic fabricates because nothing forbids it; an explicit
grounding constraint on rewrites stops invented specifics without dulling
its edits.

Result: rule fired exactly as designed — the writer drafted "Setup takes a
few days" (ungrounded) and the critic cut it, citing the rule: "an
unverifiable specific not found in the service spec or research output."
Bonus: the rule also catches WRITER-introduced unverifiable claims, partially
covering baseline finding 4. No fabrications in any rewrite; no regressions.
The critic's CTA threshold behavior was also consistent this run, weakening
the case for candidate iteration 4. KEPT.

## Iteration 3 — critic spam-scan scope (iter3_critic_scan_scope.md) — $0.50, KEEP

Hypothesis: the baseline false positive ("literally" flagged from the
researcher's hook text) happened because dimension 5 has no scan boundary;
restricting it to the drafted subject + body eliminates context bleed.

Result: spam_and_ai_tells empty 3/3 with no context bleed; emails clean.
No regressions (openers on formula, pivots varied, lengths 116/125/148). KEPT.

## Stop: plateau — $2.00 of $3.00 spent (4 runs)

All three approved findings fixed and verified. Improved vs baseline:
batch-level template convergence broken at the pivot paragraph and CTA
(opener formula untouched per spec), critic rewrites can no longer introduce
ungrounded claims (rule observed firing on a real case), spam-tell field no
longer pollutable by research context. Reverts: none — all three iterations
kept on first try.

Not improved / known residuals: critic applies the 15-minute CTA friction
threshold inconsistently (mild; candidate for a future pass), subject lines
still favor a "Name: detail" colon pattern (finding 5, deliberately skipped),
writer cost-coverage claims only partially mitigated via the critic's
no-new-facts rule (finding 4, deliberately skipped).
