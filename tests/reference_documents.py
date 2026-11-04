import sys,json,time,hashlib,resource
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import juridico as j
out=Path(sys.argv[1]);report={'passed':False,'tests':[]}
def check(code,detail,condition):
 report['tests'].append({'case':code,**detail,'passed':bool(condition)});print(code,bool(condition),flush=True)
for name,path in [('decreto',str(out/'decreto.pdf')),('orden',str(out/'orden.pdf'))]:
 allresults={}
 for lang in ['es','va','ambos']:
  t=time.monotonic();r=j.extract_pdf_document(Path(path).read_bytes(),lang);allresults[lang]=r
  (out/(name+'-'+lang+'.json')).write_text(json.dumps(r,ensure_ascii=False,indent=2))
  selected={s['pagina_pdf'] for s in r['segmentos']}
  check(('T01' if name=='decreto' else 'T02')+'-'+lang,{'latency_ms':round((time.monotonic()-t)*1000),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest(),'chars':len(r['texto']),'pages':r['paginas_totales'],'omitted':r['paginas_omitidas'],'rss_kb':resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss},
   not r['paginas_omitidas'] and all(s['idioma'] in (['es','va'] if lang=='ambos' else [lang]) for s in r['segmentos']) and selected==set(range(1,28 if name=='decreto' else 46))-({26} if name=='decreto' and lang=='es' else {27} if name=='decreto' and lang=='va' else set()))
 # Each column compared with independent coordinates from source sample pages.
 import pymupdf as fitz
 doc=fitz.open(path)
 for i in ([0,1,13,24] if name=='decreto' else [0,1,22,43,44]):
  p=doc[i]
  for lang,clip in [('va',fitz.Rect(0,90,295,p.rect.height)),('es',fitz.Rect(300,90,p.rect.width,p.rect.height))]:
   # Reference samples visually reviewed; order is independently checked by y-position of source lines.
   words=p.get_text('words',clip=clip,sort=True)
   expected=''.join(w[4] for w in words)
   segments=[s for s in allresults[lang]['segmentos'] if s['pagina_pdf']==i+1]
   text=''.join(allresults[lang]['texto'][s['inicio']:s['fin']].split(']\n',1)[-1] for s in segments)
   actual=''.join(text.split())
   # get_text words may split ligatures; compare content tokens ignoring whitespace only.
   check('T04-'+name+'-'+str(i+1)+'-'+lang,{'page':i+1,'language':lang},expected==actual)
 if name=='decreto':
  for lang,page,measure,docname in [('es',27,'Adaptaciones curriculares individuales significativas','Plan de actuación personalizado'),('va',26,'Adaptacions curriculars individuals significatives','Pla d’actuació personalitzat')]:
   t=allresults[lang]['tablas'][0]
   check('T03-'+lang,{'page':page,'table':t},t['pagina_pdf']==page and t['tabla_estructura_verificada'] and [r['nivel'] for r in t['filas']]==['I','II','III','IV'] and measure in t['filas'][3]['celdas'][4].replace('\n',' ') and docname in t['filas'][3]['celdas'][5].replace('\n',' ') and 'ordinari' in t['filas'][1]['celdas'][3].lower() and ('planificaci' in t['filas'][0]['celdas'][4].lower()) and ('programaci' in t['filas'][1]['celdas'][4].lower()) and ('enriqu' in t['filas'][2]['celdas'][4].lower()))
refs=json.loads((out/'baseline-ts.json').read_text())
for code,(roj,v) in zip(['T05','T06','T07'],refs.items()):
 path=out/(roj.replace(' ','-').replace('/','-')+'.pdf');text=j.extract_pdf(path.read_bytes());ecli=v['search']['datos']['resoluciones'][0]['ecli'];identity=j.cendoj_identity(text,roj,ecli)
 check(code,{'identity':identity,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},identity['identificacion_verificada'] and identity['coincidencia_busqueda_verificada'] and roj not in identity['roj_resoluciones_citadas'] and (roj!='STS 5603/2025' or set(['ATS 282/2023','STS 114/2021'])<=set(identity['roj_resoluciones_citadas'])))
report['passed']=all(t['passed'] for t in report['tests']);(out/'reference-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print('PASSED',report['passed'])
