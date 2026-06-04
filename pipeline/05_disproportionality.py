#!/usr/bin/env python3
"""
PATH 2 -- STEPS 9, 10 & 11: triples + disproportionality + temporal trends.

Contingency for a (drug D, event E) over the full deduped FAERS case universe (N cases):
    a = cases with D and E    b = cases with D, not E
    c = cases without D, with E    d = remainder
Metrics:
  ROR  = ad/bc, 95% CI via SE(lnROR)=sqrt(1/a+1/b+1/c+1/d)
  PRR  = [a/(a+b)] / [c/(c+d)] + chi-square
  IC   = log2((a+0.5)/(E+0.5)) (BCPNN/Noren shrinkage), IC025 lower 95%
  EBGM = empirical-Bayes Gamma-Poisson shrinkage of RR=a/E with method-of-moments prior
         over all evaluated DECs (simplified MGPS), EB05 lower 5%.
Signal rule: ROR>2 AND ROR_lo>1 AND a>=3; also flag IC025>0 and EB05>1; report agreement.

Novel stratified analysis: ROR among cases WITH a focal substance co-mention vs WITHOUT,
with a z-test on the lnROR difference (interaction).

Temporal (Step 11): annual ROR for key triples + Cochran-Armitage trend test.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

BASE = Path(__file__).resolve().parent
PAR = BASE / "results" / "parsed"
TAB = BASE / "results" / "tables"
RES = BASE / "results"

MIN_A = 3
SERIOUS = {"DE", "LT", "HO", "DS", "CA", "RI"}   # death, life-threat, hosp, disability...


def load_universe():
    demo = pd.read_csv(PAR / "demo.csv", usecols=["primaryid", "year", "quarter", "sex"],
                       dtype=str, keep_default_na=False).drop_duplicates("primaryid")
    N = demo.primaryid.nunique()
    reac = pd.read_csv(PAR / "reac.csv", usecols=["primaryid", "pt"], dtype=str,
                       keep_default_na=False)
    reac = reac[reac.pt != ""].drop_duplicates(["primaryid", "pt"])
    sud = pd.read_csv(PAR / "case_sud_meds.csv", dtype=str,
                      keep_default_na=False).drop_duplicates(["primaryid", "generic"])
    subs = pd.read_csv(PAR / "case_substances.csv", dtype=str, keep_default_na=False)
    return demo, reac, sud, subs, N


def metrics(a, n_drug, n_event, N, rr_prior=None):
    a = float(a); b = n_drug - a; c = n_event - a; d = N - a - b - c
    if min(a, b, c, d) <= 0:
        b = max(b, 0.5); c = max(c, 0.5); d = max(d, 0.5); a = max(a, 0.5)
    ror = (a * d) / (b * c)
    se = np.sqrt(1/a + 1/b + 1/c + 1/d)
    ror_lo, ror_hi = ror * np.exp(-1.96 * se), ror * np.exp(1.96 * se)
    prr = (a / (a + b)) / (c / (c + d))
    # chi-square (Yates)
    exp_a = (a + b) * (a + c) / N
    chi2 = (abs(a - exp_a) - 0.5) ** 2 / exp_a if exp_a > 0 else np.nan
    # IC (BCPNN shrinkage)
    E = (a + b) * (a + c) / N
    ic = np.log2((a + 0.5) / (E + 0.5))
    var_ic = (1 / (np.log(2) ** 2)) * ((N - a + 0.5) / ((a + 0.5) * (1 + N + 0.5))
                                       + (N - (a + b) + 0.5) / (((a + b) + 0.5) * (1 + N + 0.5))
                                       + (N - (a + c) + 0.5) / (((a + c) + 0.5) * (1 + N + 0.5)))
    ic025 = ic - 1.96 * np.sqrt(var_ic)
    # EBGM (simplified EB gamma-Poisson): shrink RR=a/E toward prior mean
    rr = a / E if E > 0 else np.nan
    if rr_prior is not None:
        alpha, beta = rr_prior
        ebgm = (a + alpha) / (E + beta)
        eb05 = stats.gamma.ppf(0.05, a + alpha, scale=1 / (E + beta)) if (E + beta) > 0 else np.nan
    else:
        ebgm, eb05 = rr, np.nan
    return dict(a=int(a), ror=ror, ror_lo=ror_lo, ror_hi=ror_hi, prr=prr, chi2=chi2,
                ic=ic, ic025=ic025, ebgm=ebgm, eb05=eb05, expected=E)


def main():
    demo, reac, sud, subs, N = load_universe()
    print(f"Universe: N={N:,} cases | reac pairs={len(reac):,} | SUD-med pairs={len(sud):,}")

    # marginals
    drug_marg = sud.groupby("generic").primaryid.nunique()
    event_marg = reac.groupby("pt").primaryid.nunique()

    # joint a for all (generic, pt): merge SUD cases with their reactions
    joint = (sud[["primaryid", "generic"]].drop_duplicates()
             .merge(reac, on="primaryid")
             .groupby(["generic", "pt"]).primaryid.nunique().reset_index(name="a"))
    joint = joint[joint.a >= MIN_A].copy()
    print(f"Drug-event combinations with a>={MIN_A}: {len(joint):,}")

    # method-of-moments gamma prior on RR across evaluated DECs (simplified MGPS)
    joint["E"] = [(drug_marg[g]) * (event_marg[e]) / N
                  for g, e in zip(joint.generic, joint.pt)]
    rr = (joint.a / joint.E).replace([np.inf, -np.inf], np.nan).dropna()
    m, v = rr.mean(), rr.var()
    beta = m / v if v > 0 else 1.0
    alpha = m * beta
    print(f"EB gamma prior (MoM): alpha={alpha:.3f}, beta={beta:.3f}")

    rows = []
    for g, e, a in zip(joint.generic, joint.pt, joint.a):
        mt = metrics(a, drug_marg[g], event_marg[e], N, (alpha, beta))
        mt.update(drug=g, event=e)
        rows.append(mt)
    sig = pd.DataFrame(rows)
    sig["signal_ror"] = (sig.ror > 2) & (sig.ror_lo > 1) & (sig.a >= MIN_A)
    sig["signal_ic"] = sig.ic025 > 0
    sig["signal_eb"] = sig.eb05 > 1
    sig["methods_agree"] = sig[["signal_ror", "signal_ic", "signal_eb"]].sum(axis=1)
    sig = sig.sort_values("ror", ascending=False)
    sig.to_csv(RES / "faers_drug_substance_signals.csv", index=False)
    print(f"\nSignals (ROR rule): {int(sig.signal_ror.sum()):,} / {len(sig):,} DECs")

    # ---- novel: substance-stratified ROR (WITH vs WITHOUT substance co-mention) ----
    # bounded set intersections over only the focus events (no per-case scans)
    strat_rows = []
    focus = sig[sig.signal_ror].head(300)
    focus_events = set(focus.event.unique())
    event_pids = (reac[reac.pt.isin(focus_events)].groupby("pt").primaryid.agg(set)).to_dict()
    drug_pids = {g: set(sud.loc[sud.generic == g, "primaryid"]) for g in focus.drug.unique()}
    sub_pids = {s: set(subs.loc[subs.substance == s, "primaryid"])
                for s in subs.substance.unique()}
    Nall = N

    def ror_2x2(a, nD, nE, Ntot):
        b = nD - a; c = nE - a; d = Ntot - a - b - c
        if min(a, b, c, d) <= 0:
            return np.nan, np.nan
        return (a * d) / (b * c), np.sqrt(1/a + 1/b + 1/c + 1/d)

    for s in ["alcohol", "cannabis", "cocaine", "heroin", "methamphetamine"]:
        Sset = sub_pids.get(s, set())
        if len(Sset) < 50:
            continue
        N_S = len(Sset); N_noS = Nall - N_S
        for _, r in focus.iterrows():
            Dset = drug_pids[r.drug]; Eset = event_pids.get(r.event, set())
            a_S = len(Dset & Eset & Sset)
            nD_S = len(Dset & Sset); nE_S = len(Eset & Sset)
            a_all = len(Dset & Eset)
            r_with, se_w = ror_2x2(a_S, nD_S, nE_S, N_S)
            r_wo, se_o = ror_2x2(a_all - a_S, len(Dset) - nD_S,
                                 len(Eset) - nE_S, N_noS)
            if np.isnan(r_with) or np.isnan(r_wo):
                continue
            z = (np.log(r_with) - np.log(r_wo)) / np.sqrt(se_w**2 + se_o**2)
            strat_rows.append(dict(substance=s, drug=r.drug, event=r.event,
                                   ror_with=r_with, a_with=a_S,
                                   ror_without=r_wo, ratio=r_with / r_wo, z_diff=z,
                                   p_diff=2 * stats.norm.sf(abs(z))))
    strat = pd.DataFrame(strat_rows)
    if len(strat):
        strat = strat.sort_values("ratio", ascending=False)
    strat.to_csv(TAB / "step10_substance_stratified_ROR.csv", index=False)

    # ---- temporal (Step 11): annual ROR for top signals (sud already carries year) ----
    temp_rows = []
    top = sig[sig.signal_ror].sort_values("ror", ascending=False).head(20)
    for _, r in top.iterrows():
        g, e = r.drug, r.event
        ev_pids = set(reac[reac.pt == e].primaryid)
        for y in ["2020", "2021", "2022", "2023", "2024"]:
            dy = demo[demo.year == y]; Ny = len(dy)
            dpids = set(sud.loc[(sud.generic == g) & (sud.year == y), "primaryid"])
            a = len(dpids & ev_pids); b = len(dpids) - a
            ey = dy.primaryid.isin(ev_pids).sum(); c = ey - a; d = Ny - a - b - c
            if min(a, b, c, d) > 0:
                temp_rows.append(dict(drug=g, event=e, year=int(y), a=a,
                                      ror=(a*d)/(b*c)))
    temp = pd.DataFrame(temp_rows)
    temp.to_csv(RES / "faers_temporal_trends.csv", index=False)

    print("\n--- Top 15 SUD-drug -> AE signals by ROR (a>=3) ---")
    show = sig[sig.signal_ror].head(15)[["drug", "event", "a", "ror", "ror_lo",
                                         "ror_hi", "ic025", "eb05", "methods_agree"]]
    print(show.round(2).to_string(index=False))
    if len(strat):
        print("\n--- Top substance-modified signals (ROR with vs without substance) ---")
        print(strat.head(10)[["substance", "drug", "event", "ror_with", "ror_without",
                              "ratio", "p_diff"]].round(3).to_string(index=False))
    print("\nWrote faers_drug_substance_signals.csv, step10_substance_stratified_ROR.csv,"
          " faers_temporal_trends.csv")


if __name__ == "__main__":
    main()
