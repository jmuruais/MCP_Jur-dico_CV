"""Extracción geométrica acotada. Sin OCR, red ni modelos. Coordenadas en puntos PDF."""
import re
import unicodedata


def norm(s):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', s.lower()) if not unicodedata.combining(c)).split())


def identify_language(text):
    words=re.findall(r"[a-z]+",norm(text))
    vocab={'es':set('los las para con del una por sus este esta estos estas educacion alumnado articulo articulos aprendizaje requiere medidas apoyos disposicion disposiciones seccion orden quienes tiene deben gobierno anexo niveles quien ambito decreto siguiente publicacion segunda dia'.split()),
           'va':set('els les per amb dels una seua seu aquest aquesta aquests aquestes educacio alumnat article articles aprenentatge requerix mesures suports disposicio disposicions seccio ordre govern annex nivells qui ambit decret segona publicacio endema'.split())}
    # «una» compartido se excluye; ninguna posición de columna determina el idioma.
    scores={k:sum(w in (v-{'una'}) for w in words) for k,v in vocab.items()}
    best=max(scores,key=scores.get);other='va' if best=='es' else 'es'
    reliable=scores[best]>=4 and scores[best]-scores[other]>=3 and scores[best]>=1.5*max(1,scores[other])
    return (best if reliable else None),scores


def lines_for(page):
    lines=[]
    for b in page.get_text('dict',flags=0)['blocks']:
        if b['type']!=0:continue
        for l in b['lines']:
            text=''.join(s['text'] for s in l['spans']).strip()
            if text:lines.append({'bbox':list(l['bbox']),'dir':list(l['dir']),'text':text})
    return lines


def split_columns(lines,width):
    """Solo acepta un corredor vacío real y texto a ambos lados. Sin cortar líneas."""
    candidates=[]
    for x in range(int(width*.35),int(width*.65)):
        if not any(l['bbox'][0]<x+3 and l['bbox'][2]>x-3 for l in lines):
            left=[l for l in lines if l['bbox'][2]<=x];right=[l for l in lines if l['bbox'][0]>=x]
            if sum(len(l['text']) for l in left)>120 and sum(len(l['text']) for l in right)>120:
                candidates.append(x)
    if not candidates:return None
    x=min(candidates,key=lambda x:abs(x-width/2))
    return [[l for l in lines if l['bbox'][2]<=x],[l for l in lines if l['bbox'][0]>=x]]


def table_data(page,number,rotation):
    output=[]
    for table in page.find_tables().tables:
        data=table.extract()
        while data and all(re.fullmatch(r'[\s*]*',c or '') for c in data[-1]):
            data.pop()
        entry={'pagina_pdf':number,'bbox_normalizado':list(table.bbox),'rotacion_normalizacion':rotation,
            'tabla_estructura_verificada':False,'criterio':'Detección geométrica; celdas y relaciones no verificadas.',
            'filas_detectadas':table.row_count,'columnas_detectadas':table.col_count}
        # Validación estricta de la matriz del anexo: cabecera explícita y cuatro filas únicas.
        header=next((i for i,row in enumerate(data) if [norm((c or '').strip()) for c in row[1:]] in
                     [['nivel','a quien se dirige','agentes responsables','apoyos','medidas','documentos'],
                      ['nivell','a qui s’adreca','agents responsables','suports','mesures','documents']]),None)
        if header is not None and len(data)==header+5 and all(len(row)==7 for row in data):
            rows=data[header+1:]
            if [row[1] for row in rows]==['I','II','III','IV'] and all(all(c and c.strip() for c in row[1:]) for row in rows):
                cells=[cell for row in table.rows[header+1:header+5] for cell in row.cells[1:]]
                # Cada palabra del rectángulo de las cuatro filas pertenece a una sola celda.
                core=(min(c[0] for c in cells),min(c[1] for c in cells),max(c[2] for c in cells),max(c[3] for c in cells)) if all(cells) else None
                words=page.get_text('words')
                inside=[w for w in words if core and core[0]<(w[0]+w[2])/2<core[2] and core[1]<(w[1]+w[3])/2<core[3]]
                unique=bool(inside) and all(sum(c[0]<=(w[0]+w[2])/2<=c[2] and c[1]<=(w[1]+w[3])/2<=c[3] for c in cells)==1 for w in inside)
                if unique:
                    entry.update({'tabla_estructura_verificada':True,'criterio':'Cabecera explícita, filas I–IV, seis celdas completas por fila y asignación geométrica única de palabras. No dictamen jurídico.',
                        'contexto_tabla':[c for row in data[:header] for c in row if c and c.strip()], 'encabezados':data[header][1:],'filas':[{'nivel':r[1],'celdas':r[1:],'bbox_celdas_normalizado':[list(c) for c in tr.cells[1:]]} for r,tr in zip(rows,table.rows[header+1:header+5])]})
        output.append(entry)
    return output


def extract(path,requested='es'):
    import pymupdf as fitz
    doc=fitz.open(path)
    if len(doc)>120:raise ValueError('PDF supera 120 páginas; extracción geométrica no realizada.')
    segments=[];pages=[];tables=[];offset=0
    for index,source in enumerate(doc):
        number=index+1;page=source;temporary=None;rotation=0
        initial=lines_for(source)
        body=[l for l in initial if l['bbox'][1]>=max(70,source.rect.height*.075)]
        vertical=sum(len(l['text']) for l in body if abs(l['dir'][1])>.9)
        horizontal=sum(len(l['text']) for l in body if l['dir'][0]>.9)
        if vertical>horizontal*3 and vertical>100:
            dirs={round(l['dir'][1]) for l in body if abs(l['dir'][1])>.9}
            if len(dirs)==1:
                rotation=-90 if next(iter(dirs))<0 else 90
                temporary=fitz.open();page=temporary.new_page(width=source.rect.height,height=source.rect.width)
                page.show_pdf_page(page.rect,doc,index,rotate=rotation)
                body=[l for l in lines_for(page) if l['dir'][0]>.9]
        elif any(abs(l['dir'][1])>.2 for l in body):
            body=[]
        pts=table_data(page,number,rotation) if sum(len(d['items']) for d in page.get_drawings())>=8 else []
        # Una tabla detectada pero no validada no se entrega como texto lineal fiable.
        parts=(split_columns(body,page.rect.width) or [body]) if body else None
        info={'pagina_pdf':number,'rotacion_normalizacion':rotation,'columnas':len(parts) if parts else None,
              'idiomas_detectados':[],'estado':'omitida_estructura_o_idioma_incierto','fragmentos':[]}
        if parts:
            evidence=[identify_language(' '.join(l['text'] for l in part)) for part in parts]
            if len(parts)==2 and {v[0] for v in evidence}!={'es','va'}:
                parts=[]
            elif len(parts)==1 and not pts:
                _,scores=evidence[0]
                if max(scores.values()) < 10*max(1,min(scores.values())):
                    parts=[]
            for part in parts:
                text='\n'.join(l['text'] for l in sorted(part,key=lambda l:(round(l['bbox'][1],1),l['bbox'][0])))
                lang,scores=identify_language(text)
                if not lang:continue
                info['idiomas_detectados'].append(lang)
                if requested not in ('ambos',lang):continue
                selected_tables=[]
                for t in pts:
                    t=dict(t,idioma=lang);selected_tables.append(t);tables.append(t)
                if pts:
                    verified=[t for t in selected_tables if t['tabla_estructura_verificada']]
                    text='\n\n'.join('\n'.join(t['contexto_tabla'])+'\n| '+' | '.join(t['encabezados'])+' |\n| '+' | '.join(['---']*len(t['encabezados']))+' |\n'+'\n'.join('| '+' | '.join(c.replace('\n',' ').replace('|','\\|') for c in r['celdas'])+' |' for r in t['filas']) for t in verified)
                    if len(verified)!=len(pts):text+='\n[TABLA CON ESTRUCTURA NO VERIFICADA: consultar PDF oficial, página '+str(number)+']'
                if not text.strip():continue
                heading=f'\n[PDF página {number}; idioma {lang}]\n';chunk=heading+text+'\n'
                seg={'pagina_pdf':number,'idioma':lang,'inicio':offset,'fin':offset+len(chunk),
                     'bbox_normalizado':[min(l['bbox'][0] for l in part),min(l['bbox'][1] for l in part),max(l['bbox'][2] for l in part),max(l['bbox'][3] for l in part)],
                     'criterio':'separación geométrica y detección léxica conservadora','puntuaciones_idioma':scores}
                segments.append((chunk,seg));info['fragmentos'].append(seg);offset+=len(chunk)
            if info['fragmentos']:info['estado']='extraida_geometria'
            elif info['idiomas_detectados']:info['estado']='otro_idioma'
        pages.append(info)
        if temporary:temporary.close()
    omitted=[p['pagina_pdf'] for p in pages if p['estado'].startswith('omitida')]
    text=''.join(s[0] for s in segments)
    return {'texto':text,'paginas':pages,'segmentos':[s[1] for s in segments],'tablas':tables,
        'paginas_totales':len(doc),'paginas_omitidas':omitted,'idioma_solicitado':requested,
        'documento_recuperado':True,'texto_extraido':bool(text),'extraccion_verificada':False,
        'calidad_extraccion':'geometría comprobada automáticamente; sin cotejo íntegro visual o semántico',
        'extraccion_parcial':bool(omitted) or any(not t['tabla_estructura_verificada'] for t in tables),
        'advertencias':['No se aplica OCR. Idioma inferido por evidencia léxica; páginas ambiguas omitidas.','La verificación geométrica no equivale a cotejo íntegro ni a validez jurídica.']}
