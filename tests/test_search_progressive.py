import sys,json,copy,unittest,io
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import juridico as j
import search_logic as s

def row(n,title,code=None):return {'id':n,'titulo':title,'codigoInsercion':code or '2023/'+str(n),'fechaPublicacion':'21/04/2023','organismo':'Generalitat','numeroDogv':9580}
def result(rows,total=None,start=0):
 d={'publicaciones':copy.deepcopy(rows),'total':len(rows) if total is None else total,'siguiente_inicio':start+len(rows) if total and start+len(rows)<total else None,'filtros':{'solo_titulo':True},'recuperacion_completa':True}
 return {'ok':True,'datos':d,'url_api':j.DOGV+'/dogv/search','url_oficial':'https://dogv.gva.es/es/','consultado_en':'2026-11-04T00:00:00Z','cache':False,'sha256_fuente':'a'*64}
def verify(item,*args):return dict(item,identificacion_verificada=True)
class ReferenceVocabulary(unittest.TestCase):
 def test_second_reference_with_shared_type_vocabulary_is_rejected(self):
  for text in ['Ley 4/2021 y Decret 3/2020','Ley 4/2021 y Ordre 3/2020','Ley 4/2021 y Resolucio 3/2020','Ley 4/2021 y Decreto legislativo 3/2020']:
   with self.subTest(text=text):
    with self.assertRaises(j.JuridicoError) as caught:s.reference(j,text)
    self.assertEqual(caught.exception.codigo,'REFERENCIA_NORMATIVA_REQUERIDA')
    self.assertEqual(caught.exception.mensaje,'Consultar una referencia normativa por llamada.')
 def test_simple_supported_forms_keep_type_number_and_year(self):
  table=[('Ley 4/2021','ley',4,2021),('Llei 4/2021','ley',4,2021),('Decreto 104/2018','decreto',104,2018),('Decret 104/2018','decreto',104,2018),('Orden 20/2019','orden',20,2019),('Ordre 20/2019','orden',20,2019),('Resolucion 5/2020','resolucion',5,2020),('Resolucio 5/2020','resolucion',5,2020),('Decreto ley 1/2021','decreto ley',1,2021),('Decreto-ley 1/2021','decreto ley',1,2021),('Decreto legislativo 1/2015','decreto legislativo',1,2015)]
  for text,tipo,numero,ano in table:
   with self.subTest(text=text):
    r=s.reference(j,text);self.assertEqual((r['tipo'],r['numero'],r['ano']),(tipo,numero,ano))
 def test_multiple_spanish_references_and_decree_law_are_still_rejected(self):
  for text in ['Ley 4/2021 y Decreto 3/2020','Ley 4/2021 y Ley 5/2022','Ley 4/2021 y Decreto ley 3/2020','Ley 4/2021 y Decreto-ley 3/2020']:
   with self.subTest(text=text):
    with self.assertRaises(j.JuridicoError) as caught:s.reference(j,text)
    self.assertEqual(caught.exception.mensaje,'Consultar una referencia normativa por llamada.')
 def test_context_without_number_and_year_is_not_a_second_reference(self):
  r=s.reference(j,'Ley 4/2021 sobre el decreto legislativo de 1965')
  self.assertEqual((r['tipo'],r['numero'],r['ano']),('ley',4,2021))
  self.assertIn('decreto legislativo de 1965',r['contexto'])
  with self.assertRaises(j.JuridicoError) as caught:s.reference(j,'Ley 4/2021 sobre el decreto legislativo 1/1965')
  self.assertEqual(caught.exception.mensaje,'Consultar una referencia normativa por llamada.')
class Dogv(unittest.TestCase):
 def call(self,text,fn,**kw):
  with patch.object(j,'dogv_search_metadata',side_effect=verify),patch.object(j,'dogv_buscar',side_effect=fn):return s.dogv_locate(j,text,'es',0,10,'','',False,**kw)
 def test_reference_extracts_context_without_hardcoded_signatures(self):
  r=s.reference(j,'Localiza la Ley 4/2021 de función pública valenciana');self.assertEqual(r['numero'],4);self.assertEqual(r['ano'],2021);self.assertIn('publica',r['terminos'])
 def test_D02_exact_after_year_strategy_and_no_global_exhaustiveness(self):
  calls=[]
  def fn(q,**kw):
   calls.append(kw);return result([row(1,'Anuncio que cita la Ley 5/2023')],20) if not kw['desde'] else result([row(4174,'LEY 5/2023, contra el despoblamiento')])
  r=self.call('Ley 5/2023 contra el despoblamiento',fn)['datos'];self.assertEqual(r['localizacion'],'localizada');self.assertEqual(len(calls),2);self.assertFalse(r['recuperacion_completa']);self.assertFalse(r['busqueda_agotada'])
 def test_D04_publication_can_be_in_a_later_year(self):
  r=self.call('Decreto 104/2018',lambda *a,**kw:result([row(1,'DECRETO 104/2018, ejemplo')]))['datos'];self.assertEqual(r['localizacion'],'localizada');self.assertEqual(r['paginas_consultadas'],1)
 def test_D05_D06_orders_are_ambiguous_then_disambiguated_by_subject(self):
  rows=[row(1,'ORDEN 20/2019, enseñanzas deportivas'),row(2,'ORDEN 20/2019, respuesta educativa para la inclusión'),row(3,'ORDEN 20/2019, empleo público')]
  for query,expected in [('Orden 20/2019',None),('Orden 20/2019 de inclusión educativa',2),('Orden 20/2019 de enseñanzas deportivas',1)]:
   d=self.call(query,lambda *a,**kw:result(rows))['datos']
   if expected:self.assertEqual(d['publicaciones'][0]['id'],expected);self.assertEqual(d['localizacion'],'localizada')
   else:self.assertEqual(d['localizacion'],'ambigua');self.assertEqual(len(d['publicaciones']),3)
 def test_D07_budget_stop_is_partial_and_preserves_continuation(self):
  d=self.call('Ley 4/2021',lambda *a,**kw:result([row(i,'Anuncio Ley 4/2021') for i in range(10)],100),max_paginas=1)['datos'];self.assertEqual(d['localizacion'],'no_confirmada');self.assertEqual(d['siguiente_inicio'],10);self.assertFalse(d['busqueda_agotada']);self.assertFalse(d['recuperacion_completa'])
 def test_relation_needs_explicit_title_evidence(self):
  ref=s.reference(j,'Ley 4/2021')
  self.assertEqual(s.classify(ref,row(1,'Anuncio sobre Ley 4/2021'))[0],'mencion_documental')
  kind,evidence=s.classify(ref,row(2,'DECRETO 2/2023, por el que se modifica la Ley 4/2021'))
  self.assertEqual(kind,'disposicion_relacionada');self.assertEqual(evidence['fuente'],'titulo_oficial')
 def test_decree_law_relations_accept_official_separators_and_language(self):
  ref=s.reference(j,'Decreto ley 1/2021')
  for title in ['ORDEN 5/2022, por la que se modifica el Decreto-Ley 1/2021 de medidas',
                'ORDEN 5/2022, por la que se deroga el Decreto ley 1/2021 de medidas',
                'ORDEN 5/2022, por la que se modifica el Decret-llei 1/2021 de mesures']:
   with self.subTest(title=title):
    kind,evidence=s.classify(ref,{'titulo':title})
    self.assertEqual(kind,'disposicion_relacionada')
    self.assertEqual(evidence['fuente'],'titulo_oficial')
  self.assertEqual(s.classify(ref,{'titulo':'ORDEN 5/2022, por la que se modifica el Decreto-Ley 11/2021'})[0],'mencion_documental')
  self.assertEqual(s.classify(ref,{'titulo':'Anuncio sobre el Decreto-Ley 1/2021'})[0],'mencion_documental')
 def test_exact_prefix_is_not_enough_to_verify_identity(self):
  with patch.object(j,'dogv_buscar',return_value=result([row(1,'LEY 4/2021, ejemplo')])),patch.object(j,'dogv_search_metadata',side_effect=j.JuridicoError('IDENTIDAD_NO_VERIFICADA','prueba')):
   d=s.dogv_locate(j,'Ley 4/2021','es',0,10,'','',False,max_paginas=1)['datos']
  self.assertFalse(d['identificacion_verificada']);self.assertEqual(d['localizacion'],'candidata_pendiente')
 def test_access_denial_does_not_try_alternative(self):
  with patch.object(j,'dogv_buscar',side_effect=j.JuridicoError('ACCESO_INTERACTIVO_REQUERIDO','prueba',status=403)) as op:
   r=j.run_safe(s.dogv_locate,j,'Ley 4/2021','es',0,10,'','',False)
  self.assertFalse(r['ok']);self.assertEqual(op.call_count,1)
 def test_invalid_budget_fails_before_network(self):
  with patch.object(j,'dogv_buscar') as op:
   self.assertFalse(j.run_safe(s.dogv_locate,j,'Ley 4/2021','es',0,10,'','',False,max_paginas=6)['ok'])
  op.assert_not_called()
 def test_unresolved_auxiliary_is_not_reported_as_exhaustive_absence(self):
  def auxiliary(core,ref,idioma,desde,hasta,pages,*args):
   pages.append({'estrategia':'referencia_cruzada_boe_titulo','candidatos':2,'total_fuente':100,'inicio':0,'filtros_aplicados':{},'url_api':'https://www.boe.es/buscar/legislacion.php'})
   return None
  with patch.object(j,'dogv_buscar',return_value=result([],0)),patch.object(s,'boe_dogv_anchor',side_effect=auxiliary):
   d=s.dogv_locate(j,'Ley 4/2021','es',0,10,'','',False)['datos']
  self.assertEqual(d['localizacion'],'no_confirmada');self.assertFalse(d['busqueda_agotada']);self.assertFalse(d['recuperacion_completa']);self.assertEqual(d['candidatos_examinados'],2)
 def test_only_current_filter_does_not_use_unfiltered_auxiliary(self):
  with patch.object(j,'dogv_buscar',return_value=result([],0)) as op,patch.object(s,'boe_dogv_anchor') as anchor:
   d=s.dogv_locate(j,'Ley 4/2021','es',0,10,'','',True)['datos']
  anchor.assert_not_called();self.assertTrue(all(x.kwargs['solo_vigentes'] for x in op.call_args_list))
 def test_ficha_checks_dates_in_both_official_formats(self):
  ref=s.reference(j,'Ley 5/2023');item=row(4174,'LEY 5/2023, ejemplo');data=dict(item,fechaPublicacion='2023-04-21')
  r={'body':json.dumps(data).encode(),'url':j.DOGV,'consultado_en':'2026-11-04','cache':False}
  with patch.object(j.HTTP,'get',return_value=r):self.assertTrue(s.verify_dogv(j,item,ref,'es')['identificacion_verificada'])
  data['codigoInsercion']='2023/999';r['body']=json.dumps(data).encode()
  with patch.object(j.HTTP,'get',return_value=r),self.assertRaises(j.JuridicoError):s.verify_dogv(j,item,ref,'es')
 def test_boe_anchor_verifies_date_and_edition_before_getting_signature(self):
  ref=s.reference(j,'Ley 4/2021 de función pública valenciana');pages=[]
  boe={'datos':{'data':[{'identificador':'BOE-A-2021-8880','titulo':'Ley 4/2021, Función Pública Valenciana','metadatos_publicacion':'Comunitat Valenciana','recuperable_api':True}]},'url_api':'https://www.boe.es/buscar/legislacion.php','sha256_fuente':'a','cache':False}
  html='<h3>Ley 4/2021, Función Pública Valenciana</h3><dt>Publicado en:</dt><dd>«DOGV» núm. 9065, de 20/04/2021</dd>'
  summary={'cabecera':{'numeroDogv':9065},'disposiciones':[dict(row(1,'LEY 4/2021, Función Pública Valenciana','2021/3988'),fechaPublicacion='20/04/2021')]}
  def get(url,*a):return {'body':html.encode() if 'boe.es' in url else json.dumps(summary).encode(),'url':url,'cache':False,'consultado_en':'2026-11-04'}
  with patch.object(j,'boe_buscar',return_value=boe),patch.object(j.HTTP,'get',side_effect=get):
   r=s.boe_dogv_anchor(j,ref,'es','','',pages,5,50);self.assertEqual(r['datos']['publicaciones'][0]['codigoInsercion'],'2021/3988')
   summary['cabecera']['numeroDogv']=999
   with self.assertRaises(j.JuridicoError):s.boe_dogv_anchor(j,ref,'es','','',[],5,50)
 def test_boe_anchor_never_drops_user_date_filter(self):
  with patch.object(j,'boe_buscar') as op:self.assertIsNone(s.boe_dogv_anchor(j,s.reference(j,'Ley 4/2021'),'es','','',[],2,50))
  op.assert_not_called()

class TS(unittest.TestCase):
 def reply(self,rows,total=1):
  return {'ok':True,'datos':{'resoluciones':copy.deepcopy(rows),'total_fuente':total,'filtros':{},'siguiente_inicio':None},'url_api':j.CENDOJ,'url_oficial':j.CENDOJ,'consultado_en':'2026-11-04','cache':False,'sha256_fuente':'a','advertencia':''}
 def item(self,n,text,kind='STS'):return {'roj':f'{kind} {n}/2025','ecli':f'ECLI:ES:TS:2025:{n}'+('A' if kind=='ATS' else ''),'resumen_fuente':text,'metadatos':'Sala Social','url_oficial':j.CENDOJ+'AN/openDocument/aaaaaaaaaaaaaaaa'}
 def test_J01_zero_then_quoted_expression_and_max_two_calls(self):
  with patch.object(j,'_ts_buscar_page',side_effect=[self.reply([],0),self.reply([self.item(1,'silla ergonómica en teletrabajo')])]) as op:
   r=j.ts_buscar('Obligación de entregar silla ergonómica a teletrabajadores')
  self.assertEqual(op.call_count,2);self.assertEqual(op.call_args.args[0],'"silla ergonomica"');self.assertEqual(r['datos']['resoluciones'][0]['estado_relevancia'],'candidata_no_examinada');self.assertFalse(r['datos']['identificacion_verificada'])
 def test_aggregate_total_is_unknown_when_alternative_returns_results(self):
  with patch.object(j,'_ts_buscar_page',side_effect=[self.reply([],0),self.reply([self.item(1,'silla ergonomica')],1)]):
   d=j.ts_buscar('silla ergonómica',limite=1)['datos']
  self.assertIsNone(d['total_fuente'])
  self.assertEqual(len(d['resoluciones']),1)
  self.assertEqual([x['total_fuente'] for x in d['traza_busqueda']],[0,1])
  self.assertFalse(d['recuperacion_completa'])
  self.assertIsNone(d['siguiente_inicio'])
  self.assertEqual(d['continuaciones'],[])
 def test_alternative_continuation_retains_its_query_and_offset(self):
  rows=[self.item(i,'silla ergonomica') for i in range(10)]
  with patch.object(j,'_ts_buscar_page',side_effect=[self.reply([],0),self.reply(rows,25)]):
   d=j.ts_buscar('silla ergonómica',limite=2)['datos']
  self.assertIsNone(d['total_fuente'])
  self.assertIsNone(d['siguiente_inicio'])
  self.assertEqual(len(d['continuaciones']),1)
  self.assertEqual(d['continuaciones'][0]['consulta'],'"silla ergonomica"')
  self.assertEqual(d['continuaciones'][0]['inicio'],10)
 def test_J03_phrase_retains_legal_construction(self):self.assertEqual(s.ts_phrases('Plazo de aprobación de facturas e intereses de demora')[0],'plazo de aprobacion')
 def test_J02_official_summary_rank_and_document_type(self):
  rows=[self.item(1,'videovigilancia sustracción titanio'),self.item(2,'videovigilancia de trabajadora en caja de comercio'),self.item(3,'videovigilancia caja','ATS')]
  with patch.object(j,'_ts_buscar_page',return_value=self.reply(rows,3)) as op:r=j.ts_buscar('Videovigilancia de trabajadora en caja de comercio')
  self.assertEqual(op.call_count,1);self.assertEqual(r['datos']['resoluciones'][0]['roj'],'STS 2/2025');self.assertEqual(next(x for x in r['datos']['resoluciones_candidatas'] if x['roj']=='ATS 3/2025')['tipo_resolucion'],'auto')
 def test_chronological_does_not_expand_or_reorder(self):
  rows=[self.item(1,'resumen genérico'),self.item(2,'intereses demora')]
  with patch.object(j,'_ts_buscar_page',return_value=self.reply(rows,100)) as op:r=j.ts_buscar('intereses demora',orden='cronologico')
  self.assertEqual(op.call_count,1);self.assertEqual(r['datos']['resoluciones'][0]['roj'],'STS 1/2025')
 def test_roj_in_query_is_sent_as_roj_not_generic_text(self):
  with patch.object(j,'_ts_buscar_page',return_value=self.reply([self.item(1,'texto')])) as op:j.ts_buscar('STS 1/2025')
  self.assertEqual(op.call_args.args[0],'');self.assertEqual(op.call_args.args[7],'STS 1/2025')
 def test_403_does_not_expand(self):
  with patch.object(j,'_ts_buscar_page',side_effect=j.JuridicoError('ACCESO_INTERACTIVO_REQUERIDO','bloqueo',status=403)) as op:r=j.run_safe(j.ts_buscar,'silla ergonómica')
  self.assertFalse(r['ok']);self.assertEqual(op.call_count,1)
 def test_alternative_error_preserves_primary_as_partial(self):
  with patch.object(j,'_ts_buscar_page',side_effect=[self.reply([self.item(1,'texto')],100),j.JuridicoError('ACCESO_INTERACTIVO_REQUERIDO','bloqueo',status=403)]) as op:r=j.ts_buscar('plazo de aprobación facturas')
  self.assertEqual(op.call_count,2);self.assertFalse(r['datos']['recuperacion_completa']);self.assertEqual(r['datos']['error_estrategia_adicional']['http_status'],403)
  self.assertEqual(r['datos']['continuaciones'],[])
  self.assertIsNone(r['datos']['siguiente_inicio'])
  self.assertIn('BÚSQUEDA PARCIAL',r['advertencia'])
 def test_empty_primary_then_block_returns_structured_failure(self):
  denied=j.JuridicoError('ACCESO_INTERACTIVO_REQUERIDO','bloqueo',status=403)
  with patch.object(j,'_ts_buscar_page',side_effect=[self.reply([],0),denied]) as op:
   r=j.run_safe(j.ts_buscar,'silla ergonómica')
  self.assertEqual(op.call_count,2)
  self.assertFalse(r['ok'])
  self.assertEqual(r['error']['http_status'],403)
  self.assertNotIn('datos',r)
 def test_continuation_points_to_raw_source_page(self):
  rows=[self.item(i,'videovigilancia caja' if i>6 else 'texto') for i in range(10)]
  with patch.object(j,'_ts_buscar_page',return_value=self.reply(rows,20)):r=j.ts_buscar('videovigilancia caja',limite=2,max_consultas=1)
  self.assertEqual(r['datos']['siguiente_inicio'],10);self.assertEqual(len(r['datos']['resoluciones_candidatas']),10)

class HTTPBudget(unittest.TestCase):
 def test_expired_budget_does_not_connect(self):
  b=s.Budget(j,1);b.deadline=0;token=s.SEARCH_BUDGET.set(b)
  try:
   with patch.object(j.HTTP.opener,'open') as op:r=j.run_safe(j.HTTP.get,j.DOGV+'/dogv/latest')
   self.assertEqual(r['error']['codigo'],'PRESUPUESTO_AGOTADO');op.assert_not_called()
  finally:s.SEARCH_BUDGET.reset(token)
 def test_allowlist_for_boe_anchor_is_narrow(self):
  j.check_url('https://www.boe.es/buscar/act.php?id=BOE-A-2021-8880')
  for url in ['https://www.boe.es/buscar/act.php?id=secret','https://www.boe.es/buscar/act.php?id=BOE-A-2021-8880&x=1']:
   with self.assertRaises(j.JuridicoError):j.check_url(url)

if __name__=='__main__':unittest.main()
