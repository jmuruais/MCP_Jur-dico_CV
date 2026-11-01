"""Ejecuta el extractor del sistema con límites, en un proceso independiente."""
import os
import resource
import sys

if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_AS, (192 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    os.execv("/usr/bin/pdftotext", ["pdftotext", "-layout", "-enc", "UTF-8", sys.argv[1], sys.argv[2]])
