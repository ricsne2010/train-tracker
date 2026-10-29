"""Network helpers: secure connections that work on any Python install, and this computer's network address."""
import socket
import ssl

import certifi


def ssl_context():
    """Certificates from certifi: python.org's Python for macOS has none until you run its "Install Certificates"
    step, which would make every feed fail."""
    return ssl.create_default_context(cafile=certifi.where())


def lan_address():
    """This computer's address on the local network (what a phone on the same Wi-Fi uses), or None."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))    # picks the outgoing interface; nothing is sent
            return s.getsockname()[0]
    except OSError:
        return None
