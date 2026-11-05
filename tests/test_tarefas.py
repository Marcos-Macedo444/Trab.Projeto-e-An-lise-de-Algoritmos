import copy
import hashlib
import json
import multiprocessing
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from tsp_experimentos import ROOT, analisar, planejar, validar_config, validar_amostra
from web_local.tarefas import Gerenciador, Ocupado, Cancelado
from web_local.worker import executar_grupo
import tsp_forca_bruta as b


def worker_eof(canal, matriz, grupo):
    canal.close()


def worker_bloqueado(canal, matriz, grupo):
    canal.send({'evento': 'pronto'})
    canal.recv()
    threading.Event().wait(30)


def worker_aquecendo(canal, matriz, grupo):
    canal.send({'evento': 'aquecendo'})
    threading.Event().wait(30)


def worker_falha(canal, matriz, grupo):
    canal.send({'evento':'erro','mensagem':'falha deliberada no filho'})
    canal.close()


class Tarefas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.m = Gerenciador(self.tmp.name)

    def tearDown(self):
        self.m.close()
        self.tmp.cleanup()

    def terminar(self, ident):
        self.m.thread.join(20)
        self.assertFalse(self.m.thread.is_alive(), 'Coordenador não finalizou')
        return self.m.snapshot(ident)

    def criar(self, **kwargs):
        return self.m.criar(dict(tipo='demo', n=3, repeticoes=2, **kwargs))['id']

    def test_spawn_real_equivalencia_checkpoint_e_exportacao(self):
        fases = []
        original = self.m._fase
        def fase(t, estado, atual=None):
            if estado == 'calculando' and atual['repeticao'] == 2:
                cp = json.loads((self.m.base/t['id']/'checkpoint_000001.json').read_text(encoding='utf-8'))
                self.assertEqual(cp['dados']['sequencia'], 1)
                self.assertEqual(len(cp['dados']['amostras']), 1)
                fases.append('checkpoint antes de autorizar repetição 2')
            return original(t, estado, atual)
        with patch.object(self.m, '_fase', fase):
            ident = self.criar()
            s = self.terminar(ident)
        self.assertEqual(s['estado'], 'concluido',s)
        self.assertEqual(s['concluidas'], 2)
        self.assertEqual(len(fases), 1)
        resultado = self.m.resultados(ident)
        d=resultado['instancias']['3']['matriz']
        rota, custo, cont = b.tsp_forca_bruta(d)
        for a in resultado['amostras']:
            self.assertEqual(a['rota_indices'], rota)
            self.assertAlmostEqual(a['custo'], custo)
            self.assertEqual(a['rotas_observadas'], cont['rotas'])
            self.assertEqual(a['arestas_observadas'], cont['arestas'])
        self.assertIn('tarefa.zip', s['arquivos'])
        self.assertTrue(self.m.arquivo(ident,'grafico_tsp.png').is_file())
        self.assertIsNone(self.m.filho)

    def test_worker_clock_aquecimento_e_protocolo(self):
        eventos=[]
        class Canal:
            comandos=iter([{'comando':'executar','repeticao':1},{'comando':'executar','repeticao':2},{'comando':'encerrar'}])
            def send(self,v):eventos.append(('enviar',v))
            def recv(self):eventos.append(('receber',None));return next(self.comandos)
            def close(self):eventos.append(('fechar',None))
        def solver(d,g):
            eventos.append(('solver',None))
            return [0,1,2],3.,{'rotas':2,'arestas':6}
        tempos=iter([10.,12.,20.,25.])
        def clock():eventos.append(('clock',None));return next(tempos)
        g=planejar(validar_config({'tipo':'demo','n':3}))[0]
        executar_grupo(Canal(),[[0,1,1],[1,0,1],[1,1,0]],g,solver,clock)
        self.assertEqual(sum(t=='solver' for t,_ in eventos),3)
        self.assertEqual(sum(t=='clock' for t,_ in eventos),4)
        resultados=[v['amostra'] for t,v in eventos if t=='enviar' and v['evento']=='resultado']
        self.assertEqual([a['tempo_s'] for a in resultados],[2.,5.])
        # Um aquecimento antes de qualquer clock; cada envio depois do segundo clock.
        self.assertLess(next(i for i,(t,_) in enumerate(eventos) if t=='solver'),next(i for i,(t,_) in enumerate(eventos) if t=='clock'))
        for i,(tipo,valor) in enumerate(eventos):
            if tipo=='enviar' and valor['evento']=='resultado':
                self.assertEqual(eventos[i-1][0],'clock')

    def test_cancelar_antes_de_comecar(self):
        entrou=threading.Event();liberar=threading.Event();real=self.m._executar
        def executar(t):entrou.set();liberar.wait(5);real(t)
        with patch.object(self.m,'_executar',executar):
            ident=self.criar();self.assertTrue(entrou.wait(5))
            self.m.cancelar(ident);liberar.set();s=self.terminar(ident)
        self.assertEqual(s['estado'],'cancelado');self.assertEqual(s['concluidas'],0)
        self.assertIsNone(self.m.resultados(ident)['c'])

    def _cancelar_fase(self,worker,esperada):
        self.m.worker=worker
        entrou=threading.Event();real=self.m._fase
        def fase(t,e,a=None):
            r=real(t,e,a)
            if e==esperada:entrou.set()
            return r
        with patch.object(self.m,'_fase',fase):
            ident=self.criar();self.assertTrue(entrou.wait(10))
            self.m.cancelar(ident);s=self.terminar(ident)
        self.assertEqual(s['estado'],'cancelado');self.assertEqual(s['concluidas'],0)
        self.assertIsNone(self.m.filho)

    def test_cancelar_aquecimento(self):self._cancelar_fase(worker_aquecendo,'aquecendo')
    def test_cancelar_calculo(self):self._cancelar_fase(worker_bloqueado,'calculando')

    def test_cancelar_exportacao_preserva_concluidas(self):
        entrou=threading.Event();liberar=threading.Event();real=self.m._exportar
        def exportar(t,e):entrou.set();liberar.wait(5);return real(t,e)
        with patch.object(self.m,'_exportar',exportar):
            ident=self.criar();self.assertTrue(entrou.wait(10));self.m.cancelar(ident);liberar.set();s=self.terminar(ident)
        self.assertEqual(s['estado'],'cancelado');self.assertEqual(s['concluidas'],2)
        meta=json.loads(self.m.arquivo(ident,'metadados.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['estado'],'cancelado')

    def test_resposta_tardia_cancelada_e_amostra_aceita(self):
        ident=self.criar();self.terminar(ident)
        t=self.m.tarefas[ident];am=copy.deepcopy(t['amostras'][0]);g=t['plano'][0]
        self.assertEqual(len(t['amostras']),2)
        t['cancelamento']=True
        with self.assertRaises(Cancelado):self.m._aceitar(t,am,g,1)
        self.assertEqual(len(t['amostras']),2)

    def test_falha_eof_zero_amostras(self):
        self.m.worker=worker_eof
        ident=self.criar();s=self.terminar(ident)
        self.assertEqual(s['estado'],'falhou');self.assertEqual(s['concluidas'],0)
        self.assertIn('Worker',s['razao'])
        self.assertTrue((self.m.base/ident/'checkpoint_000000.json').exists())

    def test_falha_do_filho_e_figura_preserva_csv(self):
        self.m.worker=worker_falha
        ident=self.criar();s=self.terminar(ident)
        self.assertEqual(s['estado'],'falhou')
        self.assertIn('deliberada',s['razao'])
        self.m.worker=executar_grupo
        with patch('web_local.tarefas.b.plotar',side_effect=OSError('figura indisponível')):
            ident=self.criar();s=self.terminar(ident)
        self.assertEqual(s['estado'],'falhou');self.assertEqual(s['concluidas'],2)
        self.assertIsNotNone(self.m.arquivo(ident,'repeticoes.csv'))
        self.assertIsNotNone(self.m.arquivo(ident,'metadados.json'))

    def test_resultado_invalido_nao_entra_no_checkpoint(self):
        ident=self.criar();self.terminar(ident)
        t=self.m.tarefas[ident];a=copy.deepcopy(t['amostras'][0]);a['rota_indices']=[0,0,1]
        with self.assertRaises(ValueError):self.m._aceitar(t,a,t['plano'][0],1)
        self.assertEqual(len(t['amostras']),2)

    def test_recuperar_checkpoint_mais_novo_que_manifesto(self):
        ident=self.criar();self.terminar(ident)
        p=self.m.base/ident/'estado.json'
        estado=json.loads(p.read_text(encoding='utf-8'))
        estado.update(estado='calculando',sequencia=1,concluidas=1)
        p.write_text(json.dumps(estado),encoding='utf-8')
        self.m.close();self.m=Gerenciador(self.tmp.name)
        self.assertEqual(self.m.snapshot(ident)['concluidas'],2)
        self.assertEqual(self.m.snapshot(ident)['estado'],'interrompido')

    def test_falha_exportacao_e_recuperacao(self):
        with patch.object(self.m,'_exportar',side_effect=OSError('disco indisponível')):
            ident=self.criar();s=self.terminar(ident)
        self.assertEqual(s['estado'],'falhou');self.assertEqual(s['concluidas'],2)
        self.assertTrue((self.m.base/ident/'checkpoint_000002.json').exists())
        # Simula manifesto que não acompanhou o checkpoint e último cp corrompido.
        (self.m.base/ident/'checkpoint_000002.json').write_text('{quebrado',encoding='utf-8')
        self.m.close();self.m=Gerenciador(self.tmp.name)
        s=self.m.snapshot(ident)
        self.assertEqual(s['estado'],'interrompido');self.assertEqual(s['concluidas'],1)
        self.assertEqual(self.m.resultados(ident)['amostras'][0]['repeticao'],1)

    def test_encerramento_normal_e_lock(self):
        with self.assertRaises(Ocupado):Gerenciador(self.tmp.name)
        self.m.worker=worker_bloqueado
        evento=threading.Event();real=self.m._fase
        def fase(t,e,a=None):
            r=real(t,e,a)
            if e=='calculando':evento.set()
            return r
        with patch.object(self.m,'_fase',fase):
            ident=self.criar();self.assertTrue(evento.wait(10));self.m.close()
        self.assertIsNone(self.m.filho)
        self.assertFalse(self.m.thread.is_alive())
        self.m=Gerenciador(self.tmp.name)
        self.assertEqual(self.m.snapshot(ident)['estado'],'cancelado')

    def test_comparacao_sem_contadores_inventados(self):
        ident=self.m.criar({'tipo':'comparacao','n':4,'repeticoes':1})['id']
        s=self.terminar(ident);self.assertEqual(s['estado'],'concluido',s)
        d=self.m.resultados(ident)
        self.assertIsNone(d['c']);self.assertEqual(len(d['amostras']),4)
        for a in d['amostras'][1:]:self.assertIsNone(a['rotas_observadas'])
        self.assertNotIn('resultados_tsp.csv',s['arquivos'])


if __name__=='__main__':unittest.main()
