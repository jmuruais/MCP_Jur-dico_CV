import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import juridico as j
F=Path(__file__).with_name('fixtures')
CAT=json.loads((F/'dogv-decreto-versiones.json').read_text())
BASE={'id':327983,'codigoInsercion':'2018/7822','titulo':'DECRETO 104/2018, de 27 de julio','numeroDogv':8356,'fechaPublicacion':'2018-08-07','consolidacion':True,'consolidacionVigente':False,'estado':{'descripcion':'VIGENTE'},'version':3,'contieneAnexo':False,'texto':'Versión vigente: 17.08.2022 Texto consolidado con referencia al anexo.'}
PDFTEXT='Num. 8356 / 07.08.2018\nDECRETO 104/2018. [2018/7822]\nTexto original.\nANEXO\nNiveles de respuesta educativa.'
def response(data,url):
 return {'body':data if isinstance(data,bytes) else json.dumps(data).encode(),'url':url,'consultado_en':'2026-11-03T00:00:00Z','cache':False,'content_type':'application/json'}

def text_packet():
 return {'texto':PDFTEXT,'segmentos':[{'pagina_pdf':1,'idioma':'es','inicio':0,'fin':len(PDFTEXT)}], 'paginas':[], 'tablas':[], 'extraccion_parcial':True, 'extraccion_verificada':False}

class Precision(unittest.TestCase):
 def setUp(self):
  self.base=copy.deepcopy(BASE);self.cat=copy.deepcopy(CAT);self.wrong_pdf=False;self.cat_error=False
 def get(self,url,*args,**kwargs):
  if '/fechasVigencia' in url:
   if self.cat_error:raise j.JuridicoError('HTTP_ERROR','fuente',status=503)
   return response(self.cat,url)
  if '/textoVigencia' in url:
   i=int(j.parse_qs(j.urlsplit(url).query)['idConsolidacion'][0]);n={3078:1,3079:2,3080:3}[i]
   return response({'texto':'<p>Redacción '+str(n)+'; referencia al anexo.</p>','version':n,'contieneAnexos':False,'estado':'VIGENTE','versionSuperada':n!=3},url)
  if '/export/disposicion/' in url:
   return response(b'/consolidacion/2018/actual.pdf' if self.wrong_pdf else b'/2018/08/07/pdf/2018_7822.pdf',url)
  if '/datos/' in url:return response(b'%PDF-test',url)
  return response(self.base,url)
 def call(self,**kw):
  with patch.object(j.HTTP,'get',side_effect=self.get),patch.object(j,'extract_pdf',return_value=PDFTEXT),patch.object(j,'extract_pdf_document',side_effect=lambda *a: dict(text_packet())):
   return j.run_safe(j.dogv_publicacion,'327983',**kw)
 def test_current_text_has_distinct_original_and_version_dates(self):
  r=self.call();d=r['datos'];self.assertTrue(r['ok'])
  self.assertEqual(d['naturaleza_texto'],'texto_consolidado_html')
  self.assertEqual(d['fecha_publicacion_original'],'2018-08-07')
  self.assertEqual(d['fecha_publicacion_texto'],'2022-08-16')
  self.assertEqual(d['version_texto']['fecha_inicio_declarada'],'2022-08-17')
  self.assertIsNone(d['vigencia_juridica_automatica'])
  self.assertIn('no determina vigencia',r['advertencia'])
  self.assertEqual(len(d['versiones_disponibles']),3)
 def test_historical_boundaries_select_source_intervals(self):
  for date,n in [('2021-06-03',1),('2021-06-04',2),('2022-08-16',2),('2022-08-17',3)]:
   r=self.call(fecha=date);self.assertTrue(r['ok']);self.assertEqual(r['datos']['version'],n)
   self.assertEqual(r['datos']['fecha_solicitada'],date)
   self.assertIsNone(r['datos']['vigencia_juridica_automatica'])
 def test_before_first_interval_does_not_invent_text(self):
  self.assertEqual(self.call(fecha='2018-08-07')['error']['codigo'],'SIN_VERSION_EN_FECHA')
 def test_overlaps_and_future_publication_are_rejected(self):
  self.cat[1]['fechaFinVigencia']='18/08/2022'
  self.assertEqual(self.call(fecha='2022-08-17')['error']['codigo'],'VERSION_AMBIGUA')
  self.cat=copy.deepcopy(CAT);self.cat[0]['fechaPublicacion']='20220818'
  self.assertEqual(self.call(fecha='2022-08-17')['error']['codigo'],'VERSION_NO_PUBLICADA_EN_FECHA')
 def test_original_pdf_is_not_consolidated_and_annex_is_detected(self):
  r=self.call(tipo_texto='original');d=r['datos'];self.assertTrue(r['ok'])
  self.assertEqual(d['naturaleza_texto'],'publicacion_original_pdf')
  self.assertEqual(d['fecha_publicacion_texto'],'2018-08-07')
  self.assertIsNone(d['version']);self.assertEqual(d['version_ficha'],3)
  self.assertTrue(d['anexos']['encabezado_detectado'])
  self.assertFalse(d['anexos']['indicador_ficha'])
  self.assertIsNone(d['documento_original']['firma_criptografica_verificada'])
  self.assertIn('sha256_fuente',d['documento_original'])
 def test_consolidation_pdf_never_replaces_original(self):
  self.wrong_pdf=True
  self.assertEqual(self.call(tipo_texto='original')['error']['codigo'],'ORIGINAL_NO_VERIFICADO')
 def test_original_pdf_identity_is_checked(self):
  with patch.object(j.HTTP,'get',side_effect=self.get),patch.object(j,'extract_pdf',return_value=PDFTEXT.replace('[2018/7822]','[2018/9999]')):
   self.assertEqual(j.run_safe(j.dogv_publicacion,'327983',tipo_texto='original')['error']['codigo'],'ORIGINAL_NO_VERIFICADO')
 def test_catalog_failure_is_partial_for_portal_and_error_for_history(self):
  self.cat_error=True;r=self.call();self.assertTrue(r['ok']);self.assertFalse(r['datos']['recuperacion_completa'])
  self.assertIn('sin_version_verificada',r['datos']['naturaleza_texto'])
  self.assertFalse(self.call(fecha='2021-01-01')['ok'])
  self.assertFalse(self.call(tipo_texto='original')['ok'])
 def test_no_original_or_date_conflict_is_silently_substituted(self):
  self.cat=[x for x in self.cat if not x['inicial']]
  self.assertEqual(self.call(tipo_texto='original')['error']['codigo'],'ORIGINAL_NO_VERIFICADO')
  with patch.object(j.HTTP,'get') as get:
   self.assertFalse(j.run_safe(j.dogv_publicacion,'327983',tipo_texto='original',fecha='2021-01-01')['ok']);get.assert_not_called()
 def test_annex_reference_does_not_claim_full_annex(self):
  r=self.call(max_caracteres=500);d=r['datos'];self.assertFalse(d['anexos_incluidos'])
  self.assertTrue(d['anexos']['referencias_en_texto']);self.assertFalse(d['anexos']['encabezado_detectado'])
 def test_unified_dogv_date_uses_same_selector(self):
  with patch.object(j,'dogv_publicacion',return_value={'ok':True}) as pub:
   j.juridico_documento('DOGV','2018/7822',fecha='2021-01-01')
  self.assertEqual(pub.call_args.kwargs['fecha'],'2021-01-01')
 def test_historical_summaries_recover_references_without_official_positions(self):
  for date,total in [('2018-07-13',39),('2018-08-07',48)]:
   d=json.loads((F/('dogv-summary-'+date+'.json')).read_text())
   with patch.object(j.HTTP,'get',return_value=response(d,j.DOGV)):
    r=j.dogv_sumario(date,limite=3);strict=j.run_safe(j.dogv_sumario,date,exigir_orden=True)
   self.assertTrue(r['ok']);self.assertEqual(r['datos']['total'],total)
   self.assertFalse(r['datos']['orden_verificado']);self.assertFalse(r['datos']['recuperacion_completa'])
   self.assertIn('ORDEN NO VERIFICADO',r['advertencia']);self.assertFalse(strict['ok'])
   pages=[int(x['paginaInicial']) for x in r['datos']['publicaciones']];self.assertEqual(pages,sorted(pages))
 def test_wrong_summary_collection_is_not_partial_success(self):
  d=json.loads((F/'dogv-summary-2018-08-07.json').read_text())
  with patch.object(j.HTTP,'get',return_value=response(d,j.DOGV)):
   self.assertEqual(j.run_safe(j.dogv_sumario,'2018-07-13')['error']['codigo'],'EDICION_NO_VERIFICADA')
 def test_exact_search_excludes_references_in_other_titles_and_preserves_candidates(self):
  rows=[{'id':1,'codigoInsercion':'2019/210','titulo':'ORDEN 1/2019, desarrolla el Decreto 104/2018'}, {'id':2,'codigoInsercion':'2018/7822','titulo':'DECRETO 104/2018, de 27 de julio'}]
  d={'pageNumber':0,'pageSize':10,'totalElements':2,'content':rows}
  with patch.object(j.HTTP,'post_query',return_value=response(d,j.DOGV)) as post:
   r=j.dogv_buscar('Decreto 104/2018',modo='disposicion',limite=1)
  self.assertTrue(post.call_args.args[1]['soloTitulo'])
  self.assertEqual(r['datos']['publicaciones'][0]['codigoInsercion'],'2018/7822')
  self.assertEqual(r['datos']['publicaciones'][0]['posicion_en_fuente'],1)
  self.assertEqual(r['datos']['candidatos_fuente'][0]['id'],1)
  self.assertTrue(r['datos']['recuperacion_completa']);self.assertEqual(r['datos']['total'],1)
 def test_exact_search_incomplete_page_does_not_prove_absence(self):
  d={'pageNumber':0,'pageSize':10,'totalElements':20,'content':[{'id':1,'codigoInsercion':'2026/1','titulo':'ORDEN 1/2026, desarrolla el Decreto 104/2018'}]}
  with patch.object(j.HTTP,'post_query',return_value=response(d,j.DOGV)):
   r=j.dogv_buscar('Decreto 104/2018',modo='disposicion')
  self.assertFalse(r['datos']['recuperacion_completa']);self.assertIsNone(r['datos']['total']);self.assertEqual(r['datos']['publicaciones'],[])
 def test_exact_query_requires_number_and_type_before_network(self):
  with patch.object(j.HTTP,'post_query') as post:
   for q in ['inclusión educativa','104/2018','Decreto 104/2018 y Orden 20/2019']:
    self.assertEqual(j.run_safe(j.dogv_buscar,q,modo='disposicion')['error']['codigo'],'REFERENCIA_NORMATIVA_REQUERIDA')
   post.assert_not_called()
 def test_pdf_url_allowlist_rejects_other_files_and_hosts(self):
  for u in ['https://dogv.gva.es/datos/2018/08/07/pdf/2018_7822.pdf','https://dogv.gva.es/dogv-portal/disposicion/327983/fechasVigencia']:
   j.check_url(u)
  for u in ['https://dogv.gva.es/datos/secret.pdf','https://dogv.gva.es/datos/2018/08/07/pdf/../secret.pdf','https://evil.example/datos/2018/08/07/pdf/2018_7822.pdf']:
   with self.assertRaises(j.JuridicoError):j.check_url(u)

class AdditionalPrecision(unittest.TestCase):
 def test_exact_title_requires_boundary_after_year(self):
  rows=[{'id':1,'codigoInsercion':'2018/1','titulo':'DECRETO 104/2018bis, no coincide'},{'id':2,'codigoInsercion':'2018/2','titulo':'DECRETO 104/20180, no coincide'}]
  d={'pageNumber':0,'pageSize':10,'totalElements':2,'content':rows}
  with patch.object(j.HTTP,'post_query',return_value=response(d,j.DOGV)):
   r=j.dogv_buscar('Decreto 104/2018',modo='disposicion')
  self.assertEqual(r['datos']['publicaciones'],[]);self.assertEqual(r['datos']['total'],0)
 def test_pdf_reference_must_identify_first_page_not_only_a_later_citation(self):
  obj=Precision();obj.setUp()
  text=PDFTEXT.replace('[2018/7822]','[2018/9999]')+'\fReferencia posterior [2018/7822]'
  with patch.object(j.HTTP,'get',side_effect=obj.get),patch.object(j,'extract_pdf',return_value=text):
   self.assertEqual(j.run_safe(j.dogv_publicacion,'327983',tipo_texto='original')['error']['codigo'],'ORIGINAL_NO_VERIFICADO')
 def test_catalog_rejects_duplicate_ids_and_bad_dates(self):
  for cat in [CAT+[CAT[0]], [dict(CAT[0],fechaInicioVigencia='99/99/2022')]]:
   with patch.object(j.HTTP,'get',return_value=response(cat,j.DOGV)):
    with self.assertRaises(j.JuridicoError):j.dogv_versions('327983','es_es')
 def test_unverified_order_with_duplicate_pages_does_not_invent_sort(self):
  d=json.loads((F/'dogv-summary-2018-08-07.json').read_text());d['disposiciones'][1]['paginaInicial']=d['disposiciones'][0]['paginaInicial']
  with patch.object(j.HTTP,'get',return_value=response(d,j.DOGV)):
   r=j.dogv_sumario('2018-08-07',limite=2)
  self.assertFalse(r['datos']['orden_verificado'])
  self.assertEqual(r['datos']['publicaciones'][0]['id'],d['disposiciones'][0]['id'])
  self.assertIn('secuencia recibida',r['datos']['verificacion_orden']['criterio_presentacion'])

class Compatibility(unittest.TestCase):
 def test_original_selector_works_with_the_existing_identifier_argument(self):
  obj=Precision();obj.setUp()
  with patch.object(j.HTTP,'get',side_effect=obj.get),patch.object(j,'extract_pdf',return_value=PDFTEXT),patch.object(j,'extract_pdf_document',side_effect=lambda *a: dict(text_packet())):
   r=j.dogv_publicacion('original:327983')
  self.assertEqual(r['datos']['naturaleza_texto'],'publicacion_original_pdf')
  self.assertEqual(r['datos']['codigoInsercion'],'2018/7822')
  self.assertIn('selector_compatibilidad',r['datos'])
 def test_original_selector_does_not_discard_date_conflicts(self):
  with patch.object(j.HTTP,'get') as get:
   r=j.run_safe(j.dogv_publicacion,'original:327983',fecha='2021-01-01')
  self.assertFalse(r['ok']);get.assert_not_called()

if __name__=='__main__':unittest.main()
