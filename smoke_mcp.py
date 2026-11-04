"""Regresión puntual DOGV por protocolo MCP, con guardia BOE. Sin corpus ni llamadas CENDOJ."""
import asyncio,hashlib,json,sys,time
from pathlib import Path
from fastmcp import Client
from fastmcp.client.transports import StdioTransport

async def main():
 root=Path(__file__).resolve().parent
 report={'passed':False,'tests':[],'alcance':'DOGV: casos puntuales de versiones, originales, sumarios y búsqueda; guardia BOE. No compara modelos ni recorre resultados en lote.'}
 target=root/'smoke-results.json';target.write_text(json.dumps(report))
 async with Client(StdioTransport(command=sys.executable,args=[str(root/'server.py')],cwd=str(root))) as client:
  defs=await client.list_tools();report['tools']=[t.name for t in defs];assert len(defs)==14
  async def call(case,name,args,check):
   t=time.monotonic();r=await client.call_tool(name,args,raise_on_error=False);d=r.structured_content or json.loads(r.content[0].text)
   entry={'case':case,'tool':name,'args':args,'latency_ms':round((time.monotonic()-t)*1000),'ok':d.get('ok'),'is_error':r.is_error,'response':d}
   try:
    assert r.is_error is (not d.get('ok',False)), 'Error de protocolo no coherente'
    assert check(d), 'Criterio del caso no satisfecho'
    entry['passed']=True
   except (AssertionError,KeyError,TypeError,IndexError) as exc:entry.update(passed=False,failure=str(exc))
   report['tests'].append(entry);target.write_text(json.dumps(report,ensure_ascii=False,indent=2))
   print(json.dumps({k:v for k,v in entry.items() if k!='response'},ensure_ascii=False),flush=True)
   return d
  state=await call('S00','juridico_estado',{},lambda x:x['ok'] and x['version']=='1.1.5' and x['uid_proceso']!=0);report['version']=state.get('version')
  await call('BOE-guardia','boe_bloque',{'identificador':'BOE-A-2015-10565','id_bloque':'a32'},lambda x:x['ok'] and len(x['datos']['texto'])>200)
  first=await call('D-global-0','dogv_buscar',{'texto':'Decreto 104/2018','limite':2},lambda x:x['ok'] and bool(x['datos']['publicaciones']))
  await call('D-global-2','dogv_buscar',{'texto':'Decreto 104/2018','limite':2,'inicio':2},lambda x:x['ok'] and x['datos']['total']==first['datos']['total'] and {p['id'] for p in x['datos']['publicaciones']}.isdisjoint({p['id'] for p in first['datos']['publicaciones']}))
  await call('D-exacta','dogv_buscar',{'texto':'Decreto 104/2018','modo':'disposicion','limite':3},lambda x:x['ok'] and [p['codigoInsercion'] for p in x['datos']['publicaciones']]==['2018/7822'] and x['datos']['recuperacion_completa'] and bool(x['datos']['candidatos_fuente']))
  await call('D-portal-version','dogv_publicacion',{'identificador':'2018/7822','max_caracteres':1000},lambda x:x['ok'] and x['datos']['naturaleza_texto']=='texto_consolidado_html' and x['datos']['fecha_publicacion_original']=='2018-08-07' and x['datos']['fecha_publicacion_texto']=='2022-08-16' and x['datos']['version_texto']['fecha_inicio_declarada']=='2022-08-17' and x['datos']['vigencia_juridica_automatica'] is None)
  await call('D-original-pdf','dogv_publicacion',{'identificador':'2018/7822','tipo_texto':'original','max_caracteres':1000},lambda x:x['ok'] and x['datos']['naturaleza_texto']=='publicacion_original_pdf' and x['datos']['fecha_publicacion_texto']=='2018-08-07' and x['datos']['version'] is None and x['datos']['anexos']['encabezado_detectado'] and bool(x['datos']['documento_original']['sha256_fuente']))
  for case,date,version in [('D-hist-2020','2020-01-01',1),('D-hist-2021','2021-07-01',2)]:
   await call(case,'dogv_publicacion',{'identificador':'2018/7822','fecha':date,'max_caracteres':1000},lambda x,v=version:x['ok'] and x['datos']['version']==v and x['datos']['vigencia_juridica_automatica'] is None)
  await call('D-antes-intervalo','dogv_publicacion',{'identificador':'2018/7822','fecha':'2018-08-07'},lambda x:not x['ok'] and x['error']['codigo']=='SIN_VERSION_EN_FECHA')
  await call('D-unificada-fecha','juridico_documento',{'fuente':'DOGV','identificador':'2018/7822','fecha':'2021-07-01','max_caracteres':500},lambda x:x['ok'] and x['datos']['version']==2)
  codes=[]
  for name,start in [('D-10483-a',0),('D-10483-b',40)]:
   d=await call(name,'dogv_sumario',{'fecha':'2026-10-30','inicio':start,'limite':40},lambda x:x['ok'] and x['datos']['orden_verificado'] and x['datos']['total']==53)
   codes += [p['codigoInsercion'] for p in d.get('datos',{}).get('publicaciones',[])]
  expected=json.loads((root/'tests/dogv-10483-order.json').read_text());report['orden_10483']={'coincidencia_completa':codes==expected,'posiciones_correctas':sum(a==b for a,b in zip(codes,expected)),'total':53}
  for case,date,total in [('D-sumario-8338','2018-07-13',39),('D-sumario-8356','2018-08-07',48)]:
   await call(case,'dogv_sumario',{'fecha':date,'limite':40},lambda x,n=total:x['ok'] and x['datos']['total']==n and x['datos']['orden_verificado'] is False and x['datos']['recuperacion_completa'] is False and 'ORDEN NO VERIFICADO' in x['advertencia'])
  await call('D-historico-estricto','dogv_sumario',{'fecha':'2018-08-07','exigir_orden':True},lambda x:not x['ok'] and x['error']['codigo']=='ORDEN_NO_VERIFICADO')
  await call('D-historico-pagina2','dogv_sumario',{'fecha':'2018-08-07','inicio':40,'limite':40},lambda x:x['ok'] and len(x['datos']['publicaciones'])==8 and x['datos']['siguiente_inicio'] is None and x['datos']['orden_verificado'] is False)
  await call('D-CVE-html','dogv_publicacion',{'identificador':'DOGV-C-2026-33531','max_caracteres':1000},lambda x:x['ok'] and x['datos']['codigoInsercion']=='2026/33531' and x['datos']['naturaleza_texto']=='texto_html_no_consolidado_de_consulta' and bool(x['datos']['documento_original']['url_oficial']))
  await call('D-original-compatible','dogv_publicacion',{'identificador':'original:2018/7822','max_caracteres':500},lambda x:x['ok'] and x['datos']['naturaleza_texto']=='publicacion_original_pdf' and x['datos']['codigoInsercion']=='2018/7822' and 'selector_compatibilidad' in x['datos'])
  await call('D-CVE-original','dogv_publicacion',{'identificador':'DOGV-C-2026-33531','tipo_texto':'original','max_caracteres':1000},lambda x:x['ok'] and x['datos']['naturaleza_texto']=='publicacion_original_pdf' and bool(x['datos']['documento_original']['sha256_fuente']))
  for ident,lang in [('original:2018/7822','es'),('original:2018/7822','va'),('original:2019/4442','es'),('original:2019/4442','va'),('original:2019/4442','ambos')]:
   await call('PDF-'+ident+'-'+lang,'dogv_publicacion',{'identificador':ident,'idioma':lang,'max_caracteres':1000},lambda x,l=lang:x['ok'] and x['datos']['idioma_solicitado']==l and not x['datos']['paginas_omitidas'] and bool(x['datos']['paginas_fragmento']) and x['datos']['extraccion_verificada'] is False and x['datos']['documento_recuperado'] and x['datos']['texto_extraido'])
 report['passed']=all(t['passed'] for t in report['tests']) and report['orden_10483']['coincidencia_completa']
 report['tested_hashes']={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('server.py','juridico.py','pdf_extract.py','pdf_geometry.py','smoke_mcp.py')}
 target.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'passed':report['passed'],'orden':report['orden_10483']}),flush=True)
 if not report['passed']:sys.exit(1)
if __name__=='__main__':asyncio.run(main())
