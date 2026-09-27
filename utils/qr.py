"""QR code helpers for the backup (GPS-free) check-in flow."""

import base64
import io
import secrets

import qrcode


def generate_qr_secret():
    """A random per-event token embedded in the printed QR code's URL."""
    return secrets.token_urlsafe(16)


def qr_code_data_uri(data, box_size=8, border=2):
    """
    Render `data` (a URL, typically) as a QR code PNG and return it as a
    data: URI, so it can be dropped straight into an <img src="..."> with
    no separate static file to save or serve.
    """
    img = qrcode.make(data, box_size=box_size, border=border)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
