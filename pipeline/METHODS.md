# FAERS Pharmacovigilance Pipeline — Methods & Key Findings

Drug–substance–adverse-event signal detection from FAERS 2020Q1–2024Q4 (20 quarters).

## Data-reality adaptation (important)
The public FAERS quarterly ASCII release contains **only structured `$`-delimited coded
tables** (DEMO, DRUG, REAC, OUTC, INDI, THER, RPSR) — **there are no free-text
narratives.** The build spec's narrative-extraction + scispaCy-NER steps (Steps 4–5) do
not apply to this source. Substances are instead detected over the structured text a case
provides — reported drug products (`drugname`/`prod_ai`), indications (`indi_pt`), and
reactions (`pt`) — which is the standard approach for FAERS substance-co-use studies.

**Deferred (documented, not silently dropped):** scispaCy biomedical NER (no narratives to
run on + heavy/fragile install); live RxNorm API drug enrichment (`prod_ai` already gives
the active ingredient); licensed MedDRA LLT→PT→SOC dictionary (reactions are already coded
MedDRA PTs). These are additive, not blocking, for the signal analysis.

## Pipeline
`01_parse_faers` (parse + dedup) → `03_filter_sud` (SUD-med filter + normalization +
substance flags) → `05_disproportionality` (triples + 4-method DA + stratified + temporal)
→ `06_export_manuscript` (validation + tables + figures). Module: `substance_detection.py`.

## Scale
- 8.74M report-versions → **7.47M unique cases** (14.4% duplicate report-versions removed).
- **819,964 SUD-medication cases**; **58,646 substance-mention cases**.
- 100,650 drug–event combinations with n≥3; **47,103 ROR signals**.

## Methods
Four disproportionality measures per (drug, event): **ROR** (+95% CI), **PRR** (+χ²),
**IC** (BCPNN shrinkage, IC025), **EBGM** (empirical-Bayes Gamma-Poisson, method-of-moments
prior — simplified MGPS, EB05). Signal rule: ROR>2 & ROR_lo>1 & n≥3; cross-method agreement
reported. Evidence grading A/B/C/D. **Novel analysis:** substance-stratified ROR (with vs
without substance co-mention) + z-test on the lnROR difference. Temporal: annual ROR.

## Validation (methodological confidence)
Top signals reproduce **known FDA labels/black-box AEs** — strong positive controls:
olanzapine→post-injection delirium/sedation syndrome (Zyprexa Relprevv), valproate→foetal
anticonvulsant syndrome + congenital malformations, acamprosate→Wernicke-Korsakoff,
disulfiram→alcohol intolerance. Substance-detection module passes all exclusion-homonym
(alcohol swab, dronabinol, sodium oxybate, adderall, PCP-visit) and positive-control tests.

## Exports for MCP (Path 3)
`faers_drug_substance_signals.csv` (ROR/PRR/IC/EBGM/CI/n/evidence_level per DEC),
`faers_temporal_trends.csv`, `faers_substance_detection_validation.csv`,
`faers_descriptive_stats.csv`.
