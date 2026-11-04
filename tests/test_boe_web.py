import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import juridico as j

FIXTURE=Path(__file__).with_name('fixtures')/'boe-web-title.html'

def response(body):
    return {'body':body.encode() if isinstance(body,str) else body,'url':'https://www.boe.es/buscar/legislacion.php','consultado_en':'2026-11-03T00:00:00Z','cache':False,'content_type':'text/html'}

class BoeWeb(unittest.TestCase):
    def test_real_title_page_has_twenty_unique_matching_references(self):
        total,items=j.boe_search_page(FIXTURE.read_bytes())
        self.assertEqual((total,len(items)),(20,20))
        self.assertEqual(len({x['identificador'] for x in items}),20)
        law=next(x for x in items if x['identificador']=='BOE-A-2015-10565')
        self.assertTrue(law['recuperable_api'])
        self.assertIn('Ley 39/2015',law['titulo'])
        self.assertIn('02/10/2015',law['metadatos_publicacion'])

    def test_changed_or_malformed_page_never_means_zero(self):
        for s in ['<html>Servicio temporalmente no disponible</html>', '<html>CAPTCHA</html>', FIXTURE.read_text().replace('Resultados 1 a 20 de 20','Resultados 51 a 70 de 70'),FIXTURE.read_text().replace('de 20','de 21',1)]:
            with self.assertRaises(j.JuridicoError):j.boe_search_page(s.encode())

    def test_confirmed_empty_page(self):
        self.assertEqual(j.boe_search_page('No se han encontrado documentos que satisfagan sus criterios de búsqueda'.encode()),(0,[]))

    def test_duplicate_mismatched_and_missing_consolidated_links_rejected(self):
        s=FIXTURE.read_text()
        cases=[s.replace('BOE-A-2015-10565','BOE-A-2018-12131'),s.replace('../buscar/act.php?id=BOE-A-2015-10565','../buscar/act.php?id=BOE-A-1992-26318'),s.replace('../buscar/act.php?id=BOE-A-2015-10565','https://evil.example/act.php?id=BOE-A-2015-10565')]
        for c in cases:
            with self.assertRaises(j.JuridicoError):j.boe_search_page(c.encode())

    def test_non_boe_reference_is_preserved_and_not_claimed_api_compatible(self):
        s=FIXTURE.read_text().replace('BOE-A-2015-10565','DOGC-f-2017-90436')
        _,items=j.boe_search_page(s.encode())
        item=next(x for x in items if x['identificador']=='DOGC-f-2017-90436')
        self.assertFalse(item['recuperable_api'])

    def test_fallback_500_marks_different_scope_and_pins_pagination(self):
        with patch.object(j.HTTP,'get',side_effect=[j.JuridicoError('HTTP_ERROR','500',status=500),response(FIXTURE.read_bytes())]) as get:
            r=j.boe_buscar('procedimiento administrativo',limite=1,inicio=1,solo_titulo=True)
        self.assertEqual(get.call_count,2)
        self.assertFalse(r['datos']['recuperacion_completa'])
        self.assertEqual(r['datos']['error_consulta_original']['http_status'],500)
        self.assertEqual(r['datos']['data'][0]['identificador'],'BOE-A-2015-10565')
        self.assertEqual(r['paginacion']['siguiente_inicio'],2)
        self.assertEqual(r['paginacion']['continuacion']['modo'],'web')
        self.assertIn('checkbox_solo_tit=S',get.call_args.args[0])

    def test_dates_restrictions_and_explicit_api_never_fallback(self):
        for status,kw in [(403,{}),(429,{}),(503,{}),(500,{'desde':'2026-01-01'}),(500,{'modo':'api'})]:
            with patch.object(j.HTTP,'get',side_effect=j.JuridicoError('HTTP_ERROR','error',status=status)) as get:
                self.assertFalse(j.run_safe(j.boe_buscar,'ejemplo',**kw)['ok'])
                self.assertEqual(get.call_count,1)

    def test_api_success_never_calls_web_and_literal_title_filter(self):
        data={'status':{'code':'200'},'data':[{'identificador':'BOE-A-2015-10565'}]}
        with patch.object(j.HTTP,'get',return_value=response(json.dumps(data))) as get:
            r=j.boe_buscar('ley',solo_titulo=True)
        self.assertTrue(r['ok']);self.assertEqual(get.call_count,1)
        params=j.parse_qs(j.urlsplit(get.call_args.args[0]).query)
        expression=json.loads(params['query'][0])['query']['query_string']['query']
        self.assertEqual(expression,'titulo:"ley"')

    def test_web_rejects_unpreserved_filters_and_ambiguous_literals_before_network(self):
        cases=[{'desde':'2026-01-01'},{'hasta':'2026-01-01'},{'inicio':50},{'solo_titulo':'yes'},{'modo':'invalid'}]
        with patch.object(j.HTTP,'get') as get:
            for kw in cases:
                self.assertFalse(j.run_safe(j.boe_buscar,'ejemplo',**({'modo':'web'}|kw))['ok'])
            for text in ['una "frase"','una\\frase']:
                self.assertFalse(j.run_safe(j.boe_buscar,text,modo='web')['ok'])
            get.assert_not_called()

    def test_final_page_and_bounded_truncation(self):
        with patch.object(j.HTTP,'get',return_value=response(FIXTURE.read_bytes())):
            r=j.boe_buscar('ejemplo',modo='web',inicio=19,limite=25)
        self.assertEqual(len(r['datos']['data']),1)
        self.assertIsNone(r['paginacion']['siguiente_inicio'])
        self.assertFalse(r['datos']['truncado'])

    def test_only_exact_web_route_is_allowed(self):
        j.check_url('https://www.boe.es/buscar/legislacion.php?accion=Buscar')
        for u in ['https://www.boe.es/buscar/legislacion.php/evil','https://www.boe.es/mi_boe/login.php']:
            with self.assertRaises(j.JuridicoError):j.check_url(u)

if __name__=='__main__':unittest.main()

class OperationalLogging(unittest.TestCase):
    def test_logs_status_without_query_or_source_message(self):
        def operation(secret):
            raise j.JuridicoError('HTTP_ERROR','SOURCE_SECRET',status=500)
        with self.assertLogs(j.LOG,level='INFO') as logs:
            r=j.run_safe(operation,'PRIVATE_QUERY')
        self.assertFalse(r['ok'])
        logged=' '.join(logs.output)
        self.assertIn('estado=error',logged);self.assertIn('http_status=500',logged)
        self.assertNotIn('SOURCE_SECRET',logged);self.assertNotIn('PRIVATE_QUERY',logged)

    def test_logs_partial_distinct_from_complete(self):
        def operation():return {'ok':True,'datos':{'recuperacion_completa':False}}
        with self.assertLogs(j.LOG,level='INFO') as logs:j.run_safe(operation)
        self.assertIn('estado=parcial',' '.join(logs.output))
