"""Regression tests for the substance detector.

METHODS.md claims the detector "passes all exclusion-homonym and positive-control tests",
but that claim was only ever exercised by a print-based demo in
`pipeline/substance_detection.py`. These are the assertions behind it.

The exclusion patterns are the load-bearing part: every false positive here would inflate
the substance-co-mention counts that the whole substance-stratified ROR analysis rests on.
An alcohol swab is not alcohol use.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from substance_detection import detect_substances  # noqa: E402


def found(text: str) -> set[str]:
    return {h.substance for h in detect_substances(text)}


# --------------------------------------------------------------------------
# Exclusion homonyms: text that LOOKS like substance use but is not
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,must_not_find", [
    ("Cleaned site with an alcohol swab prior to injection.", "alcohol"),
    ("Isopropyl alcohol applied topically.", "alcohol"),
    ("Cetyl alcohol listed as an excipient.", "alcohol"),
    ("Benzyl alcohol preservative in the formulation.", "alcohol"),
    ("Polyvinyl alcohol ophthalmic solution.", "alcohol"),
    ("Patient started on dronabinol for appetite.", "cannabis"),
    ("Nabilone prescribed for nausea.", "cannabis"),
    ("Epidiolex titrated for seizure control.", "cannabis"),
    ("Amphetamine salt combo 20mg daily.", "methamphetamine"),
    ("Adderall prescribed for ADHD.", "methamphetamine"),
    ("Vyvanse 40mg every morning.", "methamphetamine"),
    ("Dextroamphetamine initiated.", "methamphetamine"),
    ("Sodium oxybate prescribed for narcolepsy.", "ghb"),
    ("Xyrem dosing adjusted overnight.", "ghb"),
    ("Referred back to PCP for follow-up appointment.", "pcp"),
    ("Discussed with the patient's PCP physician.", "pcp"),
    ("Fentanyl patch 25 mcg/hr for cancer pain.", "illicit_fentanyl"),
    ("Fentanyl citrate administered peri-operatively.", "illicit_fentanyl"),
    ("Cocaine hydrochloride topical for ENT procedure.", "cocaine"),
])
def test_exclusions_do_not_fire(text, must_not_find):
    assert must_not_find not in found(text), (
        f"false positive: {must_not_find!r} detected in {text!r}"
    )


# --------------------------------------------------------------------------
# Positive controls: genuine substance use must still be detected
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Patient reports heavy drinking and intoxication.", "alcohol"),
    ("Daily ethanol use reported.", "alcohol"),
    ("Marijuana use daily; THC positive.", "cannabis"),
    ("Uses cannabis edibles nightly.", "cannabis"),
    ("Crystal meth use for two years.", "methamphetamine"),
    ("Methamphetamine-induced psychosis.", "methamphetamine"),
    ("Heroin injection use.", "heroin"),
    ("Illicit fentanyl powder found.", "illicit_fentanyl"),
    ("Street fentanyl overdose.", "illicit_fentanyl"),
    ("Xylazine wound necrosis.", "xylazine"),
    ("Tranq dope exposure.", "xylazine"),
    ("Kratom taken for withdrawal.", "kratom"),
    ("Tianeptine purchased at a gas station.", "tianeptine"),
    ("Phenibut taken for anxiety.", "phenibut"),
    ("Isotonitazene detected on tox screen.", "nitazenes"),
    ("Flualprazolam identified in the sample.", "designer_benzodiazepines"),
    ("Bromazolam counterfeit tablet.", "designer_benzodiazepines"),
    ("MDMA ingestion at a concert.", "mdma"),
    ("Took molly recreationally.", "mdma"),
    ("GHB overdose in the emergency department.", "ghb"),
    ("Phencyclidine intoxication.", "pcp"),
    ("Cocaine use and crack pipe found.", "cocaine"),
])
def test_positive_controls_fire(text, expected):
    assert expected in found(text), f"missed {expected!r} in {text!r}"


# --------------------------------------------------------------------------
# Multi-substance and boundary behaviour
# --------------------------------------------------------------------------

def test_detects_multiple_substances_in_one_report():
    hits = found("Xylazine (tranq) wound; illicit fentanyl powder laced.")
    assert {"xylazine", "illicit_fentanyl"} <= hits


def test_prescribed_fentanyl_and_street_fentanyl_are_distinguished():
    # The same report can carry a prescribed opioid and an illicit one; only the illicit
    # form should count as substance use.
    assert "illicit_fentanyl" not in found("Fentanyl transdermal patch, prescribed.")
    assert "illicit_fentanyl" in found("Counterfeit tablet containing fentanyl.")


def test_exclusion_suppresses_only_the_excluded_occurrence():
    # The whole point of span-based exclusion: a homonym must not mask a genuine mention
    # elsewhere in the same report.
    assert "alcohol" not in found("Site prepped with an alcohol swab.")
    assert "alcohol" in found("Site prepped with an alcohol swab; patient drinks alcohol daily.")
    assert "pcp" not in found("Follow up with PCP appointment.")
    assert "pcp" in found("Follow up with PCP appointment; urine positive for phencyclidine.")


def test_empty_and_null_input_are_safe():
    assert found("") == set()
    assert detect_substances("") == []


def test_word_boundaries_are_respected():
    # 'crack' as in cracked lips must not read as crack cocaine
    assert "cocaine" not in found("Patient reports crack lip and dry mouth.")
