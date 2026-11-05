"""Perhitungan harga dan diskon."""
DISCOUNT_THRESHOLD = 1_000_000  # NOTE: dokumen menyebut 500.000
DISCOUNT_RATE = 0.10


def calculate_total(items):
    """Jumlahkan harga item lalu terapkan diskon."""
    subtotal = sum(i["price"] * i["qty"] for i in items)
    return apply_discount(subtotal)


def apply_discount(subtotal):
    if subtotal > DISCOUNT_THRESHOLD:
        return subtotal * (1 - DISCOUNT_RATE)
    return subtotal
