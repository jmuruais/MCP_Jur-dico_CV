import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import juridico as j
import pdf_geometry


URL = 'https://dogv.gva.es/datos/2019/03/06/pdf/2019_2067.pdf'
FIXTURE = {'codigoInsercion': '2019/2067', 'fechaPublicacion': '2019-03-06', 'numeroDogv': 8500}


class Response(io.BytesIO):
    url = URL

    def __init__(self, content, length=None):
        super().__init__(content)
        self.headers = {} if length is None else {'Content-Length': str(length)}


class Pages(unittest.TestCase):
    def test_only_original_accepts_selection(self):
        for args in ({'paginas':[1]}, {'tipo_texto':'original','paginas':[]},
                     {'tipo_texto':'original','paginas':[2,2]}, {'tipo_texto':'original','paginas':[True]},
                     {'tipo_texto':'original','paginas':[0]}, {'tipo_texto':'original','paginas':list(range(1,8))}):
            with self.subTest(args=args), patch.object(j.HTTP,'get') as get:
                self.assertFalse(j.run_safe(j.dogv_publicacion,'2019/2067',**args)['ok'])
                get.assert_not_called()

    def test_invalid_compatibility_selector_does_not_use_network(self):
        for identifier, args in (
            ('2019/2067#paginas=4', {}),
            ('original:2019/2067#paginas=4', {'paginas':[4]}),
            ('original:2019/2067#paginas=0', {}),
            ('original:2019/2067#paginas=4,4', {}),
            ('original:2019/2067#paginas=4', {'fecha':'2019-03-06'}),
        ):
            with self.subTest(identifier=identifier,args=args), patch.object(j.HTTP,'get') as get:
                self.assertFalse(j.run_safe(j.dogv_publicacion,identifier,**args)['ok'])
                get.assert_not_called()

    def test_stream_is_hashed_and_not_cached(self):
        http = j.OfficialHTTP()
        data = b'%PDF-1234'
        target = io.BytesIO()
        with patch.object(http.opener,'open',return_value=Response(data,len(data))):
            result = http.download_dogv_original(URL,target)
        self.assertEqual(target.getvalue(),data)
        self.assertEqual(result['bytes_descargados'],len(data))
        self.assertEqual(j.source_hash(result),hashlib.sha256(data).hexdigest())
        self.assertFalse(result['body'])
        self.assertFalse(http.cache)

    def test_stream_caps_announced_and_actual_size_and_rejects_truncation(self):
        for content, length, error in [(b'',21,'RESPUESTA_DEMASIADO_GRANDE'),
                                       (b'x'*21,None,'RESPUESTA_DEMASIADO_GRANDE'),
                                       (b'x'*8,12,'PDF_DESCARGA_INCOMPLETA')]:
            http = j.OfficialHTTP()
            with self.subTest(error=error), patch.object(j,'MAX_DOGV_PDF_BYTES',20),                  patch.object(http.opener,'open',return_value=Response(content,length)):
                with self.assertRaises(j.JuridicoError) as caught:
                    http.download_dogv_original(URL,io.BytesIO())
                self.assertEqual(caught.exception.codigo,error)

    def test_pdf_scope_excludes_other_hosts_and_dogv_endpoints(self):
        http = j.OfficialHTTP()
        for url in (j.CENDOJ+'indexAN.jsp',j.DOGV+'/dogv/latest',URL+'?test=1'):
            with self.subTest(url=url), patch.object(http.opener,'open') as op:
                with self.assertRaises(j.JuridicoError):
                    http.download_dogv_original(url,io.BytesIO())
                op.assert_not_called()

    def test_only_requested_pages_and_partial_when_one_fails(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as folder, pymupdf.open() as doc:
            for n in range(3):
                page = doc.new_page()
                page.insert_text((40,110),('Los artículos de la educación para los centros con las medidas. '*2))
            source = Path(folder)/'fixture.pdf'
            doc.save(source)
            original = pdf_geometry.lines_for

            def read(page):
                if page.number == 1:
                    raise RuntimeError('simulated')
                self.assertEqual(page.number,2)
                return original(page)

            with patch.object(pdf_geometry,'lines_for',side_effect=read):
                result = pdf_geometry.extract(source,'es',[2,3])
            self.assertEqual(result['paginas_totales'],3)
            self.assertEqual(result['paginas_omitidas'],[2])
            self.assertEqual([x['pagina_pdf'] for x in result['segmentos']],[3])
            self.assertTrue(result['extraccion_parcial'])
            self.assertTrue(pdf_geometry.extract(source,'es',[4])['paginas_fuera'])

    def test_monolingual_fallback_requires_wide_and_consistent_regions(self):
        valencian = "Els articles de les disposicions per als centres amb alumnat i suports."
        spanish = "Los artículos de las disposiciones para los centros con alumnado y apoyos."
        lines = [{'text':valencian, 'bbox':[80,n*10,520,n*10+8]} for n in range(30)]
        self.assertTrue(pdf_geometry.consistent_single_column(lines,600,'va',{'va':50,'es':9}))
        narrow = [dict(line,bbox=[80,line['bbox'][1],280,line['bbox'][3]]) for line in lines]
        self.assertFalse(pdf_geometry.consistent_single_column(narrow,600,'va',{'va':50,'es':9}))
        mixed = lines[:20] + [dict(line,text=spanish) for line in lines[20:]]
        self.assertFalse(pdf_geometry.consistent_single_column(mixed,600,'va',{'va':50,'es':9}))

    def test_header_requires_complete_signature(self):
        j.verify_dogv_pdf_header('Num. 8500 / 06.03.2019\n[2019/2067]',FIXTURE)
        with self.assertRaises(j.JuridicoError):
            j.verify_dogv_pdf_header('Num. 8500 / 06.03.2019\n[2019/20678]',FIXTURE)
