"""Localización acotada sobre índices oficiales. Sin corpus, modelos ni fuentes alternativas."""
from contextvars import ContextVar
import re,time,unicodedata
SEARCH_BUDGET=ContextVar('juridico_search_budget',default=None)

class Budget:
 def __init__(self,core,seconds):self.j=core;self.started=time.monotonic();self.deadline=self.started+seconds;self.requests=0;self.hits=0;self.http=[]
 def remaining(self):
  left=self.deadline-time.monotonic()
  if left<=0:raise self.j.JuridicoError('PRESUPUESTO_AGOTADO','Se alcanzó el tiempo de búsqueda; no se infiere ausencia de documentos.')
  return left
 def metrics(self):return {'consultas_externas':self.requests,'aciertos_cache_http':self.hits,'duracion_ms':round((time.monotonic()-self.started)*1000),'respuestas_http':self.http}

def norm(s):return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if not unicodedata.combining(c)).split())
STOP=set('de del la las el los un una unos unas y e o a al en por para con sobre que cual cuales se su sus este esta ley decreto orden resolucion consell generalitat conselleria numero num n funcion'.split())-{'funcion'}
def tokens(s):return list(dict.fromkeys(w for w in re.findall(r'[a-z]+',norm(s)) if len(w)>2 and w not in STOP))
def stem(w):
 if len(w)>4 and w.endswith(('as','os')):w=w[:-1]
 for prefix in ['educ','inclu','ensen','deport']:
  if w.startswith(prefix):return prefix
 return w[:7]
KINDS={'ley':('ley','(?:ley|llei)'), 'llei':('ley','(?:ley|llei)'), 'decreto':('decreto','(?:decreto|decret)'), 'decret':('decreto','(?:decreto|decret)'), 'orden':('orden','(?:orden|ordre)'), 'ordre':('orden','(?:orden|ordre)'), 'resolucion':('resolucion','(?:resolucion|resolucio)'), 'resolucio':('resolucion','(?:resolucion|resolucio)'), 'decreto ley':('decreto ley','(?:decreto[ -]ley|decret[ -]llei)'), 'decreto legislativo':('decreto legislativo','decreto legislativo')}
# Vocabulario del tipo normativo compartido por el parser y el guard; formas compuestas primero.
TYPE_FORMS=('decreto[ -]ley','decreto legislativo','decreto','decret','ley','llei','orden','ordre','resolucion','resolucio')
# Variante valenciana ya rechazada como segunda referencia; no se admite como referencia inicial.
EXTRA_GUARD_FORMS=('decret[ -]llei',)
TYPE_PATTERN='(?:'+'|'.join(TYPE_FORMS)+')'
GUARD_TYPE_PATTERN='(?:'+'|'.join(EXTRA_GUARD_FORMS+TYPE_FORMS)+')'

def reference(core,text):
 text=norm(text)
 m=re.fullmatch(r'\s*(?:(?:busca|buscar|localiza|localizar|encuentra|recupera)\s+(?:(?:la|el)\s+)?)?('+TYPE_PATTERN+r')\s+(?:n[.º°o]*\s*)?(\d{1,6})\s*/\s*(\d{4})(?=$|[\s,.;:])(.*)',text)
 if not m:raise core.JuridicoError('REFERENCIA_NORMATIVA_REQUERIDA','Indicar tipo y número/año; puede añadirse materia u organismo. Ejemplo: Ley 4/2021 de función pública valenciana.')
 # Varias referencias en una consulta no se interpretan como una sola norma.
 if re.search(r'\b'+GUARD_TYPE_PATTERN+r'\s+\d+/\d{4}',m[4]):raise core.JuridicoError('REFERENCIA_NORMATIVA_REQUERIDA','Consultar una referencia normativa por llamada.')
 kind,pattern=KINDS[m[1].replace('-',' ')]
 return {'tipo':kind,'numero':int(m[2]),'ano':int(m[3]),'contexto':m[4].strip(' ,.;:'),'terminos':tokens(m[4]),'consulta_base':kind.capitalize()+' '+str(int(m[2]))+'/'+m[3], 'pattern':r'^\s*'+pattern+r'\s+0*'+str(int(m[2]))+r'/'+m[3]+r'(?=\s|[,.;:]|$)'}

def context_score(ref,item):
 words={stem(w) for w in tokens(item.get('titulo') or '')};org={stem(w) for w in tokens(str(item.get('organismo') or ''))}
 terms={stem(w) for w in ref['terminos']};matched=sorted(t for t in terms if t in words or t in org)
 return len(matched),matched,len(terms)

def classify(ref,item):
 title=norm(item.get('titulo') or '')
 if re.search(ref['pattern'],title):return 'disposicion_exacta',None
 # Relación solo si el título conecta expresamente el verbo con esa referencia.
 target=ref['pattern'].removeprefix(r'^\s*')
 rel=re.search(r'\b(modifica(?:cion)?|desarrolla|deroga|correccion de errores)\b[^.;:]{0,75}\b'+target+r'(?=\s|[,.;:]|$)',title)
 if rel:return 'disposicion_relacionada',{'declaracion':rel[0],'fuente':'titulo_oficial','alcance':'Relación expresada en título; no se determinan automáticamente efectos jurídicos.'}
 return 'mencion_documental',None

def verify_dogv(core,item,ref,lang):
 docid=str(item.get('id',''))
 if not re.fullmatch(r'\d{1,9}',docid):raise core.JuridicoError('IDENTIDAD_NO_VERIFICADA','Falta ID oficial verificable en candidato.')
 r=core.HTTP.get(f'{core.DOGV}/disposicion/{docid}?lang={core.language(lang)}');data=core.json_response(r)
 if not isinstance(data,dict) or str(data.get('id'))!=docid or data.get('desindexar'):raise core.JuridicoError('IDENTIDAD_NO_VERIFICADA','Ficha ausente, desindexada o con ID diferente.')
 signature=data.get('codigoInsercion','');date=data.get('fechaPublicacion','');edition=str(data.get('numeroDogv',''))
 if not re.fullmatch(r'\d{4}/\d{1,8}',signature) or not edition.isdigit() or not re.search(ref['pattern'],norm(data.get('titulo') or '')):raise core.JuridicoError('IDENTIDAD_NO_VERIFICADA','Título, signatura o edición de la ficha no verificables.')
 core.valid_date(date)
 index_date=item.get('fechaPublicacion')
 if index_date and re.fullmatch(r'\d{2}/\d{2}/\d{4}',index_date):
  index_date=core.datetime.strptime(index_date,'%d/%m/%Y').date().isoformat()
 if signature!=item.get('codigoInsercion') or (index_date and index_date!=date):raise core.JuridicoError('REFERENCIA_NO_COINCIDE','Ficha e índice no coinciden en signatura o fecha.')
 return dict(item,titulo=data['titulo'],codigoInsercion=signature,fechaPublicacion=date,numeroDogv=data['numeroDogv'],organismo=data.get('organismo'),identificacion_verificada=True,verificacion={'url_api':r['url'],'consultado_en':r['consultado_en'],'sha256_fuente':core.hashlib.sha256(r['body']).hexdigest(),'criterio':'Título tipo/número/año, ID, signatura, fecha y edición cotejados con ficha oficial.'})

def dogv_locate(core,text,idioma,inicio,limite,desde,hasta,vigentes,max_paginas=5,max_alternativas=2,max_segundos=35,max_candidatos=50):
 for v,n,lo,hi in [(max_paginas,'max_paginas',1,5),(max_alternativas,'max_alternativas',0,3),(max_segundos,'max_segundos',1,60),(max_candidatos,'max_candidatos',1,50)]:core.valid_int(v,n,lo,hi)
 ref=reference(core,text);budget=Budget(core,max_segundos);token=SEARCH_BUDGET.set(budget);pages=[];items={};continuations=[];last=None;examined=0;cause=None;source_error=None
 base={'consulta':ref['consulta_base'],'desde':desde,'hasta':hasta,'nombre':'referencia_sin_restriccion_anual'}
 strategies=[base]
 # Año es una vía auxiliar, nunca sustituye ni agota el alcance temporal solicitado.
 if not desde and not hasta:
  strategies.append(dict(base,desde=str(ref['ano'])+'-01-01',hasta=str(ref['ano'])+'-12-31',nombre='referencia_en_ano_numeracion'))
 if not vigentes:strategies.append(dict(base,nombre='referencia_cruzada_boe_sumario'))
 strategies=strategies[:1+max_alternativas]
 verified=[];selected=[];ambiguity=False
 try:
  for si,strategy in enumerate(strategies):
   offset=inicio if si==0 else 0;scope_done=False
   # Primera ronda una página por vía; las alternativas acotan el ruido antes de profundizar.
   quota=1 if si<len(strategies)-1 else max_paginas-len(pages)
   for _ in range(max(0,quota)):
    if len(pages)>=max_paginas or examined>=max_candidatos:cause='Limite de exploracion alcanzado';break
    budget.remaining()
    if strategy['nombre']=='referencia_cruzada_boe_sumario':
     result=boe_dogv_anchor(core,ref,idioma,desde,hasta,pages,max_paginas,max_candidatos-examined)
     if result is None:break
    else:result=core.dogv_buscar(strategy['consulta'],idioma=idioma,inicio=offset,limite=min(10,max_candidatos-examined),modo='global',desde=strategy['desde'],hasta=strategy['hasta'],solo_titulo=True,solo_vigentes=vigentes)
    last=result;data=result['datos'];rows=data['publicaciones'];pages.append({'estrategia':strategy['nombre'],'texto':strategy['consulta'],'inicio':offset,'filtros_aplicados':data['filtros'],'candidatos':len(rows),'total_fuente':data['total'],'url_api':result['url_api'],'sha256_fuente':result['sha256_fuente'],'cache':result['cache']});examined+=len(rows)+data.get('candidatos_auxiliares',0)
    for i,item in enumerate(rows):
     key=item.get('codigoInsercion') or str(item.get('id'));position={'estrategia':strategy['nombre'],'posicion_en_fuente':offset+i}
     if key in items:items[key]['apariciones_fuente'].append(position);continue
     kind,relation=classify(ref,item);score,hits,total=context_score(ref,item)
     items[key]=dict(item,clasificacion=kind,relacion_acreditada=relation,coincidencia_exacta=kind=='disposicion_exacta',identificacion_verificada=False,apariciones_fuente=[position],posicion_en_fuente=offset+i,indicios_contexto={'coincidencias':hits,'total_terminos':total,'puntuacion':score})
    scope_done=data['siguiente_inicio'] is None
    nextpos=data['siguiente_inicio'];offset=nextpos if nextpos is not None else offset+len(rows)
    # Verifica como máximo cuatro fichas exactas por llamada.
    exact=[x for x in items.values() if x['coincidencia_exacta']]
    for item in sorted(exact,key=lambda x:-x['indicios_contexto']['puntuacion']):
     if item.get('verificacion_intentada'):continue
     if sum(bool(x.get('verificacion_intentada')) for x in items.values())>=4:cause='Limite de verificacion de fichas alcanzado';break
     item['verificacion_intentada']=True
     try:
      item.update(core.dogv_search_metadata(item,ref,idioma))
      score,hits,total=context_score(ref,item);item['indicios_contexto']={'coincidencias':hits,'total_terminos':total,'puntuacion':score}
     except core.JuridicoError as exc:
      if exc.codigo=='PRESUPUESTO_AGOTADO' or exc.status in (401,403,429):raise
      item['error_verificacion']=exc.result()['error']
    verified=[x for x in items.values() if x['coincidencia_exacta'] and x['identificacion_verificada']]
    verified.sort(key=lambda x:-x['indicios_contexto']['puntuacion']);selected=verified[:]
    if ref['terminos'] and verified:
     best=verified[0]['indicios_contexto'];leaders=[x for x in verified if x['indicios_contexto']['puntuacion']==best['puntuacion']]
     if best['puntuacion']>0 and best['puntuacion']==best['total_terminos'] and len(leaders)==1:selected=leaders
     else:selected=verified
    ambiguity=len(selected)>1
    if nextpos is not None:continuations.append(dict(strategy,inicio=nextpos))
    # Orden/resolución sin contexto requieren reconocer la ambigüedad, no escoger el primer resultado.
    if selected and ((ref['terminos'] and len(selected)==1 and selected[0]['indicios_contexto']['puntuacion']==selected[0]['indicios_contexto']['total_terminos']) or (scope_done and (len(verified)>1 or ref['tipo'] not in ('orden','resolucion')))):
     cause='Coincidencias verificadas; detencion anticipada sin afirmar exhaustividad global';break
    if scope_done:break
   if selected and (len(selected)>1 or (ref['terminos'] and len(selected)==1 and selected[0]['indicios_contexto']['puntuacion']==selected[0]['indicios_contexto']['total_terminos']) or (not ref['terminos'] and ref['tipo'] not in ('orden','resolucion'))):break
   if cause and ('Limite' in cause):break
  # Completo solo si la primera vía (sin filtro anual inferido) terminó desde cero.
  basepages=[p for p in pages if p['estrategia']==base['nombre']];base_exhausted=bool(basepages) and inicio==0 and basepages[-1]['inicio']+basepages[-1]['candidatos']>=basepages[-1]['total_fuente']
 except core.JuridicoError as exc:
  if exc.codigo=='PRESUPUESTO_AGOTADO':cause='Tiempo maximo de exploracion alcanzado'
  else:source_error=exc.result()['error'];cause='Error de acceso o formato de la fuente; exploracion interrumpida'
  base_exhausted=False
  if last is None:raise
 finally:SEARCH_BUDGET.reset(token)
 if last is None:raise core.JuridicoError('PRESUPUESTO_AGOTADO','No se pudo consultar una página dentro del presupuesto.')
 examined=sum(p['candidatos'] for p in pages)
 allitems=list(items.values());ranked=sorted(allitems,key=lambda x:({'disposicion_exacta':0,'disposicion_relacionada':2,'mencion_documental':3}[x['clasificacion']],-x['indicios_contexto']['puntuacion']))
 confirmed=selected or verified
 # Contexto no satisfecho no se disfraza de selección inequívoca.
 context_ok=not ref['terminos'] or (len(confirmed)==1 and confirmed[0]['indicios_contexto']['puntuacion']==confirmed[0]['indicios_contexto']['total_terminos'])
 state='ambigua' if len(confirmed)>1 else 'localizada' if len(confirmed)==1 and context_ok else 'candidata_pendiente' if confirmed else 'candidata_pendiente' if any(x['coincidencia_exacta'] for x in allitems) else 'no_encontrada_en_alcance' if base_exhausted else 'no_confirmada'
 complete=base_exhausted and not (not confirmed and any(p['estrategia']=='referencia_cruzada_boe_titulo' for p in pages)) and not source_error and len(confirmed)<=limite and all(x.get('identificacion_verificada') for x in allitems if x['coincidencia_exacta'])
 if state=='no_encontrada_en_alcance' and not complete:state='no_confirmada'
 if not cause:cause='Alcance declarado recorrido' if complete else 'Limite de exploracion alcanzado'
 public=[dict(x,seleccionada_por_contexto=context_ok and len(confirmed)==1) for x in confirmed[:limite]]
 nextbase=next((x['inicio'] for x in continuations if x['nombre']==base['nombre']),None)
 data={'modo':'localizacion_disposicion','consulta':text,'alcance':'Exploración puntual acotada de títulos oficiales; ficha verificada por candidato. No es inventario completo del DOGV.', 'localizacion':state,'identificacion_verificada':bool(public) and all(x['identificacion_verificada'] for x in public),'coincidencia_exacta':bool(public),'ambiguedad':len(confirmed)>1,'publicaciones':public,'otras_coincidencias_exactas':[x for x in verified if x not in confirmed], 'candidatos_fuente':allitems,'candidatos_encontrados':[{k:x[k] for k in ['id','codigoInsercion','clasificacion','identificacion_verificada']} for x in allitems],'resultados_clasificados':ranked[:limite],'disposiciones_relacionadas':[x for x in allitems if x['clasificacion']=='disposicion_relacionada'],'total':len(confirmed) if complete else None,'total_candidatos_fuente':basepages[0]['total_fuente'] if 'basepages' in locals() and basepages else None,'coincidencias_exactas_en_pagina':len(verified),'criterio_identificacion':{k:v for k,v in ref.items() if k!='pattern'},'estrategia_busqueda':[p['estrategia'] for p in pages],'paginas_consultadas':len(pages),'candidatos_examinados':examined,'candidatos_unicos':len(items),'traza':pages,'filtros_aplicados':[p['filtros_aplicados'] for p in pages],'busqueda_agotada':complete,'busqueda_candidatos_agotada':base_exhausted,'recuperacion_completa':complete,'truncado_por_limite':len(confirmed)>limite,'siguiente_inicio':nextbase,'continuaciones':continuations,'motivo':cause,'presupuesto':{'max_paginas':max_paginas,'max_alternativas':max_alternativas,'max_segundos':max_segundos,'max_candidatos':max_candidatos,'max_fichas':4},'metricas':budget.metrics(),'limitaciones':['Un filtro auxiliar por año no descarta publicaciones de otro año.','La clasificación contextual es determinista y no acredita vigencia ni efectos jurídicos.','La ausencia dentro de presupuesto no acredita inexistencia fuera del alcance.']}
 if source_error:
  data['error_fuente']=source_error;data['recuperacion_completa']=False
  if not public:data['localizacion']='error_fuente'
 result=core.envelope('DOGV',{'url':last['url_api'],'body':b'','consultado_en':last['consultado_en'],'cache':False},last['url_oficial'],data,'LOCALIZACIÓN ACOTADA: comprobar localizacion, ambiguedad, verificacion de ficha y traza. La huella de cada fuente está en traza/verificacion; no hay una descarga documental única agregada.')

 result['sha256_fuente']=None
 result['nota_procedencia']='Resultado agregado: huellas oficiales individuales en traza y verificacion de cada ficha.'
 return result

def boe_dogv_anchor(core,ref,idioma,desde,hasta,pages,max_pages,remaining_candidates):
 """BOE solo descubre fecha/edición; la identidad final se verifica siempre en DOGV."""
 if len(pages)+3>max_pages:return None
 query=' '.join(ref['terminos']) if ref['terminos'] else ref['consulta_base']
 b=core.boe_buscar(query[:200],limite=min(25,remaining_candidates),modo='web',solo_titulo=True)
 bd=b['datos'];rows=bd.get('data',[])
 pages.append({'estrategia':'referencia_cruzada_boe_titulo','texto':query,'inicio':0,'candidatos':len(rows),'total_fuente':bd.get('total_fuente'),'url_api':b['url_api'],'sha256_fuente':b['sha256_fuente'],'cache':b['cache'],'filtros_aplicados':bd.get('filtros'),'alcance':'BOE solo como referencia auxiliar de publicación DOGV; no se sustituye la fuente final.'})
 matches=[x for x in rows if re.search(ref['pattern'],norm(x.get('titulo',''))) and 'valenciana' in norm(x.get('metadatos_publicacion','')+' '+x.get('titulo','')) and x.get('recuperable_api')]
 if len(matches)!=1:return None
 candidate=matches[0];ident=core.boe_id(candidate['identificador']);u='https://www.boe.es/buscar/act.php?id='+ident
 r=core.HTTP.get(u,'text/html');source=r['body'].decode('utf-8','strict');h=re.search(r'<h3\b[^>]*>(.*?)</h3>',source,re.S)
 if not h or not re.search(ref['pattern'],norm(core.plain_html(h[1]))):raise core.JuridicoError('IDENTIDAD_NO_VERIFICADA','La cabecera BOE no coincide con la referencia solicitada.')
 pub=re.search(r'<dt>\s*Publicado en:\s*</dt>\s*<dd>(.*?)</dd>',source[:120000],re.S)
 meta=core.plain_html(pub[1]) if pub else ''
 found=re.findall(r'«(?:DOGV|DOCV)»\s*núm\.\s*(\d+),\s*de\s*(\d{2})/(\d{2})/(\d{4})',meta)
 pages.append({'estrategia':'metadatos_publicacion_boe','texto':ident,'inicio':0,'candidatos':0,'total_fuente':1,'url_api':u,'sha256_fuente':core.hashlib.sha256(r['body']).hexdigest(),'cache':r['cache'],'filtros_aplicados':{'cabecera':'Publicado en: DOGV/DOCV'}})
 if len(found)!=1:return None
 edition,day,month,year=found[0];date=f'{year}-{month}-{day}';core.valid_date(date)
 if (desde and date<desde) or (hasta and date>hasta):return None
 sr=core.HTTP.get(core.DOGV+'/dogv?'+core.urlencode({'date':date,'lang':core.language(idioma)}));data=core.json_response(sr)
 if not isinstance(data,dict) or not isinstance(data.get('disposiciones'),list) or str(data.get('cabecera',{}).get('numeroDogv'))!=edition:raise core.JuridicoError('EDICION_NO_VERIFICADA','El sumario DOGV no coincide con la edición publicada en metadatos BOE.')
 expected=core.datetime.strptime(date,'%Y-%m-%d').strftime('%d/%m/%Y')
 if any(x.get('fechaPublicacion')!=expected for x in data['disposiciones']):raise core.JuridicoError('EDICION_NO_VERIFICADA','El sumario contiene publicaciones de otra fecha.')
 limit=max(0,remaining_candidates-len(rows));selected=data['disposiciones'][:limit]
 items=[dict(core.dogv_item(x),fechaPublicacion=date) for x in selected]
 return core.envelope('DOGV',sr,'https://dogv.gva.es/es/',{'publicaciones':items,'siguiente_inicio':len(items) if len(items)<len(data['disposiciones']) else None,'total':len(data['disposiciones']),'filtros':{'fecha':date,'numeroDogv':edition,'idioma':idioma,'derivados_de':'metadatos oficiales BOE, cotejados con DOGV'},'candidatos_auxiliares':len(rows)},'Referencia cruzada oficial; no se atribuye orden editorial al sumario.')

TS_STOP=STOP|set('obligacion entregar facilitar proporcionar necesito busca buscar localiza localizar encontrar dime explica supuesto relativa relativo'.split())
def ts_terms(s):return list(dict.fromkeys(w for w in re.findall(r'[a-z]+',norm(s)) if len(w)>2 and w not in TS_STOP))
def ts_phrases(query):
 # Construcciones nominales conservan preposiciones; no contienen ROJ de referencia predefinidos.
 text=norm(query)
 phrases=re.findall(r'\b((?:plazo|carga|prueba|derecho|responsabilidad|intereses|contrato|recurso)\s+(?:de|del|de la|de las|de los)\s+[a-z]+)',text)
 if phrases:return list(dict.fromkeys(phrases))[:3]
 words=ts_terms(query)
 if len(words)>=2:return [' '.join(words[:2])]
 return words

def ts_priority(query,item):
 summary=norm(item.get('resumen_fuente',''));words={stem(w) for w in ts_terms(summary)};requested={stem(w) for w in ts_terms(query)};hits=sorted(t for t in requested if t in words)
 phrases=[p for p in ts_phrases(query) if p in summary]
 # Se documentan indicios en el resumen, no una conclusión sobre doctrina o aplicabilidad.
 score=len(hits)*3+len(phrases)*5
 return score,{'terminos_en_resumen':hits,'expresiones_en_resumen':phrases,'puntuacion':score,'texto_resolucion_examinado':False,'conclusion':'Candidata; examinar PDF y cuestión resuelta antes de atribuir doctrina.'}

def ts_search(core,consulta,limite,inicio,sala,desde,hasta,ecli,roj,ponente,recurso,resolucion,orden='relevancia',max_consultas=2,max_segundos=30):
 if orden not in ('relevancia','cronologico'):raise core.JuridicoError('ORDEN_INVALIDO','orden debe ser relevancia o cronologico.')
 core.valid_int(max_consultas,'max_consultas',1,2);core.valid_int(max_segundos,'max_segundos',1,60)
 consulta=core.valid_text(consulta,'consulta',200,empty=True)
 core.valid_int(limite,'limite',1,10);core.valid_int(inicio,'inicio',0,199)
 original=consulta
 if not roj and not ecli:
  match=re.fullmatch(r'\s*(?:ROJ:\s*)?((?:STS|ATS|AATS)\s+\d+/\d{4})\s*',consulta,re.I)
  em=re.fullmatch(r'\s*(ECLI:ES:TS:\d{4}:[A-Z0-9.]+)\s*',consulta,re.I)
  if match:roj=match[1].upper();consulta=''
  elif em:ecli=em[1].upper();consulta=''
 if not any((consulta,sala,desde,hasta,ecli,roj,ponente,recurso,resolucion)):
  return core._ts_buscar_page(consulta,limite,inicio,sala,desde,hasta,ecli,roj,ponente,recurso,resolucion)
 budget=Budget(core,max_segundos);token=SEARCH_BUDGET.set(budget);responses=[];err=None
 try:
  first=core._ts_buscar_page(consulta,10 if consulta and orden=='relevancia' else limite,inicio,sala,desde,hasta,ecli,roj,ponente,recurso,resolucion);responses.append((consulta,first))
  total=first['datos']['total_fuente']
  if consulta and not (roj or ecli) and orden=='relevancia' and inicio==0 and max_consultas>1 and (total==0 or total>10):
   phrases=ts_phrases(consulta);alternative='"'+phrases[0]+'"' if phrases else ''
   if alternative and norm(alternative)!=norm(consulta):
    try:
     budget.remaining();second=core._ts_buscar_page(alternative,10,0,sala,desde,hasta,ecli,roj,ponente,recurso,resolucion);responses.append((alternative,second))
    except core.JuridicoError as exc:
     if not first['datos']['resoluciones']:
      raise
     err=exc.result()['error']
 finally:SEARCH_BUDGET.reset(token)
 first=responses[0][1];d=first['datos'];items={};trace=[]
 for strategy,(q,r) in enumerate(responses):
  rd=r['datos'];trace.append({'consulta':q,'filtros_aplicados':rd['filtros'],'total_fuente':rd['total_fuente'],'candidatos':len(rd['resoluciones']),'url_api':r['url_api'],'sha256_fuente':r['sha256_fuente']})
  for position,item in enumerate(rd['resoluciones']):
   key=item['ecli'];appearance={'consulta':q,'posicion_en_fuente':inicio+position if strategy==0 else position}
   if key in items:items[key]['apariciones_fuente'].append(appearance);continue
   score,evidence=ts_priority(original,item);kind='sentencia' if item['roj'].startswith('STS ') else 'auto' if item['roj'].startswith(('ATS ','AATS ')) else 'otra'
   items[key]=dict(item,tipo_resolucion=kind,criterio_tipo='Prefijo ROJ del índice; confirmar cabecera del PDF.',estado_relevancia='candidata_no_examinada',indicios_relevancia=evidence,apariciones_fuente=[appearance],posicion_en_fuente=appearance['posicion_en_fuente'])
 found=list(items.values())
 if consulta and orden=='relevancia':found.sort(key=lambda x:-x['indicios_relevancia']['puntuacion'])
 ranked=bool(consulta) and not (roj or ecli) and orden=='relevancia'
 selected=found[:limite];d['resoluciones']=selected
 d.update({'consulta_original':original,'orden_solicitado':orden,'estrategia_busqueda':'resumen_oficial_y_expresiones_juridicas' if ranked else 'referencia_exacta_o_cronologia_oficial','criterio_identificacion':'ROJ/ECLI verificados en metadatos del índice; cabecera se coteja en ts_resolucion.','identificacion_verificada':False,'resoluciones_candidatas':[{k:v for k,v in dict(x,resumen_fuente=x.get('resumen_fuente','')[:900],resumen_candidato_truncado=len(x.get('resumen_fuente',''))>900).items() if k!='metadatos'} for x in found],'candidatos_examinados':sum(x['candidatos'] for x in trace),'paginas_consultadas':len(trace),'consultas_efectuadas':[x['consulta'] for x in trace],'traza_busqueda':trace,'recuperacion_completa':len(responses)==1 and inicio==0 and total<=len(selected) and err is None,'busqueda_agotada':len(responses)==1 and inicio==0 and total<=len(found),'metricas':budget.metrics(),'presupuesto':{'max_consultas':max_consultas,'max_candidatos':20,'max_segundos':max_segundos},'limitaciones':['Prioridad basada en resumen oficial y expresiones; no equivale a doctrina pertinente ni aplicable.','Solo páginas recibidas; no descarga ni lee PDF automáticamente.','No se infiere sala competente si el usuario no la indica.']})
 if ranked:
  d['siguiente_inicio']=inicio+trace[0]['candidatos'] if inicio+trace[0]['candidatos']<min(total,200) else None
  d['continuaciones']=[{'consulta':q,'inicio':(inicio if i==0 else 0)+trace[i]['candidatos'],'orden':'relevancia','filtros':r['datos']['filtros']} for i,(q,r) in enumerate(responses) if (inicio if i==0 else 0)+trace[i]['candidatos']<min(trace[i]['total_fuente'],200)]
  d['nota_paginacion']='Cada continuación pertenece a su consulta fuente; las posiciones no son posiciones del ranking agregado. Las candidatas no mostradas en resoluciones están en resoluciones_candidatas.'
 if err:
  d['error_estrategia_adicional']=err
  d['recuperacion_completa']=False
  d['busqueda_agotada']=False
  first['advertencia']+=' BÚSQUEDA PARCIAL: falló una consulta adicional; se conservan las candidatas de la consulta inicial.'
  if err['codigo']=='ACCESO_INTERACTIVO_REQUERIDO' or err.get('http_status')==429:
   d['siguiente_inicio']=None
   d['continuaciones']=[]
   first['advertencia']+=' Detener las consultas automatizadas a CENDOJ ante esta restricción.'
 if len(responses)>1:
  d['total_fuente']=None
  d['total_fuente_consulta_inicial']=total
  d['nota_total_fuente']='Total agregado desconocido: las consultas pueden solaparse. Totales individuales en traza_busqueda; seguir continuaciones por consulta.'
  first['sha256_fuente']=None;first['nota_procedencia']='Agregado: huellas de páginas oficiales en traza_busqueda.'
 first['advertencia']+=' CANDIDATAS: el resumen no acredita doctrina aplicable; examinar PDF antes de responder el fondo jurídico.'
 return first
