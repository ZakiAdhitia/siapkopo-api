"""QR code generation for letter verification codes."""
import base64
import io

import qrcode


def generate_qr_data_uri(data: str) -> str:
    """Render `data` as a QR PNG and return it as a data: URI.

    A data: URI (not a file path or external URL) so it can be embedded
    directly in TemplateRenderService's rendered HTML without touching the
    xhtml2pdf link_callback hardening — that callback already treats
    data: URIs as safe/inert (see app/services/template_render.py).
    """
    img = qrcode.make(data)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
