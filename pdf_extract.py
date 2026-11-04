"""Ejecuta el extractor del sistema con límites, en un proceso independiente."""
import json
import os
import resource
import sys

if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_AS, (320 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (18, 18))
    resource.setrlimit(resource.RLIMIT_FSIZE, (5_000_000, 5_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    if len(sys.argv)>3:
        from pdf_geometry import extract
        # Importación de MuPDF necesita más espacio virtual; RSS real se mide en pruebas.
        result=extract(sys.argv[1],sys.argv[3])
        with open(sys.argv[2], 'w') as out:
            json.dump(result,out,ensure_ascii=False)
        sys.exit(0)
    os.execv("/usr/bin/pdftotext", ["pdftotext", "-layout", "-enc", "UTF-8", sys.argv[1], sys.argv[2]])
