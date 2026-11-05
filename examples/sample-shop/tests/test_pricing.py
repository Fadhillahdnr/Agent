from src.pricing import apply_discount


def test_discount_applied_above_threshold():
    assert apply_discount(2_000_000) == 1_800_000


def test_no_discount_below_threshold():
    assert apply_discount(100_000) == 100_000
