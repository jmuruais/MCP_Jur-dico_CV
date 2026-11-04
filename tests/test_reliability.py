import copy
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import juridico as j


def response(data):
    return {"body": json.dumps(data).encode(), "url": j.DOGV, "cache": False,
            "consultado_en": "2026-11-01T00:00:00Z", "content_type": "application/json"}


class Reliability(unittest.TestCase):
    def test_historical_signature_uses_official_resolver_not_invented_cve(self):
        with patch.object(j.HTTP, "get", side_effect=[response(327983), response({"id":327983,"codigoInsercion":"2018/7822","cve":None,"texto":"Decreto"})]) as get:
            r = j.dogv_publicacion("2018/7822")
        self.assertTrue(r["ok"])
        self.assertIn("/dogv/obtenerIdDogv/2018-7822", get.call_args_list[0].args[0])
        self.assertIsNone(r["datos"]["cve"])

    def test_resolved_signature_and_id_must_match_document(self):
        with patch.object(j.HTTP, "get", side_effect=[response(327983), response({"id":327983,"codigoInsercion":"2018/999","texto":"otra"})]):
            self.assertEqual(j.run_safe(j.dogv_publicacion,"2018/7822")["error"]["codigo"],"REFERENCIA_NO_COINCIDE")
        with patch.object(j.HTTP, "get", return_value=response({"id":123,"texto":"otra"})):
            self.assertEqual(j.run_safe(j.dogv_publicacion,"327983")["error"]["codigo"],"REFERENCIA_NO_COINCIDE")

    def summary(self):
        return {"cabecera": {"numeroDogv": 10483}, "urlPdf": "/2026/10/30/pdf/sumario_2026_10483_es.pdf",
                "disposiciones": [{"id": n, "codigoInsercion": f"2026/{n}"} for n in [1, 3, 2]]}

    def ordered(self, text, data=None, fecha="2026-10-30"):
        with patch.object(j.HTTP, "get", side_effect=[response(data or self.summary()), response({})]), patch.object(j, "extract_pdf", return_value=text):
            return j.run_safe(j.dogv_sumario, fecha=fecha, limite=2, exigir_orden=True)

    def test_pdf_controls_order_before_pagination(self):
        r = self.ordered("10483 / 30.10.2026 DOGV-C-2026-1 DOGV-C-2026-2 DOGV-C-2026-3")
        self.assertTrue(r["ok"])
        self.assertEqual([x["id"] for x in r["datos"]["publicaciones"]], [1, 2])
        self.assertEqual(r["datos"]["siguiente_inicio"], 2)
        self.assertEqual(r["datos"]["verificacion_orden"]["total_verificado"], 3)

    def test_missing_duplicate_and_unknown_cve_fail_closed(self):
        for codes in [[1, 2], [1, 2, 2], [1, 2, 4]]:
            r = self.ordered("10483 / 30.10.2026 " + " ".join(f"DOGV-C-2026-{n}" for n in codes))
            self.assertEqual(r["error"]["codigo"], "ORDEN_NO_VERIFICADO")

    def test_wrong_edition_or_date_fails_closed(self):
        for header in ["10482 / 30.10.2026", "10483 / 29.10.2026"]:
            self.assertEqual(self.ordered(header)["error"]["codigo"], "EDICION_NO_VERIFICADA")

    def test_arbitrary_pdf_url_is_rejected_before_fetch(self):
        d = self.summary(); d["urlPdf"] = "https://example.com/file.pdf"
        with patch.object(j.HTTP, "get", return_value=response(d)) as get:
            self.assertFalse(j.run_safe(j.dogv_sumario, exigir_orden=True)["ok"])
        self.assertEqual(get.call_count, 1)

    def test_database_440_fallback_declares_partial_even_with_zero_hits(self):
        err = j.JuridicoError("HTTP_ERROR", "440", status=440, detalle_fuente="error.bbdd.query")
        d = {"pageNumber": 0, "pageSize": 10, "totalElements": 0, "content": []}
        seen = []
        def post(url, payload):
            seen.append(copy.deepcopy(payload))
            if len(seen) == 1: raise err
            return response(d)
        with patch.object(j.HTTP, "post_query", side_effect=post):
            r = j.dogv_buscar("Decreto 104/2018", desde="2018-01-01")
        self.assertFalse(r["datos"]["recuperacion_completa"])
        self.assertFalse(r["datos"]["filtros_solicitados"]["solo_titulo"])
        self.assertTrue(r["datos"]["filtros"]["solo_titulo"])
        self.assertIn("PARCIAL", r["advertencia"])
        self.assertEqual({k: v for k, v in seen[1].items() if k != "soloTitulo"}, {k: v for k, v in seen[0].items() if k != "soloTitulo"})

    def test_restricted_or_unknown_error_never_triggers_alternative(self):
        for status, detail, title in [(403, None, False), (440, None, False), (440, "error.bbdd.query", True)]:
            with patch.object(j.HTTP, "post_query", side_effect=j.JuridicoError("HTTP_ERROR", "error", status=status, detalle_fuente=detail)) as post:
                self.assertFalse(j.run_safe(j.dogv_buscar, "ejemplo", solo_titulo=title)["ok"])
                self.assertEqual(post.call_count, 1)

    def test_http_440_keeps_only_allowlisted_diagnostic(self):
        http = j.OfficialHTTP()
        err = HTTPError(j.DOGV, 440, "Error", {}, io.BytesIO(json.dumps({"mensajeTecnico": "error.bbdd.query", "secret": "PRIVATE"}).encode()))
        with patch.object(http.opener, "open", side_effect=err):
            r = j.run_safe(http.get, j.DOGV + "/dogv")
        self.assertEqual(r["error"]["detalle_fuente"], "error.bbdd.query")
        self.assertNotIn("PRIVATE", json.dumps(r))

    def test_roj_and_ecli_are_distinct_from_text_and_checked(self):
        item = {"roj": "ATS 11323/2025", "ecli": "ECLI:ES:TS:2025:11323A", "url_oficial": "https://www.poderjudicial.es/search/AN/openDocument/0123456789abcdef/20251203"}
        with patch.object(j.HTTP, "public_cendoj_session"), patch.object(j.HTTP, "post_query", return_value=response({})) as post, patch.object(j, "cendoj_results", return_value=(1, [item])):
            r = j.ts_buscar(roj="ATS 11323/2025", ecli="ES:TS:2025:11323A")
            self.assertTrue(r["ok"])
            self.assertNotIn("TEXT", post.call_args.args[1])
            self.assertEqual(post.call_args.args[1]["ROJ"], item["roj"])
            self.assertEqual(post.call_args.args[1]["ECLI"], item["ecli"])
            for kw in [{"roj": "ATS 1/2025"}, {"ecli": "ES:TS:2025:1A"}]:
                self.assertEqual(j.run_safe(j.ts_buscar, **kw)["error"]["codigo"], "REFERENCIA_NO_COINCIDE")


if __name__ == "__main__":
    unittest.main()
