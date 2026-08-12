#!/usr/bin/env python3
"""
PATH 2 / FAERS -- STEPS 1 & 2: parse all quarters + deduplicate.

DATA-REALITY NOTE (verified against the raw files): the public FAERS quarterly ASCII
release contains ONLY structured '$'-delimited coded tables (DEMO, DRUG, REAC, OUTC,
INDI, THER, RPSR). There are NO free-text narratives. The build spec's narrative/NER
steps therefore do not apply to this source; substance detection (Step 6) runs over the
structured text fields (drugname, prod_ai, indi_pt, reaction pt) instead -- the standard
approach for FAERS substance-co-use pharmacovigilance.

Header layout is identical across 2020Q1..2024Q4 (verified), but we still read each
file's header dynamically so the pipeline is robust to layout drift.

Dedup rule (FAERS standard): one record per caseid = the row with the highest
caseversion; ties broken by latest fda_dt, then highest primaryid. We then keep only the
winning primaryid across every table.

Outputs (pipeline/results/parsed/):  demo.csv drug.csv reac.csv outc.csv indi.csv
plus step1_record_counts.csv and step2_dedup_summary.csv.
"""
from __future__ import annotations
import csv, io, re, zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE.parent / "data" / "raw"
OUT = BASE / "results" / "parsed"
TAB = BASE / "results" / "tables"
OUT.mkdir(parents=True, exist_ok=True); TAB.mkdir(parents=True, exist_ok=True)

# columns we keep per table (lower-cased header names)
KEEP = {
    "DEMO": ["primaryid", "caseid", "caseversion", "sex", "age", "age_cod",
             "event_dt", "fda_dt", "init_fda_dt", "occr_country", "occp_cod", "rept_cod"],
    "DRUG": ["primaryid", "drug_seq", "role_cod", "drugname", "prod_ai",
             "route", "dechal", "rechal"],
    "REAC": ["primaryid", "pt", "drug_rec_act"],
    "OUTC": ["primaryid", "outc_cod"],
    "INDI": ["primaryid", "indi_drug_seq", "indi_pt"],
}
csv.field_size_limit(10_000_000)


def quarters():
    for z in sorted(RAW.glob("faers_ascii_*.zip")):
        m = re.search(r"(\d{4})q(\d)", z.name)
        yield z, int(m.group(1)), int(m.group(2))


def open_table(zf: zipfile.ZipFile, table: str, yy: int, q: int):
    """Find the inner ASCII/<TABLE><yy>Q<q>.txt regardless of case."""
    want = f"{table}{yy % 100:02d}q{q}.txt".lower()
    for name in zf.namelist():
        base = name.split("/")[-1].lower()
        if base == want and "ascii" in name.lower():
            return io.TextIOWrapper(zf.open(name), encoding="latin-1", newline="")
    return None


def to_int(x, default=-1):
    try:
        return int(x)
    except (ValueError, TypeError):
        return default


def main():
    # ---------- PASS 1: build dedup map from DEMO ----------
    best = {}            # caseid -> (caseversion, fda_dt, primaryid)
    counts = []          # per quarter/table raw row counts
    for z, yy, q in quarters():
        with zipfile.ZipFile(z) as zf:
            fh = open_table(zf, "DEMO", yy, q)
            if fh is None:
                print(f"  !! no DEMO in {z.name}"); continue
            r = csv.reader(fh, delimiter="$")
            hdr = [h.strip().lower() for h in next(r)]
            ix = {h: i for i, h in enumerate(hdr)}
            n = 0
            for row in r:
                if len(row) <= ix["primaryid"]:
                    continue
                n += 1
                cid = to_int(row[ix["caseid"]]); pid = to_int(row[ix["primaryid"]])
                ver = to_int(row[ix["caseversion"]]); fda = to_int(row[ix["fda_dt"]])
                cur = best.get(cid)
                cand = (ver, fda, pid)
                if cur is None or cand > cur:
                    best[cid] = cand
            counts.append({"quarter": f"{yy}Q{q}", "table": "DEMO", "raw_rows": n})
        print(f"  scanned DEMO {yy}Q{q}: cumulative unique caseids={len(best):,}")

    winning_pids = {v[2] for v in best.values()}
    total_demo = sum(c["raw_rows"] for c in counts if c["table"] == "DEMO")
    print(f"\nPASS1 done: {total_demo:,} DEMO rows -> {len(best):,} unique cases "
          f"({total_demo - len(best):,} duplicate report-versions removed, "
          f"{100*(total_demo-len(best))/total_demo:.1f}%)")

    # ---------- PASS 2: stream every table, keep winning primaryids ----------
    writers = {}
    files = {}
    for t in KEEP:
        f = open(OUT / f"{t.lower()}.csv", "w", newline="", encoding="utf-8")
        w = csv.writer(f)
        w.writerow(KEEP[t] + ["year", "quarter"])
        files[t] = f; writers[t] = w

    for z, yy, q in quarters():
        with zipfile.ZipFile(z) as zf:
            for t in KEEP:
                fh = open_table(zf, t, yy, q)
                if fh is None:
                    continue
                r = csv.reader(fh, delimiter="$")
                hdr = [h.strip().lower() for h in next(r)]
                ix = {h: i for i, h in enumerate(hdr)}
                keep_idx = [(c, ix.get(c)) for c in KEEP[t]]
                pid_i = ix["primaryid"]
                kept = 0; raw = 0
                for row in r:
                    if len(row) <= pid_i:
                        continue
                    raw += 1
                    if to_int(row[pid_i]) not in winning_pids:
                        continue
                    out = [(row[i].strip() if i is not None and i < len(row) else "")
                           for _, i in keep_idx]
                    writers[t].writerow(out + [yy, q])
                    kept += 1
                if t != "DEMO":
                    counts.append({"quarter": f"{yy}Q{q}", "table": t, "raw_rows": raw})
        print(f"  parsed {yy}Q{q}")
    for f in files.values():
        f.close()

    import pandas as pd
    cdf = pd.DataFrame(counts)
    cdf.to_csv(TAB / "step1_record_counts.csv", index=False)
    summary = (cdf.groupby("table").raw_rows.sum().rename("total_raw_rows").reset_index())
    summary.to_csv(TAB / "step1_table_totals.csv", index=False)

    dedup = pd.DataFrame([{
        "total_demo_report_versions": total_demo,
        "unique_cases_after_dedup": len(best),
        "duplicate_versions_removed": total_demo - len(best),
        "duplicate_rate_pct": round(100 * (total_demo - len(best)) / total_demo, 2),
    }])
    dedup.to_csv(TAB / "step2_dedup_summary.csv", index=False)
    print("\n--- raw row totals by table ---")
    print(summary.to_string(index=False))
    print("\nWrote parsed/{demo,drug,reac,outc,indi}.csv + step1/step2 summaries")


if __name__ == "__main__":
    main()
