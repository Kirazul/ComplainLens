import random

from complaintlens.rootcause import benjamini_hochberg, most_frequent_values, probable_causes

FIELDS = ["os", "app_version", "zone"]


def traffic(n, rng, cause=None):
    rows = []
    for _ in range(n):
        r = {
            "os": rng.choices(["ios", "android"], [0.7, 0.3])[0],
            "app_version": rng.choice(["5.0", "5.1", "5.2"]),
            "zone": rng.choice(["plateau", "verdun", "old_port", "mile_end"]),
        }
        if cause:
            r.update(cause)
        rows.append(r)
    return rows


def test_benjamini_hochberg_matches_hand_computation():
    assert benjamini_hochberg([0.01, 0.04, 0.03]) == [0.03, 0.04, 0.04]


def test_planted_cause_is_ranked_first_while_common_values_are_not():
    rng = random.Random(0)
    baseline = traffic(3000, rng)
    incident = traffic(40, rng, cause={"os": "android", "app_version": "5.2"}) + traffic(20, rng)
    causes = probable_causes(incident, baseline, FIELDS)
    top = {(c.field, c.value) for c in causes[:2]}
    assert top == {("os", "android"), ("app_version", "5.2")}
    assert all(c.q_value <= 0.05 for c in causes)
    # The naive baseline puts the common value first if it dominates traffic.
    naive = most_frequent_values(traffic(60, rng), FIELDS)
    assert naive[0] == ("os", "ios")


def test_no_cause_in_normal_traffic():
    rng = random.Random(1)
    assert probable_causes(traffic(60, rng), traffic(3000, rng), FIELDS) == []
