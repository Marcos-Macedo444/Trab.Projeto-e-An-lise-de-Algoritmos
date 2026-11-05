"""Limites e interrupções em bases temporárias; não são coletas de benchmark."""
import json
import math
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from tsp_experimentos import validar_config
from web_local.app import create_app
from web_local.tarefas import Gerenciador
from test_tarefas import worker_bloqueado


def primeira_completa_depois_bloqueio(canal, matriz, grupo):
    from tsp_forca_bruta import tsp_forca_bruta
    canal.send({'evento': 'pronto'})
    comando = canal.recv()
    inicio = time.perf_counter()
    rota, custo, cont = tsp_forca_bruta(matriz)
    duracao = time.perf_counter()-inicio
    canal.send({'evento': 'resultado', 'amostra': dict(
        n=grupo['n'], modo=grupo['modo'], algoritmo=grupo['algoritmo'],
        repeticao=comando['repeticao'], tempo_s=duracao, rota_indices=rota,
        custo=custo, rotas_observadas=cont['rotas'], arestas_observadas=cont['arestas'])})
    canal.recv()
    threading.Event().wait(30)


class Prolongados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)/'web'
        self.m = Gerenciador(self.base, raiz_cli=Path(self.tmp.name))
        self.client = create_app(self.m).test_client()

    def tearDown(self):
        self.m.close()
        self.tmp.cleanup()

    def terminar(self, ident):
        self.m.thread.join(15)
        self.assertFalse(self.m.thread.is_alive())
        return self.m.snapshot(ident)

    def test_plano_20_contagens_exatas_sem_iniciar_solver(self):
        p = self.client.post('/api/planejar', json=dict(nmin=20, nmax=20,
            sem_fixar=True, nmax_sem_fixar=20, avancado=True, repeticoes=1))
        self.assertEqual(p.status_code, 200, p.json)
        fixo, livre = p.json['grupos']
        self.assertEqual(fixo['rotas_esperadas'], str(math.factorial(19)))
        self.assertEqual(fixo['arestas_esperadas'], str(math.factorial(20)))
        self.assertEqual(livre['arestas_esperadas'], str(20*math.factorial(20)))
        self.assertTrue(p.json['avisos'])
        self.assertEqual(p.json['config']['limite_segundos'], 0)
        self.assertIsNone(self.m.thread)

    def test_limites_e_duracao_invalidos(self):
        for dados in [dict(nmax=11), dict(nmax=21, avancado=True),
            dict(limite_segundos=-1), dict(limite_segundos=True),
            dict(limite_segundos=1.5), dict(limite_segundos=604801),
            dict(tipo='comparacao', n=11, avancado=True)]:
            with self.subTest(dados=dados), self.assertRaises(ValueError):
                validar_config(dados)
        with self.assertRaises(ValueError):
            validar_config(dict(nmax=15, avancado=True), dict(fixo=14, livre=12, comparacao=10))

    def test_limite_interrompe_sem_inventar_medicao_e_recupera(self):
        self.m.worker = worker_bloqueado
        ident = self.m.criar(dict(tipo='demo', n=3, limite_segundos=1))['id']
        s = self.terminar(ident)
        self.assertEqual(s['estado'], 'interrompido', s)
        self.assertEqual(s['concluidas'], 0)
        self.assertEqual(s['interrupcao']['motivo'], 'limite_de_tempo')
        self.assertEqual(self.m.resultados(ident)['amostras'], [])
        meta = json.loads(self.m.arquivo(ident, 'metadados.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['interrupcao']['chamada']['repeticao'], 1)
        self.m.close()
        self.m = Gerenciador(self.base, raiz_cli=Path(self.tmp.name))
        self.assertEqual(self.m.snapshot(ident)['interrupcao'], s['interrupcao'])

    def test_limite_preserva_checkpoint_de_repeticao_completa(self):
        self.m.worker = primeira_completa_depois_bloqueio
        ident = self.m.criar(dict(tipo='demo', n=3, repeticoes=2, limite_segundos=1))['id']
        s = self.terminar(ident)
        self.assertEqual(s['estado'], 'interrompido', s)
        self.assertEqual(s['concluidas'], 1)
        self.assertEqual(s['interrupcao']['chamada']['repeticao'], 2)
        self.assertEqual(len(self.m.resultados(ident)['amostras']), 1)
        self.assertTrue((self.base/ident/'checkpoint_000001.json').is_file())

    def test_sem_limite_tempo_decorrido_e_cancelamento(self):
        self.m.worker = worker_bloqueado
        entrou = threading.Event()
        original = self.m._fase
        def fase(t, estado, atual=None):
            original(t, estado, atual)
            if estado == 'calculando': entrou.set()
        with patch.object(self.m, '_fase', fase):
            ident = self.m.criar(dict(tipo='demo', n=3))['id']
            self.assertTrue(entrou.wait(10))
            s = self.client.get('/api/tarefas/'+ident).json
            self.assertEqual(s['estado'], 'calculando')
            self.assertGreaterEqual(s['duracao_chamada_s'], 0)
            self.assertEqual(s['concluidas'], 0)
            self.m.cancelar(ident)
            s = self.terminar(ident)
        self.assertEqual(s['estado'], 'cancelado')
        self.assertIsNone(s['duracao_chamada_s'])
        self.assertEqual(s['interrupcao']['motivo'], 'cancelamento')

    def test_forca_bruta_real_n13_cancelavel_sem_callback_no_solver(self):
        entrou = threading.Event()
        original = self.m._fase
        def fase(t, estado, atual=None):
            original(t, estado, atual)
            if estado == 'calculando': entrou.set()
        with patch.object(self.m, '_fase', fase):
            ident = self.m.criar(dict(tipo='demo', n=13, avancado=True))['id']
            self.assertTrue(entrou.wait(10))
            self.m.cancelar(ident)
            s = self.terminar(ident)
        self.assertEqual(s['estado'], 'cancelado', s)
        self.assertEqual(s['concluidas'], 0)
        self.assertIsNone(self.m.filho)
        self.assertTrue((self.base/ident/'checkpoint_000000.json').is_file())


if __name__ == '__main__': unittest.main()
