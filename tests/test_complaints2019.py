from pathlib import Path

import pytest

from complaintlens.data.complaints2019 import load_aligned, text_key

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "complaints2019"


def test_text_key_matches_both_releases():
    original = "@FC_HELP can I return online purchases?? &gt; https://t.co/x"
    lowered = "<user> can i return online purchases ? ? > <url>"
    assert text_key(original) == text_key(lowered) == "canireturnonlinepurchases"


@pytest.mark.skipif(
    not (RAW / "complaint_severity_data.csv").exists(), reason="data not downloaded"
)
def test_alignment_on_real_files_is_complete_and_consistent():
    df = load_aligned(RAW / "complaints-data.csv", RAW / "complaint_severity_data.csv")
    assert len(df) == 3449
    assert df["severity"].null_count() == 0, "every tweet must receive a severity label"
    assert df["align_similarity"].min() >= 0.8
    # Exactly one row of the severity release is a spreadsheet error ("#NAME?"): unverifiable.
    assert df["align_similarity"].null_count() == 1
    # Severity 0 exactly when the tweet is not a complaint.
    assert ((df["severity"] == 0) == (df["is_complaint"] == 0)).all()
    assert df["severity"].value_counts().sort("severity")["count"].to_list() == [
        2217,
        436,
        376,
        224,
        196,
    ]
