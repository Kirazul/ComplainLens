from datetime import UTC, datetime

import polars as pl

from complaintlens.data.twcs import (
    _with_roots,
    build_first_contacts,
    mask_text,
    strip_agent_signature,
)


def test_mask_text_replaces_brand_users_and_urls():
    text = "@Uber_Support my UberX driver @115712 was rude https://t.co/abc see uber.com"
    assert mask_text(text, brand="Uber_Support") == (
        "[COMPANY] my [COMPANY]X driver [USER] was rude [URL] see [COMPANY].com"
    )


def test_mask_text_keeps_emojis_case_and_accents():
    assert mask_text("Très déçu 😡 NOT happy", brand="Uber_Support") == "Très déçu 😡 NOT happy"


def test_strip_agent_signature():
    assert strip_agent_signature("Sorry to hear that. Please DM us. ^CC") == (
        "Sorry to hear that. Please DM us."
    )
    assert strip_agent_signature("We can help -JR") == "We can help"
    assert strip_agent_signature("No signature here") == "No signature here"
    assert strip_agent_signature("Glad to help " + chr(0x2013) + "MK") == "Glad to help"


def _tweets() -> pl.DataFrame:
    # Conversation A: customer 1 writes two tweets, Uber replies, customer replies again.
    # Conversation B: customer 2 addresses Uber, never gets a reply.
    # Conversation C: a conversation with another brand (must be ignored).
    rows = [
        (
            1,
            "111",
            True,
            "Tue Oct 31 10:00:00 +0000 2017",
            "@Uber_Support charged twice!",
            "3",
            None,
        ),
        (
            2,
            "111",
            True,
            "Tue Oct 31 10:01:00 +0000 2017",
            "@Uber_Support for one ride",
            None,
            None,
        ),
        (
            3,
            "Uber_Support",
            False,
            "Tue Oct 31 10:05:00 +0000 2017",
            "@111 Sorry! DM us your email. ^AB",
            "4",
            1,
        ),
        (4, "111", True, "Tue Oct 31 10:06:00 +0000 2017", "@Uber_Support done", None, 3),
        (
            5,
            "222",
            True,
            "Wed Nov 01 09:00:00 +0000 2017",
            "@Uber_Support app keeps crashing",
            None,
            None,
        ),
        (6, "333", True, "Wed Nov 01 09:00:00 +0000 2017", "@AppleSupport battery", "7", None),
        (7, "AppleSupport", False, "Wed Nov 01 09:02:00 +0000 2017", "@333 Let's help", None, 6),
    ]
    df = pl.DataFrame(
        rows,
        schema=[
            "tweet_id",
            "author_id",
            "inbound",
            "created_at",
            "text",
            "response_tweet_id",
            "in_response_to_tweet_id",
        ],
        orient="row",
    )
    # Tweet 2 is a self-continuation of tweet 1 (the customer threads their own tweets).
    return df.with_columns(
        pl.when(pl.col("tweet_id") == 2)
        .then(1)
        .otherwise(pl.col("in_response_to_tweet_id"))
        .alias("in_response_to_tweet_id")
    )


def test_roots_resolve_very_deep_threads():
    # Real TWCS has reply chains more than 300 tweets deep; a 1,000-tweet chain must resolve.
    n = 1000
    df = pl.DataFrame(
        {
            "tweet_id": list(range(1, n + 1)),
            "in_response_to_tweet_id": [None, *range(1, n)],
        },
        schema={"tweet_id": pl.Int64, "in_response_to_tweet_id": pl.Int64},
    )
    roots = _with_roots(df)
    assert roots["root"].unique().to_list() == [1]


def test_roots_stop_at_missing_parent():
    # Tweet 2 answers tweet 99, which is absent from the data: tweet 2 becomes its own root.
    df = pl.DataFrame(
        {"tweet_id": [2, 3], "in_response_to_tweet_id": [99, 2]},
        schema={"tweet_id": pl.Int64, "in_response_to_tweet_id": pl.Int64},
    )
    assert _with_roots(df).sort("tweet_id")["root"].to_list() == [2, 2]


def test_build_first_contacts_merges_customer_tweets_before_first_reply():
    out = build_first_contacts(_tweets(), brand="Uber_Support").sort("conversation_id")
    assert out["conversation_id"].to_list() == [1, 5]

    a = out.row(0, named=True)
    assert a["customer_id"] == "111"
    assert a["text"] == "[COMPANY] charged twice!\n[COMPANY] for one ride"
    assert a["n_customer_tweets"] == 2
    assert a["brand_replied"] is True
    assert a["first_reply"] == "[USER] Sorry! DM us your email."
    assert a["reply_delay_s"] == 300
    assert a["created_at"] == datetime(2017, 10, 31, 10, 0, tzinfo=UTC)

    b = out.row(1, named=True)
    assert b["brand_replied"] is False
    assert b["first_reply"] is None
    assert b["reply_delay_s"] is None


def test_food_delivery_conversations_are_out_of_scope():
    import re

    from complaintlens.data.twcs import FOOD_DELIVERY

    food = re.compile(FOOD_DELIVERY.removeprefix("(?i)"), re.IGNORECASE)
    for text in (
        "my [COMPANY] eats order is an hour late",
        "#[COMPANY]EATS terrible service",
        "the courier never delivered my food",
    ):
        assert food.search(text), text
    for text in (
        "My driver took a detour and I was charged $12 more",
        "I left my phone in the car, the driver ordered me out",  # "order" alone is not food
        "Charged twice for one ride",
    ):
        assert not food.search(text), text
