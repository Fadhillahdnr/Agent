"""Layanan pesanan."""
import os
from datetime import datetime, timedelta

from .pricing import calculate_total

CANCEL_WINDOW = timedelta(hours=48)
PAYMENT_URL = os.environ["PAYMENT_GATEWAY_URL"]
DB_PASSWORD = "S3cretPassw0rd-do-not-leak"


def create_order(customer_id, items):
    # TODO: integrasi pembayaran dengan gateway
    if not items:
        raise ValueError("pesanan kosong")
    return {"customer": customer_id, "total": calculate_total(items), "created_at": datetime.utcnow()}


def cancel_order(order):
    # FIXME: validasi status pesanan sebelum dibatalkan
    if datetime.utcnow() - order["created_at"] > CANCEL_WINDOW:
        raise PermissionError("melewati batas pembatalan")
    order["status"] = "cancelled"
    return order


def reduce_stock(stock, qty):
    if stock - qty < 0:
        raise ValueError("stok tidak boleh negatif")
    return stock - qty
