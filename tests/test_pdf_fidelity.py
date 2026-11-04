import io,json,sys,unittest,os
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError,URLError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import juridico as j
import pdf_geometry as g
F=Path(__file__).with_name('fixtures')
class Identity(unittest.TestCase):
 def test_T05_T06_T07_reference_headers_and_citations(self):
  refs=json.loads((F/'cendoj-identidades.json').read_text())
  for ref in refs:
   r=j.cendoj_identity(ref['texto'],ref['roj'],ref['ecli'])
   self.assertEqual((r['roj_resolucion'],r['ecli_resolucion']),(ref['roj'],ref['ecli']))
   self.assertTrue(r['identificacion_verificada']);self.assertTrue(r['coincidencia_busqueda_verificada'])
   self.assertNotIn(ref['roj'],r['roj_resoluciones_citadas'])
   for cited in ref['citadas']:self.assertIn(cited,r['roj_resoluciones_citadas'])
 def test_body_only_and_second_page_do_not_identify(self):
  for text in ['Sentencia cita STS 5603/2025 ECLI:ES:TS:2025:5603','primera\fRoj: STS 5603/2025 - ECLI:ES:TS:2025:5603','Id Cendoj: 1\nRoj: STS 5603/2025 - ECLI:ES:TS:2025:5603']:
   r=j.cendoj_identity(text);self.assertFalse(r['identificacion_verificada']);self.assertIsNone(r['roj_resolucion'])
 def test_discrepancy_is_visible(self):
  r=j.cendoj_identity('Roj: STS 5603/2025 - ECLI:ES:TS:2025:5603\nId Cendoj: 1','STS 5562/2025','ECLI:ES:TS:2025:5562')
  self.assertFalse(r['identificacion_verificada']);self.assertFalse(r['coincidencia_busqueda_verificada']);self.assertIn('DISCREPANCIA',r['advertencias_identificacion'][0])
 def test_ambiguous_header_and_incoherent_pair(self):
  for text in ['Roj: ATS 11323/2025 - ECLI:ES:TS:2025:11323','Roj: STS 1/2025 - ECLI:ES:TS:2025:1\nRoj: STS 2/2025 - ECLI:ES:TS:2025:2']:
   self.assertFalse(j.cendoj_identity(text)['identificacion_verificada'])
 def test_link_without_search_does_not_claim_search_match(self):
  r=j.cendoj_identity('Roj: STS 1/2025 - ECLI:ES:TS:2025:1');self.assertTrue(r['identificacion_verificada']);self.assertIsNone(r['coincidencia_busqueda_verificada'])
class Transport(unittest.TestCase):
 def test_T09_block_and_rate_limit_not_retried(self):
  for status in [403,401,429]:
   http=j.OfficialHTTP();error=HTTPError(j.CENDOJ+'indexAN.jsp',status,'Error',{},io.BytesIO())
   with patch.object(http.opener,'open',side_effect=error) as op,patch.object(j.time,'sleep'):
    with self.assertRaises(j.JuridicoError) as c:http.get(j.CENDOJ+'indexAN.jsp')
   self.assertEqual(op.call_count,1);self.assertEqual(c.exception.status,status)
 def test_transient_has_at_most_one_retry(self):
  for status in [502,503,504]:
   http=j.OfficialHTTP()
   def fail(*a,**kw):raise HTTPError(j.CENDOJ+'indexAN.jsp',status,'Error',{},io.BytesIO())
   with patch.object(http.opener,'open',side_effect=fail) as op,patch.object(j.time,'sleep'):
    with self.assertRaises(j.JuridicoError) as c:http.get(j.CENDOJ+'indexAN.jsp')
   self.assertEqual(op.call_count,2);self.assertTrue(c.exception.reintentable)
 def test_long_retry_after_stops(self):
  http=j.OfficialHTTP();error=HTTPError(j.CENDOJ+'indexAN.jsp',503,'Error',{'Retry-After':'120'},io.BytesIO())
  with patch.object(http.opener,'open',side_effect=error) as op,patch.object(j.time,'sleep') as sleep:
   with self.assertRaises(j.JuridicoError):http.get(j.CENDOJ+'indexAN.jsp')
  self.assertEqual(op.call_count,1);sleep.assert_not_called()
 def test_empty_not_zero_or_captcha(self):
  with self.assertRaises(j.JuridicoError) as c:j.cendoj_results('')
  self.assertEqual(c.exception.codigo,'RESPUESTA_VACIA')
  with self.assertRaises(j.JuridicoError) as c:j.cendoj_results('<div id="captcha">Verifique</div>')
  self.assertEqual(c.exception.codigo,'ACCESO_INTERACTIVO_REQUERIDO')
 def test_connectivity_distinct_from_block(self):
  http=j.OfficialHTTP()
  with patch.object(http.opener,'open',side_effect=URLError('offline')) as op:
   with self.assertRaises(j.JuridicoError) as c:http.get(j.CENDOJ+'indexAN.jsp')
  self.assertEqual(c.exception.codigo,'FUENTE_NO_DISPONIBLE');self.assertEqual(op.call_count,1)
class Geometry(unittest.TestCase):
 def test_language_is_not_position(self):
  es='Artículo educación del alumnado con los apoyos para las medidas';va='Article educació de l’alumnat amb els suports per les mesures'
  self.assertEqual(g.identify_language(es)[0],'es');self.assertEqual(g.identify_language(va)[0],'va');self.assertIsNone(g.identify_language('firma 2026')[0])
 def test_spanning_lines_never_cut_into_two_languages(self):
  lines=[{'bbox':[20,100,580,115],'text':'contenido '*100}]
  self.assertIsNone(g.split_columns(lines,600))
 def test_T04_page_offsets_cross_formfeed(self):
  r=j.plain_pdf_pages('a'*600+'\f'+'b'*600,580,500,'https://example.test/doc.pdf')
  self.assertEqual([p['pagina_pdf'] for p in r['paginas_fragmento']],[1,2]);self.assertEqual(r['paginas_fragmento'][1]['inicio'],601)
 def test_T10_partial_states_not_conflated(self):
  e={'segmentos':[{'pagina_pdf':3,'inicio':0,'fin':600,'idioma':'es'}],'paginas':[],'tablas':[{'pagina_pdf':3,'idioma':'es','tabla_estructura_verificada':False}], 'documento_recuperado':True,'texto_extraido':True,'extraccion_verificada':False,'extraccion_parcial':True}
  r=j.pdf_fragment_metadata(e,0,500,'https://example.test/doc.pdf')
  self.assertTrue(r['documento_recuperado']);self.assertFalse(r['extraccion_verificada']);self.assertTrue(r['extraccion_parcial']);self.assertFalse(r['tabla_estructura_verificada']);self.assertTrue(r['paginas_fragmento'][0]['url_oficial'].endswith('#page=3'))
 def test_pdf_failure_does_not_return_mixed_fallback(self):
  with patch.object(j.subprocess,'run',return_value=type('R',(),{'returncode':1})()):
   with self.assertRaises(j.JuridicoError) as c:j.extract_pdf_document(b'%PDF-test')
  self.assertEqual(c.exception.codigo,'PDF_GEOMETRIA_NO_EXTRAIBLE')

if __name__=='__main__':unittest.main()

class SyntheticDocuments(unittest.TestCase):
 def pdf(self,columns,table=False):
  import pymupdf,tempfile
  d=pymupdf.open();p=d.new_page(width=620,height=850)
  for x,text in columns:
   p.insert_textbox(pymupdf.Rect(x,100,x+230,730),text,fontsize=10)
  if table:
   for x in [25,280,560]:p.draw_line((x,90),(x,750))
   for y in [90,200,350,500,750]:p.draw_line((25,y),(560,y))
  f=tempfile.NamedTemporaryFile(suffix='.pdf',delete=False);f.close();d.save(f.name);d.close();self.addCleanup(lambda:Path(f.name).unlink(missing_ok=True));return f.name
 def test_reversed_columns_do_not_swap_languages(self):
  es=('Artículo. Los apoyos para las medidas del alumnado.\n'*10)
  va=('Article. Els suports per les mesures de alumnat.\n'*10)
  p=self.pdf([(25,es),(330,va)])
  for lang,good,bad in [('es','Los apoyos','Els suports'),('va','Els suports','Los apoyos')]:
   r=g.extract(p,lang);self.assertIn(good,r['texto']);self.assertNotIn(bad,r['texto']);self.assertFalse(r['paginas_omitidas'])
 def test_ambiguous_page_is_omitted_explicitly(self):
  r=g.extract(self.pdf([(25,'123 firma X')]),'es')
  self.assertEqual(r['paginas_omitidas'],[1]);self.assertTrue(r['extraccion_parcial']);self.assertFalse(r['texto_extraido']);self.assertFalse(r['extraccion_verificada'])
 def test_both_has_separate_labelled_segments(self):
  p=self.pdf([(25,'Article. Els suports per les mesures de alumnat.\n'*10),(330,'Artículo. Los apoyos para las medidas del alumnado.\n'*10)])
  r=g.extract(p,'ambos');self.assertEqual({s['idioma'] for s in r['segmentos']},{'es','va'});self.assertEqual(len(r['segmentos']),2)
 def test_unrecognised_table_not_verified_or_flattened(self):
  p=self.pdf([(35,'Los apoyos para las medidas del alumnado.\n'*12)],True)
  r=g.extract(p,'es');self.assertTrue(r['tablas']);self.assertFalse(any(t['tabla_estructura_verificada'] for t in r['tablas']));self.assertIn('ESTRUCTURA NO VERIFICADA',r['texto']);self.assertTrue(r['extraccion_parcial'])
