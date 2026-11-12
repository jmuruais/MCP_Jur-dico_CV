import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import juridico as j
import pdf_geometry as geometry
import test_dogv_precision as precision


class SearchPDF(unittest.TestCase):
    def test_invalid_arguments_do_not_download(self):
        cases = [
            ('2019/2067', {'buscar_pdf': 'preámbulo'}),
            ('original:2019/2067', {'buscar_pdf': '___'}),
            ('original:2019/2067', {'buscar_pdf': 'preámbulo', 'paginas': [1]}),
            ('original:2019/2067', {'buscar_pdf': 'preámbulo', 'inicio': 1}),
            ('original:2019/2067', {'pagina_desde': 2}),
            ('original:2019/2067#buscar=preámbulo#desde=0', {}),
            ('original:2019/2067#buscar=preámbulo', {'buscar_pdf': 'otro'}),
        ]
        for identifier, args in cases:
            with self.subTest(identifier=identifier,args=args), patch.object(j.HTTP,'get') as get:
                self.assertFalse(j.run_safe(j.dogv_publicacion,identifier,**args)['ok'])
                get.assert_not_called()

    def test_phrase_normalization_and_word_boundaries(self):
        self.assertEqual(geometry.searchable_pdf_text('Situacio-\nnes  de\naprendizáje'), 'situaciones de aprendizaje')
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pdf(folder, ['Índice\nAnexo III. Aprendizaje',
                                         'Texto sin coincidencia: reaprendizaje', 'ANEXO III. APRENDIZAJE'])
            result = geometry.locate_pdf_phrase(path, 'aprendizáje', 1)
        self.assertEqual([(x['pagina_pdf'],x['tipo']) for x in result['coincidencias']],
                         [(1,'posible_indice'),(3,'posible_encabezado')])

    def test_page_and_result_limits_return_physical_continuation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pdf(folder,['Apartado único']*4)
            with patch.object(geometry,'PDF_SEARCH_PAGES',2):
                limited = geometry.locate_pdf_phrase(path,'sin resultados',1)
            with patch.object(geometry,'PDF_SEARCH_RESULTS',1):
                matching = geometry.locate_pdf_phrase(path,'apartado',2)
            invalid = geometry.locate_pdf_phrase(path,'apartado',5)
        self.assertEqual(limited['siguiente_pagina'],3)
        self.assertFalse(limited['barrido_completo'])
        self.assertEqual(matching['siguiente_pagina'],3)
        self.assertEqual(matching['motivo_fin'],'limite_resultados')
        self.assertTrue(invalid['paginas_fuera'])

    def test_omitted_pages_do_not_count_as_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.make_pdf(folder,['Anexo de ejemplo',''])
            result = geometry.locate_pdf_phrase(path,'ausente',1)
        self.assertEqual(result['paginas_sin_texto_o_no_legibles'],[2])
        self.assertIsNone(result['siguiente_pagina'])
        self.assertFalse(result['barrido_completo'])

    def test_search_returns_arguments_that_resume_with_same_settings(self):
        fixture = precision.Precision()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        pdf = precision.response(b'%PDF-test', 'https://dogv.gva.es/datos/2018/08/07/pdf/2018_7822.pdf')
        pdf['bytes_descargados'] = len(pdf['body'])
        matches = {'coincidencias': [{'pagina_pdf': 4, 'tipo': 'posible_indice'},
                                     {'pagina_pdf': 7, 'tipo': 'mencion'}], 'siguiente_pagina': 8}
        end = {'coincidencias': [], 'siguiente_pagina': None}
        with patch.object(j.HTTP, 'get', side_effect=fixture.get), \
             patch.object(j, 'dogv_pdf_pages', side_effect=[(pdf, matches), (pdf, end)]) as worker:
            first = j.dogv_publicacion('original:327983#buscar=Anexo#desde=3#extraer=1',
                                       idioma='ambos', max_caracteres=500)
            data = first['datos']
            self.assertEqual([item['parametros_extraccion']['paginas'] for item in data['coincidencias']],
                             [[4], [7]])
            self.assertEqual(data['coincidencias'][1]['parametros_extraccion'], {
                'identificador': '327983', 'tipo_texto': 'original', 'paginas': [7],
                'idioma': 'ambos', 'max_caracteres': 500,
            })
            last = j.dogv_publicacion(**data['parametros_continuacion'])
        self.assertTrue(last['ok'])
        self.assertNotIn('parametros_continuacion', last['datos'])
        self.assertEqual(worker.call_args.args[2:], ('ambos', None, 'Anexo', 8, True))

    def test_search_keeps_physical_continuation_without_invalid_arguments(self):
        fixture = precision.Precision()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        pdf = precision.response(b'%PDF-test', 'https://dogv.gva.es/datos/2018/08/07/pdf/2018_7822.pdf')
        pdf['bytes_descargados'] = len(pdf['body'])
        for next_page in (5, j.MAX_DOGV_PDF_PAGE + 1):
            with self.subTest(next_page=next_page):
                matches = {'coincidencias': [], 'siguiente_pagina': next_page}
                with patch.object(j.HTTP, 'get', side_effect=fixture.get), \
                     patch.object(j, 'dogv_pdf_pages', return_value=(pdf, matches)):
                    result = j.dogv_publicacion('327983', tipo_texto='original', buscar_pdf='anexo', pagina_desde=5)
                self.assertEqual(result['datos']['siguiente_pagina'], next_page)
                self.assertNotIn('parametros_continuacion', result['datos'])

    @staticmethod
    def make_pdf(folder, texts):
        import pymupdf
        path = Path(folder)/'fixture.pdf'
        with pymupdf.open() as doc:
            for text in texts:
                page = doc.new_page()
                if text:
                    page.insert_text((70,90),text)
            doc.save(path)
        return path
