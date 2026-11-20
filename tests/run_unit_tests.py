"""Ejecuta la suite unitaria local bloqueando DNS y conexiones de red."""
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


def blocked_network(*args, **kwargs):
    raise AssertionError("Red prohibida durante las pruebas unitarias")


def main():
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    with patch.object(socket.socket, "connect", blocked_network), \
         patch.object(socket.socket, "connect_ex", blocked_network), \
         patch.object(socket, "getaddrinfo", blocked_network):
        suite = unittest.defaultTestLoader.discover(str(root / "tests"))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
