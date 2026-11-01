import io
import json
import sys
import unittest
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import juridico as j


def response(body, content_type="application/json"):
    return {"body": body if isinstance(body, bytes) else json.dumps(body).encode(),
        "content_type": content_type, "url": j.BOE+"/id/BOE-A-2015-10565/metadatos",
        "consultado_en": "2026-10-26T00:00:00+00:00", "cache": False}


class Validations(unittest.TestCase):
    def test_ssrf_urls(self):
        for u in ("http://www.boe.es/", "https://127.0.0.1/", "https://www.boe.es@127.0.0.1/",
                  "https://www.poderjudicial.es.evil.test/search/indexAN.jsp",
                  "https://www.poderjudicial.es:443/search/indexAN.jsp",
                  "https://www.poderjudicial.es/search/../secret", "file:///etc/passwd",
                  "https://dogv.gva.es/dogv-portal/auth/signin",
                  "https://www.poderjudicial.es/search/contenidos.action?action=other&reference=ab"):
            with self.subTest(u=u), self.assertRaises(j.JuridicoError):
                j.check_url(u)

    def test_dates(self):
        for value in ("2026-02-30", "2026-13-01", "2026/10/01", "", "2026101", "  "):
            with self.subTest(value=value), self.assertRaises(j.JuridicoError):
                j.valid_date(value)
        self.assertEqual(j.valid_date("20261026"), "2026-10-26")

    def test_invalid_input_never_connects(self):
        cases = [(j.boe_bloque, ("BOE-A-2015-10565", "../secreto")),
                 (j.boe_metadatos, ("http://localhost",)),
                 (j.dogv_sumario, ("2026-02-30",)),
                 (j.ts_resolucion, ("https://127.0.0.1/secret",)),
                 (j.boe_buscar, ("",)), (j.dogv_publicacion, ("../etc/passwd",))]
        with patch.object(j.HTTP, "get") as get:
            for fn, args in cases:
                self.assertFalse(j.run_safe(fn, *args)["ok"])
            get.assert_not_called()

    def test_xml_entities_rejected(self):
        r = response(b'<!DOCTYPE response [<!ENTITY x "evil">]><response/>')
        with self.assertRaises(j.JuridicoError):
            j.xml_response(r)

    def test_html_instead_of_json(self):
        with self.assertRaises(j.JuridicoError):
            j.json_response(response(b"<html>CAPTCHA</html>"))

    def test_errors_are_structured_and_redacted(self):
        def fail():
            raise RuntimeError("SECRET_PRIVATE_TOKEN")
        with self.assertLogs(j.LOG, level="ERROR") as logs:
            r = j.run_safe(fail)
        self.assertFalse(r["ok"])
        self.assertNotIn("SECRET_PRIVATE_TOKEN", json.dumps(r)+str(logs.output))

    def test_limits_and_fragment_pagination(self):
        for bad in (-1, True, 30001):
            with self.assertRaises(j.JuridicoError):
                j.page_text("a"*2000, 0, bad)
        a = j.page_text("a"*1500, 0, 1000)
        b = j.page_text("a"*1500, a["siguiente_inicio"], 1000)
        self.assertEqual(a["texto"]+b["texto"], "a"*1500)
        self.assertIsNone(b["siguiente_inicio"])


class Semantics(unittest.TestCase):
    def test_historical_version_never_returns_future(self):
        xml = b'''<response><status><code>200</code></status><data><bloque id="a1" titulo="Articulo 1"><version fecha_publicacion="20150101" fecha_vigencia="20160101"><p>Antigua</p></version><version fecha_publicacion="20200101" fecha_vigencia="20210101"><p>Nueva</p></version></bloque></data></response>'''
        with patch.object(j.HTTP, "get", return_value=response(xml)) as get:
            old = j.boe_bloque("BOE-A-2015-10565", "a1", "2017-01-01")
            self.assertIn("Antigua", old["datos"]["texto"])
            self.assertNotIn("Nueva", old["datos"]["texto"])
            self.assertEqual(get.call_args.args[1], "application/xml")
            early = j.run_safe(j.boe_bloque, "BOE-A-2015-10565", "a1", "2014-12-31")
            self.assertEqual(early["error"]["codigo"], "SIN_VERSION_EN_FECHA")
        self.assertEqual(len(old["datos"]["versiones"]), 2)

    def test_vigencia_does_not_infer_a_legal_conclusion(self):
        data = {"data": [{"estatus_derogacion": "N", "vigencia_agotada": "N"}]}
        with patch.object(j.HTTP, "get", return_value=response(data)):
            r = j.boe_vigencia("BOE-A-2015-10565")
        self.assertIsNone(r["datos"]["conclusion_automatica"])

    def test_dogv_search_scope_and_pagination(self):
        data = {"cabecera": {"numeroDogv": 123}, "disposiciones": [
            {"id": n, "titulo": "Ayudas universidad", "codigoInsercion": f"2026/{n}"} for n in range(3)]}
        with patch.object(j.HTTP, "get", return_value=response(data)):
            r = j.dogv_buscar("universidad", limite=2, modo="sumario")
        self.assertEqual(r["datos"]["modo"], "filtro_local_del_sumario")
        self.assertEqual(len(r["datos"]["publicaciones"]), 2)
        self.assertEqual(r["datos"]["siguiente_inicio"], 2)

    def test_no_document_collection_for_cendoj(self):
        src = b'<a data-roj="STS 1/2026" href="/search/AN/openDocument/aaaaaaaaaaaaaaaa/20261026">Resolucion</a><a data-roj="SAN 3/2026" href="/search/AN/openDocument/bbbbbbbbbbbbbbbb/20261026">Otra</a>'
        with patch.object(j.HTTP, "get", return_value=response(src)) as get:
            r = j.ts_buscar()
        self.assertEqual(len(r["datos"]["resoluciones"]), 1)
        self.assertEqual(r["datos"]["modo"], "resoluciones_recientes_portada")
        self.assertFalse(get.call_args.kwargs["cache"])

    def test_ignore_active_html(self):
        self.assertEqual(j.plain_html('<p>Texto <em>legal</em></p><script>instruccion</script>'), 'Texto legal')

    def test_dogv_desindexar_is_respected(self):
        with patch.object(j.HTTP, "get", return_value=response({"id": 123, "desindexar": True, "texto": "protegido"})):
            r = j.run_safe(j.dogv_publicacion, "123")
        self.assertEqual(r["error"]["codigo"], "DOCUMENTO_DESINDEXADO")


class TransportLimits(unittest.TestCase):
    def test_access_denied_is_not_retried(self):
        http = j.OfficialHTTP()
        error = HTTPError(j.BOE, 403, "Forbidden", {}, io.BytesIO(b"private"))
        with patch.object(http.opener, "open", side_effect=error) as request:
            with self.assertRaises(j.JuridicoError) as caught:
                http.get(j.BOE)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(caught.exception.codigo, "ACCESO_INTERACTIVO_REQUERIDO")

    def test_long_retry_after_is_honoured_by_stopping(self):
        http = j.OfficialHTTP()
        error = HTTPError(j.BOE, 429, "Rate limited", {"Retry-After": "120"}, io.BytesIO())
        with patch.object(http.opener, "open", side_effect=error) as request, patch.object(j.time, "sleep") as sleep:
            with self.assertRaises(j.JuridicoError) as caught:
                http.get(j.BOE)
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()
        self.assertTrue(caught.exception.reintentable)

    def test_streaming_response_is_bounded_without_content_length(self):
        class Endless:
            url, headers = j.BOE, {"Content-Type": "application/json"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b"a"*size
        http = j.OfficialHTTP()
        with patch.object(http.opener, "open", return_value=Endless()):
            with self.assertRaises(j.JuridicoError) as caught:
                http.get(j.BOE)
        self.assertEqual(caught.exception.codigo, "RESPUESTA_DEMASIADO_GRANDE")
        self.assertEqual(http.cache_bytes, 0)

    def test_cache_does_not_hold_cendoj_documents(self):
        class Reply:
            url, headers = j.CENDOJ+"indexAN.jsp", {"Content-Type": "text/html"}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size):
                if getattr(self, "done", False): return b""
                self.done = True
                return b"CENDOJ"
        http = j.OfficialHTTP()
        with patch.object(http.opener, "open", return_value=Reply()):
            http.get(j.CENDOJ+"indexAN.jsp")
        self.assertEqual(http.cache_bytes, 0)

    def test_two_slots_limit_parallel_work(self):
        http = j.OfficialHTTP()
        http.slots.acquire()
        http.slots.acquire()
        with patch.object(http.opener, "open") as request:
            with self.assertRaises(j.JuridicoError) as caught:
                http.get(j.BOE)
        self.assertEqual(caught.exception.codigo, "OCUPADO")
        request.assert_not_called()


SAMPLE_TS = '''<aside><b>2 resultados</b><div id="jurisprudenciaresults_searchresults">
<div class="row searchresult doc" id="jurisprudenciaresults_content-123" data-db="TS">
<a href="https://www.poderjudicial.es/search/AN/openDocument/aaaaaaaaaaaaaaaa/20261026" data-roj="STS 123/2026">STS 123/2026</a>
<div class="metadatos"><ul><li><b>ECLI:ES:TS:2026:123</b></li><li>Sala de lo Social</li></ul></div>
<div class="summary">Resumen de la fuente.</div></div>
<div class="row searchresult doc" id="jurisprudenciaresults_content-124" data-db="TS">
<a href="https://www.poderjudicial.es/search/AN/openDocument/bbbbbbbbbbbbbbbb/20261026" data-roj="AATS 124/2026">AATS 124/2026</a>
<div class="metadatos"><ul><li><b>ECLI:ES:TS:2026:124A</b></li></ul></div>
<div class="summary">Otro resumen.</div></div></div></aside>'''


class GeneralSearch(unittest.TestCase):
    def test_dogv_global_contract_and_page_boundary(self):
        data = {"pageNumber": 1, "pageSize": 10, "totalElements": 100,
                "content": [{"id": n, "titulo": "Ejemplo", "codigoInsercion": f"2026/{n}"} for n in range(10,20)]}
        with patch.object(j.HTTP, "post_query", return_value=response(data)) as post:
            r = j.dogv_buscar("procedimiento", inicio=17, limite=10, desde="2020-01-01", hasta="2026-10-26")
        self.assertEqual(r["datos"]["modo"], "busqueda_global")
        self.assertEqual(len(r["datos"]["publicaciones"]), 3)
        self.assertEqual(r["datos"]["siguiente_inicio"], 20)
        self.assertIn("lang=es_es", post.call_args.args[0])
        self.assertIn("sort=fechaDogvDesc", post.call_args.args[0])
        self.assertIn("size=10", post.call_args.args[0])
        self.assertFalse(post.call_args.args[1]["soloTitulo"])
        self.assertEqual(post.call_args.args[1]["fechaInicioPublicacion"], "01-01-2020")

    def test_dogv_bad_pagination_is_not_silently_accepted(self):
        data = {"pageNumber": 999, "pageSize": 10, "totalElements": 1, "content": []}
        with patch.object(j.HTTP, "post_query", return_value=response(data)):
            r = j.run_safe(j.dogv_buscar, "ejemplo")
        self.assertEqual(r["error"]["codigo"], "PAGINACION_NO_VERIFICADA")

    def test_incompatible_dates_do_not_connect(self):
        with patch.object(j.HTTP, "post_query") as post:
            for kw in [{"fecha":"2026-01-01","desde":"2025-01-01"}, {"desde":"2026-01-01","hasta":"2025-01-01"}]:
                self.assertFalse(j.run_safe(j.dogv_buscar, "ejemplo", **kw)["ok"])
            post.assert_not_called()

    def test_parse_general_cendoj_results(self):
        total, items = j.cendoj_results(SAMPLE_TS)
        self.assertEqual(total, 2)
        self.assertEqual([x["ecli"] for x in items], ["ECLI:ES:TS:2026:123", "ECLI:ES:TS:2026:124A"])
        self.assertEqual(items[0]["resumen_fuente"], "Resumen de la fuente.")

    def test_cendoj_rejects_wrong_court_and_unknown_html(self):
        for src in [SAMPLE_TS.replace('data-db="TS"','data-db="TSJ"',1), "<html>Temporalmente no disponible</html>"]:
            with self.assertRaises(j.JuridicoError):
                j.cendoj_results(src)
        self.assertEqual(j.cendoj_results('<b>0 resultados</b>'), (0, []))
        self.assertEqual(j.cendoj_results('<aside><div id="jurisprudenciaresults_filters"><li data-totalhits="0"></li></div>No se ha encontrado ningún resultado.</aside>'), (0, []))

    def test_cendoj_general_filters_and_next_position(self):
        with patch.object(j.HTTP, "public_cendoj_session") as session, patch.object(j.HTTP, "post_query", return_value=response(SAMPLE_TS.encode())) as post:
            r = j.ts_buscar("despido", limite=1, sala="social", desde="2026-01-01", ecli="ES:TS:2026:123")
        session.assert_called_once()
        params = post.call_args.args[1]
        self.assertEqual(params["action"], "query")
        self.assertEqual(params["TIPOORGANOPUB"], "|14|")
        self.assertEqual(params["FECHARESOLUCIONDESDE"], "01/01/2026")
        self.assertEqual(params["ECLI"], "ECLI:ES:TS:2026:123")
        self.assertEqual(r["datos"]["siguiente_inicio"], 1)
        self.assertEqual(len(r["datos"]["resoluciones"]), 1)

    def test_cendoj_constraints_before_network(self):
        with patch.object(j.HTTP, "post_query") as post:
            for kw in [{"inicio":200}, {"ecli":"ECLI:ES:TSJ:2026:1"}, {"sala":"inventada"}, {"roj":"SAN 1/2026"}]:
                self.assertFalse(j.run_safe(j.ts_buscar,"prueba",**kw)["ok"])
            post.assert_not_called()

    def test_cendoj_final_page_never_exceeds_200(self):
        with patch.object(j.HTTP,"public_cendoj_session"), patch.object(j.HTTP,"post_query",return_value=response(SAMPLE_TS.replace('2 resultados','1000 resultados').encode())) as post:
            r=j.ts_buscar('prueba',inicio=199,limite=10)
        self.assertEqual(post.call_args.args[1]['recordsPerPage'],'1')
        self.assertEqual(len(r['datos']['resoluciones']),1)
        self.assertIsNone(r['datos']['siguiente_inicio'])

    def test_post_cannot_mutate_accounts(self):
        http=j.OfficialHTTP()
        with patch.object(http.opener,"open") as op:
            with self.assertRaises(j.JuridicoError):
                http.post_query(j.CENDOJ+"search.action",{"action":"delete"},form=True)
            with self.assertRaises(j.JuridicoError):
                http.post_query(j.BOE,{"texto":"prueba"})
            op.assert_not_called()

    def test_440_is_a_source_error_not_an_access_diagnosis(self):
        http=j.OfficialHTTP()
        err=HTTPError(j.BOE,440,"Error",{},io.BytesIO())
        with patch.object(http.opener,"open",side_effect=err):
            with self.assertRaises(j.JuridicoError) as e:
                http.get(j.BOE)
        self.assertEqual(e.exception.codigo,"HTTP_ERROR")

    def test_post_cache_separates_different_searches(self):
        class Reply(io.BytesIO):
            url=j.DOGV+"/dogv/search"
            headers={"Content-Type":"application/json"}
        http=j.OfficialHTTP()
        def reply(req,timeout):return Reply(req.data)
        with patch.object(http.opener,"open",side_effect=reply) as op, patch.object(j.time,"sleep"):
            a=http.post_query(j.DOGV+"/dogv/search",{"texto":"uno"})
            b=http.post_query(j.DOGV+"/dogv/search",{"texto":"dos"})
            c=http.post_query(j.DOGV+"/dogv/search",{"texto":"uno"})
        self.assertEqual(op.call_count,2)
        self.assertNotEqual(a["body"],b["body"])
        self.assertTrue(c["cache"])


if __name__ == "__main__":
    unittest.main()
