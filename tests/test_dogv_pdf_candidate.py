import unittest
from pathlib import Path
from unittest.mock import patch

import juridico as j


class CandidateExtraction(unittest.TestCase):
    def test_single_heading_requires_phrase_in_requested_fragment(self):
        for text, expected in [('Jornada lectiva', 'extraido_en_candidato_unico_del_tramo'),
                               ('Jornada lectivas', 'frase_no_confirmada_en_idioma')]:
            found = {'coincidencias': [{'pagina_pdf': 2, 'tipo': 'posible_encabezado'},
                                       {'pagina_pdf': 3, 'tipo': 'mencion'}]}
            data = {'cabecera': 'original', 'texto': text, 'segmentos': [{'inicio': 0, 'fin': len(text)}]}
            with self.subTest(text=text), patch.object(j, 'run_pdf_worker', return_value=data) as worker:
                j.extract_pdf_candidate(Path('original.pdf'), found, 'es', 'jornada lectiva')
                worker.assert_called_once_with(Path('original.pdf'), ('es', '2'))
                self.assertEqual(found['estado_pasaje'], expected)
                self.assertEqual('extraccion_candidata' in found, expected.startswith('extraido'))

    def test_multiple_headings_preserve_all_candidates(self):
        headings = [{'pagina_pdf': p, 'tipo': 'posible_encabezado'} for p in [1, 2]]
        found = {'coincidencias': headings}
        with patch.object(j, 'run_pdf_worker') as worker:
            j.extract_pdf_candidate(Path('original.pdf'), found, 'es', 'anexo')
            worker.assert_not_called()
        self.assertEqual(found['estado_pasaje'], 'varios_encabezados_en_tramo')
        self.assertEqual(found['coincidencias'], headings)

    def test_single_mention_requires_phrase_in_requested_fragment(self):
        for text, expected in [('La jornada lectiva del personal.', 'extraido_en_mencion_unica_del_tramo'),
                               ('La jornada semanal del personal.', 'frase_no_confirmada_en_idioma')]:
            found = {'coincidencias': [{'pagina_pdf': 2, 'tipo': 'mencion'}], 'siguiente_pagina': 161}
            data = {'cabecera': 'original', 'texto': text, 'segmentos': [{'inicio': 0, 'fin': len(text)}]}
            with self.subTest(text=text), patch.object(j, 'run_pdf_worker', return_value=data) as worker:
                j.extract_pdf_candidate(Path('original.pdf'), found, 'es', 'jornada lectiva')
                worker.assert_called_once_with(Path('original.pdf'), ('es', '2'))
                self.assertEqual(found['estado_pasaje'], expected)
                self.assertEqual(found['siguiente_pagina'], 161)
                if expected.startswith('extraido'):
                    self.assertEqual(found['extraccion_candidata']['intervalo_consulta'], [3, 18])
                else:
                    self.assertNotIn('extraccion_candidata', found)

    def test_multiple_candidates_or_index_do_not_trigger_extraction(self):
        for kinds in [('mencion', 'mencion'), ('mencion', 'posible_indice'), ('posible_indice',)]:
            candidates = [{'pagina_pdf': page, 'tipo': kind} for page, kind in enumerate(kinds, 1)]
            found = {'coincidencias': candidates}
            with self.subTest(kinds=kinds), patch.object(j, 'run_pdf_worker') as worker:
                j.extract_pdf_candidate(Path('original.pdf'), found, 'es', 'jornada lectiva')
                worker.assert_not_called()
                self.assertEqual(found['estado_pasaje'], 'sin_encabezado_en_tramo')
                self.assertEqual(found['coincidencias'], candidates)
                self.assertNotIn('extraccion_candidata', found)

    def test_failure_preserves_candidate_and_continuation(self):
        found = {'coincidencias': [{'pagina_pdf': 2, 'tipo': 'posible_encabezado'}], 'siguiente_pagina': 161}
        with patch.object(j, 'run_pdf_worker', side_effect=j.JuridicoError('PDF_TIMEOUT', 'límite')):
            j.extract_pdf_candidate(Path('original.pdf'), found, 'es', 'artículo 2')
        self.assertEqual(found['estado_pasaje'], 'error_extraccion')
        self.assertEqual(found['error_pasaje']['codigo'], 'PDF_TIMEOUT')
        self.assertEqual(found['siguiente_pagina'], 161)


class PassageWindow(unittest.TestCase):
    def test_normalization_preserves_original_offsets(self):
        original = "  A\nSituacio-\n nes  de  aprendizáje; l’aprenentatge"
        for query, expected in [
            ('situaciones de aprendizaje', 'Situacio-\n nes  de  aprendizáje'),
            ("l'aprenentatge", "l’aprenentatge"),
        ]:
            with self.subTest(query=query):
                start, end = j.pdf_phrase_span(original, query)
                self.assertEqual(original[start:end], expected)
        self.assertIsNone(j.pdf_phrase_span('reaprendizaje', 'aprendizaje'))

    def test_short_passage_keeps_late_match_and_source_offsets(self):
        from test_dogv_precision import Precision, response

        original = "Contexto anterior. " * 60 + "Jornada lectiva." + " Contexto posterior." * 50
        start = original.index("Jornada lectiva")
        extraction = {
            "texto": original, "intervalo_consulta": [start, start + len("Jornada lectiva")],
            "segmentos": [{"pagina_pdf": 2, "inicio": 0, "fin": len(original), "idioma": "es"}],
            "paginas": [], "tablas": [],
        }
        matches = {"coincidencias": [{"pagina_pdf": 2, "tipo": "posible_encabezado"}],
                   "extraccion_candidata": extraction, "siguiente_pagina": 161}
        fixture = Precision()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        pdf = response(b'%PDF-test', 'https://dogv.gva.es/datos/2018/08/07/pdf/2018_7822.pdf')
        pdf['bytes_descargados'] = len(pdf['body'])
        with patch.object(j.HTTP, 'get', side_effect=fixture.get), \
             patch.object(j, 'dogv_pdf_pages', return_value=(pdf, matches)):
            result = j.dogv_publicacion('original:327983#buscar=Jornada lectiva#extraer=1', max_caracteres=500)
        passage = result['datos']['pasaje']
        self.assertTrue(passage['consulta_en_fragmento'])
        self.assertGreater(passage['inicio'], 0)
        self.assertEqual(len(passage['texto']), 500)
        self.assertEqual(passage['texto'], original[passage['inicio']:passage['siguiente_inicio']])
        self.assertEqual(passage['paginas_fragmento'][0]['inicio_en_fragmento'], 0)
        self.assertTrue(passage['paginas_fragmento'][0]['url_oficial'].endswith('#page=2'))
        self.assertEqual(result['datos']['siguiente_pagina'], 161)
