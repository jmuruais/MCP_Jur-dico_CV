"""Extracción geométrica acotada. Sin OCR, red ni modelos. Coordenadas en puntos PDF."""
import re
import time
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


def consistent_single_column(lines, width, language, scores):
    """Confirma prosa de ancho amplio con evidencia de idioma distribuida."""
    if language is None or max(scores.values()) < 4 * max(1, min(scores.values())):
        return False
    ordered = sorted(lines, key=lambda line: (line['bbox'][1], line['bbox'][0]))
    if sum(line['bbox'][2] - line['bbox'][0] >= width * .55 for line in ordered) < 4:
        return False
    if len(ordered) < 24:
        return False
    third = len(ordered) // 3
    return all(
        identify_language(' '.join(line['text'] for line in section))[0] == language
        for section in (ordered[:third], ordered[third:2*third], ordered[2*third:])
    )


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


def extract(path, requested='es', selection=None):
    import pymupdf as fitz
    doc=fitz.open(path)
    if selection is None and len(doc)>120:raise ValueError('PDF supera 120 páginas; extracción geométrica no realizada.')
    header = {}
    if selection is not None:
        header = {'cabecera': doc[0].get_text(sort=True)[:12000]}
        if selection[-1] > len(doc):
            return {**header, 'paginas_fuera': True, 'paginas_totales': len(doc)}
    segments=[];pages=[];tables=[];offset=0
    indices = range(len(doc)) if selection is None else [number - 1 for number in selection]
    for index in indices:
        source = doc[index]
        number=index+1;page=source;temporary=None;rotation=0
        before = len(segments), len(tables), offset
        try:
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
                    language,scores=evidence[0]
                    if max(scores.values()) < 10*max(1,min(scores.values())) and (
                        selection is None or not consistent_single_column(parts[0],page.rect.width,language,scores)
                    ):
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
        except (ValueError, RuntimeError):
            if selection is None:
                raise
            del segments[before[0]:]
            del tables[before[1]:]
            offset = before[2]
            pages.append({'pagina_pdf': number, 'estado': 'omitida_error_extraccion', 'fragmentos': [],
                          'idiomas_detectados': []})
        finally:
            if temporary:
                temporary.close()
    omitted=[p['pagina_pdf'] for p in pages if p['estado'].startswith('omitida')]
    text=''.join(s[0] for s in segments)
    return {**header, **({'paginas_solicitadas': selection} if selection is not None else {}), 'texto':text,'paginas':pages,'segmentos':[s[1] for s in segments],'tablas':tables,
        'paginas_totales':len(doc),'paginas_omitidas':omitted,'idioma_solicitado':requested,
        'documento_recuperado':True,'texto_extraido':bool(text),'extraccion_verificada':False,
        'calidad_extraccion':'geometría comprobada automáticamente; sin cotejo íntegro visual o semántico',
        'extraccion_parcial':bool(omitted) or any(not t['tabla_estructura_verificada'] for t in tables),
        'advertencias':['No se aplica OCR. Idioma inferido por evidencia léxica; páginas ambiguas omitidas.','La verificación geométrica no equivale a cotejo íntegro ni a validez jurídica.']}

# Solo se inspecciona el texto de un PDF original; el resultado contiene candidatos.
PDF_SEARCH_PAGES = 160
PDF_SEARCH_RESULTS = 12
PDF_SEARCH_SECONDS = 8


PDF_JOIN_HYPHEN = re.compile(r"(?<=\w)[-\u00ad][ \t]*\n[ \t]*(?=\w)")


def searchable_pdf_text(text):
    text = PDF_JOIN_HYPHEN.sub("", text)
    return norm(text.replace("\u00ad", "").replace("’", "'"))


def pdf_phrase_pattern(phrase):
    return re.compile(r"(?<!\w)" + re.escape(searchable_pdf_text(phrase)) + r"(?!\w)")


def pdf_phrase_span(text, phrase):
    """Locate a normalized match and return offsets in the original text."""
    match = pdf_phrase_pattern(phrase).search(searchable_pdf_text(text))
    if not match:
        return None

    # Count the characters emitted by normalization while tracking their source positions.
    skipped = iter(PDF_JOIN_HYPHEN.finditer(text))
    join = next(skipped, None)
    offsets = []
    space = None
    for index, char in enumerate(text):
        if join and index == join.end():
            join = next(skipped, None)
        if (join and join.start() <= index < join.end()) or char == "\u00ad":
            continue
        if char.isspace():
            if offsets and space is None:
                space = index
            continue
        decomposed = unicodedata.normalize('NFD', char.lower())
        width = sum(not unicodedata.combining(part) for part in decomposed)
        if not width:
            continue
        if space is not None:
            offsets.append(space)
            space = None
        offsets.extend([index] * width)
        if len(offsets) >= match.end():
            break

    start, end = offsets[match.start()], offsets[match.end() - 1] + 1
    while end < len(text) and unicodedata.combining(text[end]):
        end += 1
    return start, end


def locate_pdf_phrase(path, phrase, start):
    import pymupdf

    query = searchable_pdf_text(phrase)
    pattern = pdf_phrase_pattern(phrase)
    deadline = time.monotonic() + PDF_SEARCH_SECONDS
    with pymupdf.open(path) as doc:
        total = len(doc)
        output = {'cabecera': doc[0].get_text(sort=True)[:12000], 'paginas_totales': total}
        if start > total:
            return {**output, 'paginas_fuera': True}
        end = min(total, start + PDF_SEARCH_PAGES - 1)
        matches, omitted = [], []
        last = start - 1
        reason = None
        for number in range(start, end + 1):
            if time.monotonic() >= deadline:
                reason = 'tiempo'
                break
            last = number
            try:
                blocks = [b[4] for b in doc[number - 1].get_text('blocks', flags=0) if b[6] == 0 and b[4].strip()]
            except (ValueError, RuntimeError):
                blocks = []
            if not blocks:
                omitted.append(number)
                continue
            index_page = any(re.search(r"(?im)^\s*(?:índice|índex)\s*$", b) for b in blocks)
            candidates = []
            for block in blocks:
                normalized = searchable_pdf_text(block)
                match = pattern.search(normalized)
                if not match:
                    continue
                first_line = searchable_pdf_text(block.lstrip().splitlines()[0])
                # Es una señal de presentación, no una clasificación jurídica.
                section_label = re.match(
                    r"^(?:articulo|article|anexo|annex|capitulo|capitol|titulo|titol)\s+(?:\d+|[ivxlcdm]+)\b",
                    first_line,
                )
                heading = first_line == query or bool(section_label and pattern.search(first_line))
                dotted_entry = bool(re.search(r"\.{3,}\s*\d+\s*$", block.strip()))
                kind = 'posible_indice' if index_page or dotted_entry else 'posible_encabezado' if heading else 'mencion'
                # La cita literal queda para la extracción geométrica posterior.
                candidates.append((kind, normalized[max(0, match.start() - 45):match.end() + 95]))
            if candidates:
                priority = {'posible_encabezado': 0, 'mencion': 1, 'posible_indice': 2}
                kind, excerpt = min(candidates, key=lambda x: priority[x[0]])
                matches.append({'pagina_pdf': number, 'tipo': kind, 'indicio_normalizado': excerpt})
                if len(matches) == PDF_SEARCH_RESULTS:
                    reason = 'limite_resultados'
                    break
        next_page = last + 1 if last < total else None
        return {
            **output, 'coincidencias': matches, 'pagina_desde': start,
            'pagina_hasta_examinada': last if last >= start else None,
            'paginas_examinadas': last - start + 1,
            'paginas_sin_texto_o_no_legibles': omitted,
            'siguiente_pagina': next_page,
            'motivo_fin': (reason or 'limite_paginas') if next_page else 'fin_pdf',
            'barrido_completo': start == 1 and next_page is None and not omitted,
        }
