# FAERS-Pharmacovigilance — drug–substance signal detection, FAERS 2020–2024

**Phase 2 of the [PRISM platform](https://github.com/SCharithaKodumagulla/PRISM-Platform).**

Detects adverse-event safety signals for medications used in substance use disorder care,
and asks a question standard pharmacovigilance does not: **does the signal change when the
patient is also using a substance?**

---

## Scale

| | |
|---|---|
| Quarters processed | 20 (2020Q1 – 2024Q4) |
| Report-versions parsed | 8,743,000 |
| Unique cases after dedup | **7,470,000** (14.4% duplicate report-versions removed) |
| SUD-medication cases | 819,964 |
| Cases with a substance mention | **41,433** (see correction note below) |
| Drug–event combinations (n ≥ 3) | 100,650 |
| ROR signals | **47,103** |

## Methods

Four disproportionality measures per (drug, event) pair:

- **ROR** with 95% CI
- **PRR** with χ²
- **IC** — BCPNN with shrinkage, reported as IC₀₂₅
- **EBGM** — empirical-Bayes Gamma-Poisson with a method-of-moments prior (simplified MGPS), reported as EB05

Signal rule: `ROR > 2 AND ROR_lower > 1 AND n ≥ 3`. Cross-method agreement is reported
rather than assumed, and each signal carries an A/B/C/D evidence grade.

**The novel analysis** is substance-stratified ROR: the same drug–event pair computed with
and without substance co-mention, compared by a z-test on the difference in log-ROR. That
is what turns a generic signal list into evidence about polysubstance risk.

## A data-reality note that matters

The public FAERS quarterly ASCII release contains **only structured `$`-delimited coded
tables** (DEMO, DRUG, REAC, OUTC, INDI, THER, RPSR). **There are no free-text narratives.**
Any pipeline promising narrative NLP or scispaCy NER over public FAERS is describing
something the data cannot support.

Substances are therefore detected across the structured text a case does provide — reported
drug products (`drugname`, `prod_ai`), indications (`indi_pt`), and reactions (`pt`) — which
is the standard approach for FAERS substance co-use studies.

Deferred deliberately, and documented rather than silently dropped: scispaCy biomedical NER
(no narratives to run it on), live RxNorm enrichment (`prod_ai` already yields the active
ingredient), and licensed MedDRA LLT→PT→SOC mapping (reactions arrive as coded MedDRA PTs).

## Substance detection

15 substances with primary / contextual / exclusion patterns:

`alcohol`, `cannabis`, `cocaine`, `methamphetamine`, `heroin`, `illicit_fentanyl`,
`xylazine`, `kratom`, `tianeptine`, `phenibut`, `nitazenes`,
`designer_benzodiazepines`, `mdma`, `ghb`, `pcp`

Exclusion patterns are load-bearing and regression-tested: *alcohol swab* is not alcohol,
*dronabinol* is not cannabis, *Adderall* is not methamphetamine, *sodium oxybate* is not
GHB, and a *PCP visit* is not phencyclidine.

## Correction, August 2026

The substance detector's exclusion patterns did not work as documented. Exclusions were
applied to *contextual* matches only, so a primary pattern matching **inside** an excluded
span still counted — `/alcohol/` matches within "alcohol swab", so antiseptic wipes,
ChloraPrep, and cetyl/benzyl/isopropyl alcohol excipients were all scored as alcohol use.

Exclusions are now span-based: a match is suppressed only where it falls inside an excluded
span, so *"alcohol swab used; patient drinks alcohol daily"* still correctly yields alcohol.

| | before | after |
|---|---|---|
| alcohol cases | 32,637 | **15,341** (−53%) |
| any-substance cases | 58,646 | **41,433** |
| all other substances | — | unchanged |

One published signal, **alcohol × risperidone → gynaecomastia**, does not survive and has
been withdrawn. Surviving alcohol-stratified RORs fall by roughly half.

The base drug–event analysis (100,650 DECs, 47,103 ROR signals) does not use substance
detection and is unchanged. 46 regression tests in `tests/` now guard this behaviour.

## Validation

Top signals recover known FDA labeling and black-box events, which is the positive-control
evidence that the estimator is behaving:

- olanzapine → post-injection delirium/sedation syndrome (Zyprexa Relprevv)
- valproate → foetal anticonvulsant syndrome, congenital malformations
- acamprosate → Wernicke–Korsakoff
- disulfiram → alcohol intolerance

## Layout

```
scripts/
  download_faers.sh         fetch all 20 quarters from FDA (retry + zip integrity check)
  faers_manifest.sha256     SHA-256 of every archive used for the published results
  verify_manifest.sh        prove your download matches, byte for byte
pipeline/
  01_parse_faers.py         parse + deduplicate
  03_filter_sud.py          SUD-medication filter, normalization, substance flags
  05_disproportionality.py  triples, 4-method DA, stratified, temporal
  06_export_manuscript.py   validation, tables, figures
  substance_detection.py    the 15-substance detector
  METHODS.md
  results/
    faers_drug_substance_signals.csv   -> Phase 3 contract (47,103 signals)
    faers_temporal_trends.csv          -> Phase 3 contract
    faers_substance_detection_validation.csv
    faers_descriptive_stats.csv
    tables/    Tables 2-6 + per-step counts
    figures/   flow, substance-modification heatmap, temporal, method comparison
```

## Data (not in this repo)

The 20 quarterly archives are ~1.3 GB, and the parsed intermediates are ~4.0 GB
(`drug.csv` alone is 1.8 GB). Neither is versioned — both are fully regenerable, and
`drug.csv` exceeds GitHub's 100 MB per-file limit by 18×.

```bash
scripts/download_faers.sh     # ~1.3 GB from fis.fda.gov
scripts/verify_manifest.sh    # confirm you have the exact bytes behind the results
```

## Running

```bash
pip install -r requirements.txt
cd pipeline
python 01_parse_faers.py      # regenerates results/parsed/ (~4 GB)
python 03_filter_sud.py
python 05_disproportionality.py
python 06_export_manuscript.py
```

## License

MIT (code). FAERS data are public-domain U.S. FDA works, obtained from FDA and not
redistributed here.
