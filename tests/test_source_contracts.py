import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import juridico as j


class SourceContracts(unittest.TestCase):
    def test_unified_boe_search_rejects_unsupported_date_before_network(self):
        reply = {"body": b'{"status":{"code":200},"data":[]}', "url": j.BOE,
                 "consultado_en": "2026-11-15T00:00:00Z", "cache": False}
        with patch.object(j.HTTP, "get", return_value=reply) as get:
            result = j.run_safe(j.juridico_buscar, "BOE", "procedimiento",
                                fecha="2026-01-01")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["codigo"], "PARAMETRO_NO_ADMITIDO")
        get.assert_not_called()

    def test_malformed_json_status_is_a_source_format_error(self):
        for status in (None, [], "200", 200, True):
            with self.subTest(status=status):
                reply = {"body": json.dumps({"status": status}).encode(),
                         "url": j.BOE}
                with self.assertRaises(j.JuridicoError) as caught:
                    j.json_response(reply)
                self.assertEqual(caught.exception.codigo, "FORMATO_INESPERADO")

    def test_valid_json_status_keeps_official_payload(self):
        for code in (200, "200"):
            with self.subTest(code=code):
                data = {"status": {"code": code}, "data": [{"titulo": "Ley"}]}
                self.assertEqual(j.json_response(
                    {"body": json.dumps(data).encode(), "url": j.BOE}), data)

    def test_official_error_status_remains_a_source_error(self):
        with self.assertRaises(j.JuridicoError) as caught:
            j.json_response({"body": b'{"status":{"code":404}}', "url": j.BOE})
        self.assertEqual(caught.exception.codigo, "ERROR_FUENTE")

    def test_dogv_numeric_resolver_without_status_is_preserved(self):
        self.assertEqual(j.json_response({"body": b"327983", "url": j.DOGV}), 327983)


if __name__ == "__main__":
    unittest.main()
