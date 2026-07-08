from __future__ import annotations

import ssl


def _patch_default_ssl_certs() -> None:
    try:
        ssl.create_default_context()
        return
    except ssl.SSLError:
        pass

    try:
        import certifi
    except ImportError:
        return

    cafile = certifi.where()

    def load_default_certs(self: ssl.SSLContext, purpose: ssl.Purpose = ssl.Purpose.SERVER_AUTH) -> None:
        self.load_verify_locations(cafile=cafile)

    ssl.SSLContext.load_default_certs = load_default_certs  # type: ignore[method-assign]


_patch_default_ssl_certs()
