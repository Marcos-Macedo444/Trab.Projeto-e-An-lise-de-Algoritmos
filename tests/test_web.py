import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import types
import contextlib
import io
import socket
import unittest
from unittest.mock import patch

from tsp_experimentos import ROOT, validar_config, api_exata
from web_local.app import create_app
from web_local.tarefas import Gerenciador
from test_tarefas import worker_bloqueado


class Web(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.m=Gerenciador(self.tmp.name)
        self.app=create_app(self.m);self.client=self.app.test_client()

    def tearDown(self):self.m.close();self.tmp.cleanup()

    def test_validacao_e_limites(self):
        for dados in [None,[],{'nmin':True},{'repeticoes':1.5},{'nmax':11},
            {'nmin':7,'nmax':5},{'sem_fixar':1},{'tipo':'outro'},{'campo':'extra'},
            {'nmax_sem_fixar':9},{'repeticoes':0},{'semente':'42'}]:
            r=self.client.post('/api/tarefas',json=dados)
            self.assertIn(r.status_code,(400,415));self.assertIn('erro',r.json)
        p=self.client.post('/api/planejar',json={'nmax':12,'avancado':True})
        self.assertEqual(p.status_code,200)
        self.assertEqual(p.json['grupos'][-1]['rotas_esperadas'],'39916800')
        p=self.client.post('/api/planejar',json={'nmin':9,'nmax':10,'sem_fixar':True})
        self.assertIsNotNone(p.json['aviso'])

    def test_http_durante_calculo_concorrencia_cancelamento(self):
        self.m.worker=worker_bloqueado
        entrou=threading.Event();real=self.m._fase
        def fase(t,e,a=None):
            r=real(t,e,a)
            if e=='calculando':entrou.set()
            return r
        with patch.object(self.m,'_fase',fase):
            r=self.client.post('/api/tarefas',json={'tipo':'demo','n':3})
            self.assertEqual(r.status_code,202);ident=r.json['id']
            self.assertTrue(entrou.wait(10))
            self.assertEqual(self.client.get('/api/tarefas/'+ident).status_code,200)
            self.assertEqual(self.client.get('/').status_code,200)
            self.assertEqual(self.client.post('/api/tarefas',json={'nmax':3}).status_code,409)
            self.assertEqual(self.client.post(f'/api/tarefas/{ident}/cancelar',json={}).status_code,202)
            self.m.thread.join(10);self.assertFalse(self.m.thread.is_alive())
        self.assertEqual(self.client.get('/api/tarefas/'+ident).json['estado'],'cancelado')

    def test_download_consistencia_e_restricoes(self):
        r=self.client.post('/api/tarefas',json={'tipo':'demo','n':3})
        ident=r.json['id'];self.m.thread.join(15)
        self.assertFalse(self.m.thread.is_alive())
        s=self.client.get('/api/tarefas/'+ident).json
        self.assertEqual(s['estado'],'concluido',s)
        dados=self.client.get(f'/api/tarefas/{ident}/resultados').json
        exportado=json.loads((self.m.base/ident/'resultados.json').read_text(encoding='utf-8'))
        self.assertFalse(exportado['c_provisorio'])
        self.assertEqual(dados['c'],exportado['c'])
        self.assertEqual(dados['amostras'][0]['rotas_observadas'],'2')
        self.assertIsInstance(dados['projecoes'][-1]['arestas_sem_fixar'],str)
        for nome in s['arquivos']:
            resposta=self.client.get(f'/api/tarefas/{ident}/arquivos/{nome}')
            self.assertEqual(resposta.status_code,200,nome)
            self.assertEqual(resposta.data,(self.m.base/ident/nome).read_bytes())
            resposta.close()
        for url in ['/api/tarefas/inexistente',f'/api/tarefas/{ident}/arquivos/estado.json',
                    f'/api/tarefas/{ident}/arquivos/..%2F..%2FREADME.md']:
            self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.get('/',headers={'Host':'malicioso.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/tarefas',json={},headers={'Origin':'https://externo.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/tarefas',json={},headers={'Origin':'null'}).status_code,403)
        self.assertEqual(self.client.get('/').headers['X-Content-Type-Options'],'nosniff')

    def test_historico_somente_leitura_n12(self):
        antes={p:hashlib.sha256(p.read_bytes()).hexdigest() for d in ['evidencias'] for p in (ROOT/d).rglob('*') if p.is_file()}
        tarefas=self.client.get('/api/tarefas').json['tarefas']
        cli=[t for t in tarefas if t['origem']=='cli'];self.assertEqual(len(cli),4)
        t=next(t for t in cli if '224818' in t['id'])
        d=self.client.get('/api/tarefas/'+t['id']+'/resultados').json
        am=next(a for a in d['amostras'] if a['n']==12)
        self.assertEqual(am['tempo_s'],76.40297299996018)
        self.assertEqual(am['rotas_observadas'],'39916800')
        self.assertIsNotNone(d['instancias']['12']['coordenadas'])
        self.assertEqual(self.client.post('/api/tarefas/'+t['id']+'/cancelar').status_code,400)
        for p,h in antes.items():self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),h)

    def test_importacoes_sem_efeitos_colaterais(self):
        codigo='import multiprocessing; import iniciar_web, web_local.app, web_local.tarefas, web_local.worker; assert not multiprocessing.active_children(); print("OK")'
        p=subprocess.run([sys.executable,'-B','-c',codigo],cwd=ROOT,capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'OK')

    def test_fluxo_lancador_ctrl_c_encerra_filho(self):
        import iniciar_web
        self.m.worker=worker_bloqueado
        entrou=threading.Event();real=self.m._fase
        def fase(t,e,a=None):
            r=real(t,e,a)
            if e=='calculando':entrou.set()
            return r
        m=self.m
        class Servidor:
            fechado=False
            def run(self):
                m.criar({'tipo':'demo','n':3})
                if not entrou.wait(10):raise RuntimeError('Worker não iniciou')
                raise KeyboardInterrupt
            def close(self):self.fechado=True
        servidor=Servidor()
        with socket.socket() as reserva_teste:
            reserva_teste.bind(('127.0.0.1',0));porta_livre=reserva_teste.getsockname()[1]
        pacote=types.ModuleType('waitress');pacote.__path__=[]
        modulo=types.ModuleType('waitress.server');modulo.create_server=lambda *a,**kw:servidor
        with patch.dict(sys.modules,{'waitress':pacote,'waitress.server':modulo}), patch('web_local.tarefas.Gerenciador',return_value=m), patch.object(m,'_fase',fase), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(iniciar_web.main(['--porta',str(porta_livre)]),0)
        self.assertTrue(servidor.fechado);self.assertIsNone(m.filho)
        self.assertFalse(m.thread.is_alive())

    def test_lancador_porta_ocupada(self):
        import iniciar_web
        pacote=types.ModuleType('waitress');pacote.__path__=[]
        modulo=types.ModuleType('waitress.server')
        modulo.create_server=lambda *a,**kw:self.fail('Não deve chegar ao Waitress com porta ocupada')
        with socket.socket() as ocupado:
            ocupado.bind(('127.0.0.1',0));ocupado.listen()
            porta=ocupado.getsockname()[1]
            saida=io.StringIO()
            with patch.dict(sys.modules,{'waitress':pacote,'waitress.server':modulo}), patch('web_local.tarefas.Gerenciador',return_value=self.m), contextlib.redirect_stderr(saida):
                self.assertEqual(iniciar_web.main(['--porta',str(porta)]),1)
            self.assertIn('--porta',saida.getvalue())


if __name__=='__main__':unittest.main()
