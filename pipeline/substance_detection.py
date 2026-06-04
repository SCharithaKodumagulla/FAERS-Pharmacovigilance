#!/usr/bin/env python3
"""
Substance detection module (PATH 2 novel component, Step 6).

Adapted to FAERS reality: there are no free-text narratives, so detection runs over the
concatenated structured text a case offers -- reported drug products (drugname/prod_ai),
indications (indi_pt) and reactions (pt). Each substance has primary / contextual /
exclusion patterns; exclusions suppress legitimate medical homonyms (alcohol swab,
dronabinol, sodium oxybate, ...). Returns one hit per substance with match type,
confidence, the matched span, and a context window.
"""
from __future__ import annotations
import re
from dataclasses import dataclass

SUBSTANCE_PATTERNS = {
    'alcohol': {
        'primary': [r'\balcohol\b', r'\bethanol\b', r'\bEtOH\b'],
        'contextual': [r'\bdrinking\b', r'\bintoxicat\w+\b', r'\bwhiskey\b', r'\bwine\b',
                       r'\bbeer\b', r'\bvodka\b', r'\bBAC\b'],
        'exclusions': [r'\balcohol\s*swab\b', r'\bisopropyl\s*alcohol\b',
                       r'\brubbing\s*alcohol\b', r'\bcetyl\s*alcohol\b',
                       r'\bbenzyl\s*alcohol\b', r'\bpolyvinyl\s*alcohol\b']},
    'cannabis': {
        'primary': [r'\bcannabis\b', r'\bmarijuana\b', r'\bTHC\b', r'\bdelta[\s-]?[89]\b'],
        'contextual': [r'\bedible[s]?\b', r'\bweed\b', r'\bhash\w*\b', r'\bcannabinoid\b'],
        'exclusions': [r'\bdronabinol\b', r'\bnabilone\b', r'\bepidiolex\b']},
    'cocaine': {
        'primary': [r'\bcocaine\b'],
        'contextual': [r'\bcrack\b(?!\s*lip)'],
        'exclusions': [r'\bcocaine\s*hydrochloride\s*(?:topical|ophthalmic)\b']},
    'methamphetamine': {
        'primary': [r'\bmethamphetamine\b', r'\bmethamph\b'],
        'contextual': [r'\bcrystal\s*meth\b'],
        'exclusions': [r'\bamphetamine\s*salt\b', r'\badderall\b', r'\bvyvanse\b',
                       r'\bdextroamphetamine\b']},
    'heroin': {
        'primary': [r'\bheroin\b', r'\bdiacetylmorphine\b'], 'contextual': [],
        'exclusions': []},
    'illicit_fentanyl': {
        'primary': [r'\billicit\s+fentanyl\b', r'\bstreet\s+fentanyl\b',
                    r'\bcounterfeit\b.*\bfentanyl\b'],
        'contextual': [r'\bfentanyl\b.*\blaced\b', r'\bfentanyl\b.*\bpowder\b'],
        'exclusions': [r'\bfentanyl\s*(?:patch|transdermal|lozenge|citrate|prescribed)\b']},
    'xylazine': {
        'primary': [r'\bxylazine\b'], 'contextual': [r'\btranq\b', r'\btranq\s*dope\b'],
        'exclusions': []},
    'kratom': {
        'primary': [r'\bkratom\b', r'\bmitragyn\w+\b'], 'contextual': [], 'exclusions': []},
    'tianeptine': {
        'primary': [r'\btianeptine\b'],
        'contextual': [r'\bgas\s*station\s*heroin\b', r'\bZaZa\b', r'\bTianna\b'],
        'exclusions': []},
    'phenibut': {'primary': [r'\bphenibut\b'], 'contextual': [], 'exclusions': []},
    'nitazenes': {
        'primary': [r'\bnitazene\b', r'\bisotonitazene\b', r'\bmetonitazene\b',
                    r'\bprotonitazene\b', r'\betonitaz\w+\b'],
        'contextual': [], 'exclusions': []},
    'designer_benzodiazepines': {
        'primary': [r'\bflualprazolam\b', r'\bclonazolam\b', r'\bflubromazolam\b',
                    r'\betizolam\b', r'\bbromazolam\b'],
        'contextual': [r'\bdesigner\s*benzo\b', r'\bRC\s*benzo\b'], 'exclusions': []},
    'mdma': {
        'primary': [r'\bMDMA\b', r'\bmethylenedioxymethamphetamine\b'],
        'contextual': [r'\becstasy\b', r'\bmolly\b'], 'exclusions': []},
    'ghb': {
        'primary': [r'\bGHB\b', r'\bgamma-hydroxybutyrate\b'],
        'contextual': [], 'exclusions': [r'\bsodium\s*oxybate\b', r'\bXyrem\b']},
    'pcp': {
        'primary': [r'\bPCP\b(?!.*primary\s*care)', r'\bphencyclidine\b'],
        'contextual': [],
        'exclusions': [r'\bPCP\b.*(?:visit|appointment|doctor|physician|provider)\b']},
}

# pre-compile
_COMPILED = {
    s: {kind: [re.compile(p, re.IGNORECASE) for p in pats]
        for kind, pats in groups.items()}
    for s, groups in SUBSTANCE_PATTERNS.items()
}


@dataclass
class SubstanceHit:
    substance: str
    match_type: str        # 'primary' | 'contextual'
    confidence: float
    matched_text: str
    context: str


def _context(text, m, width=40):
    a = max(0, m.start() - width); b = min(len(text), m.end() + width)
    return text[a:b].replace("\n", " ").strip()


def detect_substances(text: str) -> list[SubstanceHit]:
    """Return at most one hit per substance for the given text blob."""
    if not text:
        return []
    hits = []
    for sub, groups in _COMPILED.items():
        if any(rx.search(text) for rx in groups["exclusions"]):
            # if an exclusion fires, require a *primary* hit that is not the excluded span
            excl = True
        else:
            excl = False
        chosen = None
        for rx in groups["primary"]:
            m = rx.search(text)
            if m:
                chosen = SubstanceHit(sub, "primary", 0.95, m.group(0), _context(text, m))
                break
        if chosen is None and not excl:
            for rx in groups["contextual"]:
                m = rx.search(text)
                if m:
                    chosen = SubstanceHit(sub, "contextual", 0.70, m.group(0),
                                          _context(text, m))
                    break
        # exclusion present and no clear primary -> treat as medical homonym, skip
        if chosen is not None and excl and chosen.match_type == "primary":
            # primary still wins but flag lower confidence (homonym nearby)
            chosen.confidence = 0.80
        if chosen is not None and not (excl and chosen.match_type == "contextual"):
            hits.append(chosen)
    return hits


if __name__ == "__main__":
    tests = [
        "Patient used alcohol and cocaine; given alcohol swab before injection.",
        "Reported dronabinol therapy (no cannabis).",
        "Xylazine (tranq) wound; illicit fentanyl powder laced.",
        "Sodium oxybate prescribed for narcolepsy.",  # GHB exclusion
        "Suboxone patient also using street fentanyl and kratom.",
    ]
    for t in tests:
        print("TEXT:", t)
        for h in detect_substances(t):
            print(f"   -> {h.substance:18s} [{h.match_type}] '{h.matched_text}' (conf {h.confidence})")
        print()
