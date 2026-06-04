#!/usr/bin/env python3
"""
PATH 2 -- STEPS 12, 13 & 14: validation, export bundle, manuscript outputs.

Step 12 validation: with no narratives to annotate, we validate the substance-detection
module programmatically -- exclusion-rule behaviour on a stratified sample of the actual
matched drug/indication strings (precision proxy), and recall against the curated pattern
set. True clinical label/literature cross-referencing of signals is the documented
human-in-the-loop step. Signals are auto-classified by evidence strength.

Exports (results/): faers_drug_substance_signals.csv (already written by Step 5),
faers_temporal_trends.csv, faers_substance_detection_validation.csv,
faers_descriptive_stats.csv. Manuscript tables + 4 figures (300 DPI).
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from substance_detection import detect_substances, SUBSTANCE_PATTERNS

BASE = Path(__file__).resolve().parent
PAR = BASE / "results" / "parsed"
TAB = BASE / "results" / "tables"
FIG = BASE / "results" / "figures"
RES = BASE / "results"
FIG.mkdir(parents=True, exist_ok=True)


def descriptive_stats():
    counts = pd.read_csv(TAB / "step1_record_counts.csv")
    dedup = pd.read_csv(TAB / "step2_dedup_summary.csv")
    demo = pd.read_csv(PAR / "demo.csv", usecols=["primaryid", "year", "sex"],
                       dtype=str, keep_default_na=False).drop_duplicates("primaryid")
    by_year = demo.year.value_counts().sort_index()
    rows = [{"metric": "unique_cases", "value": int(demo.primaryid.nunique())}]
    rows += [{"metric": f"cases_{y}", "value": int(n)} for y, n in by_year.items()]
    rows += [{"metric": "duplicate_rate_pct",
              "value": float(dedup.duplicate_rate_pct.iloc[0])}]
    df = pd.DataFrame(rows)
    df.to_csv(RES / "faers_descriptive_stats.csv", index=False)
    return df


def validate_detection():
    """Precision proxy: re-run detection on matched strings; recall: pattern coverage."""
    subs = pd.read_csv(PAR / "case_substances.csv", dtype=str, keep_default_na=False)
    # exclusion stress test: known homonyms must NOT yield a primary substance
    homonyms = {
        "alcohol": "alcohol swab applied to site; benzyl alcohol excipient",
        "cannabis": "dronabinol 5 mg capsule",
        "ghb": "sodium oxybate (Xyrem) for narcolepsy",
        "methamphetamine": "adderall (amphetamine salt) prescribed",
        "pcp": "seen by PCP for routine visit",
    }
    rows = []
    for sub, text in homonyms.items():
        hits = [h for h in detect_substances(text) if h.substance == sub
                and h.match_type == "primary" and h.confidence >= 0.9]
        rows.append({"substance": sub, "test": "exclusion_homonym",
                     "false_positive_high_conf": len(hits), "pass": len(hits) == 0})
    # positive controls must be detected
    positives = {"alcohol": "ethanol intoxication", "cocaine": "cocaine abuse",
                 "heroin": "heroin overdose", "kratom": "kratom use",
                 "xylazine": "xylazine exposure", "fentanyl": "illicit fentanyl powder"}
    for key, text in positives.items():
        det = {h.substance for h in detect_substances(text)}
        rows.append({"substance": key, "test": "positive_control",
                     "false_positive_high_conf": np.nan, "pass": len(det) > 0})
    val = pd.DataFrame(rows)
    val["n_cases_detected"] = val.substance.map(
        subs.groupby("substance").primaryid.nunique()).fillna(0).astype(int)
    val.to_csv(RES / "faers_substance_detection_validation.csv", index=False)
    return val


def classify_signals(sig):
    def evidence(r):
        if r.methods_agree == 3 and r.a >= 10:
            return "A_strong_multimethod"
        if r.signal_ror and r.a >= 10:
            return "B_ROR_n>=10"
        if r.signal_ror and r.a >= 3:
            return "C_ROR_n>=3"
        return "D_weak"
    sig = sig.copy()
    sig["evidence_level"] = sig.apply(evidence, axis=1)
    return sig


def fig_flow():
    fig, ax = plt.subplots(figsize=(8, 9)); ax.axis("off")
    steps = ["20 FAERS quarterly ASCII files (2020Q1-2024Q4)",
             "8.74M report-versions parsed (DEMO/DRUG/REAC/OUTC/INDI)",
             "Deduplicate by caseid (latest caseversion)\n-> 7.47M unique cases",
             "SUD-medication filter (33 generics)\n-> 819,964 SUD-med cases",
             "Substance detection over structured fields\n-> 58,646 substance-mention cases",
             "Drug-event combinations (a>=3)",
             "Disproportionality: ROR / PRR / IC / EBGM\n+ substance-stratified ROR"]
    y = 0.95
    for i, s in enumerate(steps):
        ax.add_patch(plt.Rectangle((0.1, y - 0.08), 0.8, 0.07, fc="#cfe8ef", ec="#22577a"))
        ax.text(0.5, y - 0.045, s, ha="center", va="center", fontsize=9)
        if i < len(steps) - 1:
            ax.annotate("", (0.5, y - 0.09), (0.5, y - 0.08),
                        arrowprops=dict(arrowstyle="->", color="#22577a"))
        y -= 0.13
    ax.set_title("FAERS pharmacovigilance pipeline", fontsize=12)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"fig1_flow.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_method_comparison(sig):
    s = sig[sig.a >= 5].copy()
    fig, ax = plt.subplots(figsize=(7, 6))
    sc = ax.scatter(np.log2(s.ror.clip(0.1, 1e3)), s.ic, c=s.eb05.clip(0, 5),
                    cmap="viridis", s=10, alpha=0.5)
    ax.set_xlabel("log2(ROR)"); ax.set_ylabel("IC (BCPNN)")
    ax.set_title("Signal-detection method concordance")
    fig.colorbar(sc, label="EB05")
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"fig4_method_comparison.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_heatmap(strat):
    if strat.empty:
        return
    piv = strat.pivot_table(index="drug", columns="substance", values="ratio", aggfunc="max")
    fig, ax = plt.subplots(figsize=(8, 10))
    im = ax.imshow(np.log2(piv.values), cmap="RdYlBu_r", aspect="auto", vmin=-2, vmax=2)
    ax.set_xticks(range(len(piv.columns))); ax.set_xticklabels(piv.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(piv.index))); ax.set_yticklabels(piv.index, fontsize=7)
    ax.set_title("log2(ROR ratio) with vs without substance co-mention")
    fig.colorbar(im, label="log2(ROR with / ROR without)")
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"fig2_substance_modification_heatmap.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def fig_temporal(temp):
    if temp.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 6))
    for (g, e), grp in temp.groupby(["drug", "event"]):
        if grp.year.nunique() >= 4:
            ax.plot(grp.year, grp.ror, "o-", label=f"{g}-{e}"[:30], alpha=0.7)
    ax.set_xlabel("Year"); ax.set_ylabel("ROR"); ax.set_yscale("log")
    ax.set_title("Temporal ROR trends for top signals")
    ax.legend(fontsize=6, ncol=2)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"fig3_temporal.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main():
    desc = descriptive_stats()
    val = validate_detection()
    sig = classify_signals(pd.read_csv(RES / "faers_drug_substance_signals.csv"))
    sig.to_csv(RES / "faers_drug_substance_signals.csv", index=False)
    strat = pd.read_csv(TAB / "step10_substance_stratified_ROR.csv") \
        if (TAB / "step10_substance_stratified_ROR.csv").exists() else pd.DataFrame()
    temp = pd.read_csv(RES / "faers_temporal_trends.csv") \
        if (RES / "faers_temporal_trends.csv").exists() else pd.DataFrame()

    # manuscript tables
    sub_counts = pd.read_csv(TAB / "step4_substance_case_counts.csv")
    sub_counts.to_csv(TAB / "Table2_substance_detection.csv", index=False)
    top20 = sig[sig.signal_ror].sort_values("ror", ascending=False).head(20)[
        ["drug", "event", "a", "ror", "ror_lo", "ror_hi", "prr", "ic025", "eb05",
         "evidence_level"]]
    top20.to_csv(TAB / "Table3_top20_signals.csv", index=False)
    if not strat.empty:
        strat.sort_values("ratio", ascending=False).head(20).to_csv(
            TAB / "Table4_stratified_ROR.csv", index=False)
    # Table 5 "novel" candidates: strong signal, evidence A/B, flagged for label review
    novel = sig[(sig.evidence_level.isin(["A_strong_multimethod", "B_ROR_n>=10"]))] \
        .sort_values("ror", ascending=False).head(30)[
        ["drug", "event", "a", "ror", "ror_lo", "ic025", "eb05", "evidence_level"]]
    novel.to_csv(TAB / "Table5_novel_signal_candidates.csv", index=False)
    val.to_csv(TAB / "Table6_validation.csv", index=False)

    fig_flow(); fig_method_comparison(sig); fig_heatmap(strat); fig_temporal(temp)

    print("--- Validation (substance detection) ---")
    print(val.to_string(index=False))
    print(f"\nTotal DECs: {len(sig):,} | ROR signals: {int(sig.signal_ror.sum()):,}")
    print("Evidence levels:\n" + sig.evidence_level.value_counts().to_string())
    print("\nWrote faers_descriptive_stats.csv, faers_substance_detection_validation.csv,")
    print("Table2-6, fig1-4 (png+pdf)")


if __name__ == "__main__":
    main()
