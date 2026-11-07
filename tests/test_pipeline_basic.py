from complaintlens.pipeline.base import run_stages
from complaintlens.pipeline.language import detect_language
from complaintlens.pipeline.normalize import clean_email_body, html_to_text
from complaintlens.pipeline.pii import mask_pii
from complaintlens.schemas import StageResult

# --- stage runner -----------------------------------------------------------


def test_run_stages_times_stages_and_survives_crashes():
    def ok(ctx):
        ctx["x"] = 1
        return StageResult(name="ok", output={"x": 1})

    def boom(ctx):
        raise ValueError("bad input")

    seen = []
    trace = run_stages([ok, boom], {}, on_stage=seen.append)
    assert [r.name for r in trace] == ["ok", "boom"]
    assert trace[1].status == "error" and "bad input" in trace[1].note
    assert all(r.ms >= 0 for r in trace)
    assert seen == trace


# --- email cleaning ---------------------------------------------------------


def test_clean_email_removes_english_quote_and_signature():
    body = (
        "I was charged twice for my ride last night.\n"
        "Please fix this.\n\n"
        "--\nJohn Smith\n555-0100\n\n"
        "On Mon, Nov 6, 2026 at 9:14 PM LunaGo Support <support@lunago.me> wrote:\n"
        "> Thanks for contacting us.\n"
    )
    assert clean_email_body(body) == "I was charged twice for my ride last night.\nPlease fix this."


def test_clean_email_removes_french_quote_and_mobile_signature():
    body = (
        "J'ai été facturé deux fois !\n\nEnvoyé de mon iPhone\n\n"
        "Le lun. 6 nov. 2026 à 21:14, LunaGo <support@lunago.me> a écrit :\n> Bonjour"
    )
    assert clean_email_body(body) == "J'ai été facturé deux fois !"


def test_clean_email_removes_outlook_original_message_block():
    body = "Still waiting for my refund.\n\n-----Original Message-----\nFrom: LunaGo\nSent: Monday"
    assert clean_email_body(body) == "Still waiting for my refund."


def test_html_to_text_keeps_line_breaks_and_entities():
    assert html_to_text("<p>Hello&nbsp;there</p><p>Line&amp;2<br>end</p>") == (
        "Hello there\nLine&2\nend"
    )


# --- PII masking ------------------------------------------------------------


def test_mask_pii_masks_email_phone_card_but_not_amounts_or_trip_ids():
    text = (
        "Call me at (514) 555-0199 or +33 6 12 34 56 78, email jo.doe@mail.com. "
        "Card 4111 1111 1111 1111 was charged $18.40 twice for trip LG-48213."
    )
    masked, found = mask_pii(text)
    assert masked == (
        "Call me at [PHONE_1] or [PHONE_2], email [EMAIL_1]. "
        "Card [CARD_1] was charged $18.40 twice for trip LG-48213."
    )
    assert [f["type"] for f in found] == ["EMAIL", "CARD", "PHONE", "PHONE"]


def test_mask_pii_ignores_digit_runs_that_fail_luhn():
    masked, found = mask_pii("Order 1234 5678 9012 3456 arrived cold")
    assert masked == "Order 1234 5678 9012 3456 arrived cold"
    assert found == []


# --- language ---------------------------------------------------------------


def test_detect_language_english_and_french():
    assert detect_language("My driver cancelled three times and I missed my flight")[0] == "en"
    assert detect_language("Mon chauffeur a annulé trois fois et j'ai raté mon vol")[0] == "fr"


def test_detect_language_other_for_long_foreign_text():
    lang, _ = detect_language(
        "Mi conductor canceló tres veces y perdí mi vuelo, quiero un reembolso completo ahora"
    )
    assert lang == "other"


def test_detect_language_short_text_falls_back_to_en_or_fr():
    assert detect_language("merci!")[0] in {"en", "fr"}
