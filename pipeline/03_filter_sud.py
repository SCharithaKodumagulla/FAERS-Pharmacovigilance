#!/usr/bin/env python3
"""
PATH 2 -- STEPS 3, 4 & 7 (folded for the structured-data reality):
  * Step 3  Filter DRUG records to SUD-relevant medications.
  * Step 7  Normalize each matched drug to a canonical generic (prod_ai-first; exact
            then word-boundary brand/generic alternation). Heavy RxNorm-API enrichment
            is noted as a future add; prod_ai already carries the active ingredient.
  * Step 4  "Narrative" reality: none exist -> build the case text blob from structured
            fields and run the substance-detection module over it (Step 6 module).

Efficiency: detection/normalization is computed once per UNIQUE drug string (there are
orders of magnitude fewer unique strings than the 30M drug rows) and cached.

Output (results/parsed/): case_sud_meds.csv  (primaryid, generic, role_cod, year, quarter)
                          case_substances.csv (primaryid, substance, match_type, conf, source)
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd
from substance_detection import detect_substances

BASE = Path(__file__).resolve().parent
PAR = BASE / "results" / "parsed"
TAB = BASE / "results" / "tables"

# canonical generic -> list of brand/generic tokens (lowercased substrings/word stems)
SUD_MEDS = {
    "buprenorphine": ["buprenorphine", "suboxone", "subutex", "sublocade", "zubsolv", "bunavail"],
    "methadone": ["methadone", "dolophine", "methadose"],
    "naltrexone": ["naltrexone", "vivitrol", "revia"],
    "naloxone": ["naloxone", "narcan"],
    "disulfiram": ["disulfiram", "antabuse"],
    "acamprosate": ["acamprosate", "campral"],
    "sertraline": ["sertraline", "zoloft"],
    "fluoxetine": ["fluoxetine", "prozac"],
    "paroxetine": ["paroxetine", "paxil"],
    "citalopram": ["citalopram", "celexa"],
    "escitalopram": ["escitalopram", "lexapro"],
    "venlafaxine": ["venlafaxine", "effexor"],
    "duloxetine": ["duloxetine", "cymbalta"],
    "desvenlafaxine": ["desvenlafaxine", "pristiq"],
    "alprazolam": ["alprazolam", "xanax"],
    "clonazepam": ["clonazepam", "klonopin"],
    "diazepam": ["diazepam", "valium"],
    "lorazepam": ["lorazepam", "ativan"],
    "gabapentin": ["gabapentin", "neurontin"],
    "pregabalin": ["pregabalin", "lyrica"],
    "quetiapine": ["quetiapine", "seroquel"],
    "trazodone": ["trazodone", "desyrel"],
    "buspirone": ["buspirone", "buspar"],
    "hydroxyzine": ["hydroxyzine", "vistaril", "atarax"],
    "bupropion": ["bupropion", "wellbutrin", "zyban"],
    "mirtazapine": ["mirtazapine", "remeron"],
    "aripiprazole": ["aripiprazole", "abilify"],
    "olanzapine": ["olanzapine", "zyprexa"],
    "risperidone": ["risperidone", "risperdal"],
    "lithium": ["lithium", "lithobid", "eskalith"],
    "valproate": ["valproate", "valproic", "divalproex", "depakote", "depakene"],
    "lamotrigine": ["lamotrigine", "lamictal"],
    "topiramate": ["topiramate", "topamax"],
}
# token -> canonical, longest-token-first matching
_TOKEN2GEN = []
for gen, toks in SUD_MEDS.items():
    for t in toks:
        _TOKEN2GEN.append((t, gen))
_TOKEN2GEN.sort(key=lambda x: -len(x[0]))
_ALT = re.compile(r"\b(" + "|".join(re.escape(t) for t, _ in _TOKEN2GEN) + r")\b", re.I)
_LOOKUP = {t: g for t, g in _TOKEN2GEN}


def normalize_to_sud(text: str):
    """Return canonical generic if the drug string maps to a SUD med, else None."""
    if not text:
        return None
    m = _ALT.search(text.lower())
    return _LOOKUP.get(m.group(1)) if m else None


def main():
    # ---- cache per-unique-string results over the whole DRUG table ----
    print("Reading DRUG (chunked) and caching unique-string normalization/detection...")
    drug_cols = ["primaryid", "role_cod", "drugname", "prod_ai", "year", "quarter"]
    sud_parts = []
    subs_rows = []
    seen_strings = {}     # combined drug text -> (generic_or_None, [substance hits])
    n = 0
    for chunk in pd.read_csv(PAR / "drug.csv", usecols=drug_cols, dtype=str,
                             chunksize=2_000_000, keep_default_na=False):
        n += len(chunk)
        chunk["blob"] = (chunk["drugname"].fillna("") + " " + chunk["prod_ai"].fillna("")).str.strip()
        for blob in chunk["blob"].unique():
            if blob not in seen_strings:
                hits = detect_substances(blob)
                seen_strings[blob] = (normalize_to_sud(blob),
                                      [(h.substance, h.match_type, h.confidence) for h in hits])
        # SUD meds -- vectorized
        chunk["generic"] = chunk["blob"].map(lambda b: seen_strings[b][0])
        sud_parts.append(chunk.loc[chunk["generic"].notna(),
                                   ["primaryid", "generic", "role_cod", "year", "quarter"]])
        # substance hits -- only the (rare) rows whose blob produced a hit
        hit_blobs = {b for b in chunk["blob"].unique() if seen_strings[b][1]}
        if hit_blobs:
            for _, row in chunk.loc[chunk["blob"].isin(hit_blobs)].iterrows():
                for sub, mt, cf in seen_strings[row.blob][1]:
                    subs_rows.append((row.primaryid, sub, mt, cf, "drug_product"))
        print(f"   ...{n:,} drug rows; unique strings cached={len(seen_strings):,}")

    sud = pd.concat(sud_parts, ignore_index=True)
    sud.drop_duplicates().to_csv(PAR / "case_sud_meds.csv", index=False)

    # also detect substances mentioned as INDICATIONS (e.g. "Substance abuse", "Alcohol use")
    print("Scanning INDI for substance mentions...")
    indi = pd.read_csv(PAR / "indi.csv", usecols=["primaryid", "indi_pt"], dtype=str,
                       keep_default_na=False)
    indi_cache = {}
    for pt, grp in indi.groupby("indi_pt", sort=False):
        if pt not in indi_cache:
            indi_cache[pt] = [(h.substance, h.match_type, h.confidence) for h in detect_substances(pt)]
        for sub, mt, cf in indi_cache[pt]:
            for pid in grp.primaryid:
                subs_rows.append((pid, sub, mt, cf, "indication"))

    subs = pd.DataFrame(subs_rows, columns=["primaryid", "substance", "match_type",
                                            "confidence", "source"])
    subs = subs.sort_values("confidence", ascending=False).drop_duplicates(
        ["primaryid", "substance"])
    subs.to_csv(PAR / "case_substances.csv", index=False)

    # summaries
    sud_summary = sud.drop_duplicates(["primaryid", "generic"]).groupby("generic").primaryid.nunique() \
        .sort_values(ascending=False).rename("n_cases").reset_index()
    sud_summary.to_csv(TAB / "step3_sud_med_case_counts.csv", index=False)
    sub_summary = subs.groupby("substance").primaryid.nunique().sort_values(ascending=False) \
        .rename("n_cases").reset_index()
    sub_summary.to_csv(TAB / "step4_substance_case_counts.csv", index=False)

    print(f"\nSUD-med cases: {sud.primaryid.nunique():,} | substance-mention cases: {subs.primaryid.nunique():,}")
    print("\n--- top SUD meds by case count ---")
    print(sud_summary.head(15).to_string(index=False))
    print("\n--- substance mentions by case count ---")
    print(sub_summary.to_string(index=False))


if __name__ == "__main__":
    main()
