"""Exclusão executada exclusivamente em cópias e tarefas de diretórios temporários."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tsp_experimentos import ROOT
from web_local.app import create_app
from web_local.tarefas import Gerenciador


class Exclusao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tsp-exclusao-')
        self.raiz = Path(self.tmp.name)
        origem = ROOT/'evidencias/resultados/execucao_20261102_224154_225839'
        self.cli = self.raiz/'resultados'/origem.name
        shutil.copytree(origem, self.cli)
        self.m = Gerenciador(self.raiz/'resultados_web', raiz_cli=self.raiz)
        self.client = create_app(self.m).test_client()
        self.ident = self.m.criar({'tipo':'demo','n':3,'repeticoes':1})['id']
        self.m.thread.join(15)
        self.assertFalse(self.m.thread.is_alive())
        self.assertEqual(self.m.snapshot(self.ident)['estado'],'concluido')
        self.preservar = [self.raiz/'tests/test_codigo.py', self.raiz/'README.md',
            self.raiz/'historicos/evidencia.csv',self.raiz/'resultados/notas/arquivo.txt',
            self.m.base/'documentos/arquivo.txt']
        for p in self.preservar:
            p.parent.mkdir(parents=True,exist_ok=True);p.write_text('preservar',encoding='utf-8')

    def tearDown(self):
        self.m.close()
        self.tmp.cleanup()

    def previa(self):
        r=self.client.get('/api/experimentos/exclusao')
        self.assertEqual(r.status_code,200,r.json)
        return r.json

    def excluir(self,token):
        return self.client.post('/api/experimentos/excluir-todos',json={'confirmacao':token})

    def test_excluir_web_cli_preserva_codigo_testes_e_outras_pastas(self):
        pre=self.previa();self.assertEqual((pre['quantidade'],pre['web'],pre['cli']),(2,1,1))
        r=self.excluir(pre['confirmacao']);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json,{'removidos':2,'falhas':[],'restantes':0})
        self.assertFalse((self.m.base/self.ident).exists());self.assertFalse(self.cli.exists())
        self.assertEqual(self.client.get('/api/tarefas').json['tarefas'],[])
        self.assertEqual(self.client.get('/api/tarefas/'+self.ident).status_code,404)
        for p in self.preservar:self.assertEqual(p.read_text(encoding='utf-8'),'preservar')
        self.m.close();self.m=Gerenciador(self.raiz/'resultados_web',raiz_cli=self.raiz)
        self.assertEqual(self.m.listar()['tarefas'],[])

    def test_exige_confirmacao_e_permite_desistir_sem_mutacao(self):
        self.previa()
        for dados in [{},{'confirmacao':True},{'confirmacao':'x'},{'confirmacao':'0'*64},
                      {'confirmacao':self.previa()['confirmacao'],'pasta':'qualquer'}]:
            r=self.client.post('/api/experimentos/excluir-todos',json=dados)
            self.assertIn(r.status_code,(400,409))
        self.assertTrue(self.cli.exists());self.assertTrue((self.m.base/self.ident).exists())

    def test_confirmacao_desatualizada(self):
        token=self.previa()['confirmacao']
        self.m.criar({'tipo':'demo','n':3});self.m.thread.join(15)
        self.assertEqual(self.excluir(token).status_code,409)
        self.assertTrue(self.cli.exists());self.assertEqual(len(self.m.tarefas),2)

    def test_bloqueia_todas_as_fases_ativas_e_exportacao(self):
        token=self.previa()['confirmacao'];t=self.m.tarefas[self.ident]
        for fase in ('pendente','preparando','aquecendo','calculando','exportando','cancelando'):
            with self.subTest(fase=fase):
                t['estado']=fase
                self.assertEqual(self.client.get('/api/experimentos/exclusao').status_code,409)
                self.assertEqual(self.excluir(token).status_code,409)
        t['estado']='concluido';self.m.ativa=self.ident
        self.assertEqual(self.excluir(token).status_code,409)
        self.m.ativa=None
        self.assertTrue(self.cli.exists())

    def test_recusa_caminhos_fora_das_bases(self):
        registro=next(iter(self.m.cli.values()))
        original=registro['arquivos']['metadados.json']
        registro['arquivos']['metadados.json']=self.raiz/'tests/metadados.json'
        self.assertEqual(self.client.get('/api/experimentos/exclusao').status_code,400)
        registro['arquivos']['metadados.json']=original
        self.m.tarefas['../tests']={'estado':'falhou'}
        self.assertEqual(self.client.get('/api/experimentos/exclusao').status_code,400)
        self.m.tarefas.pop('../tests')
        for p in self.preservar:self.assertTrue(p.exists())

    def test_recusa_juncoes_e_links_sem_atravessar(self):
        fora=self.raiz/'fora_da_base';fora.mkdir();sentinela=fora/'segredo.txt';sentinela.write_text('intacto')
        for descendente in (False,True):
            pasta=self.m.base/'web_vinculo'
            if descendente:
                pasta.mkdir();link=pasta/'subpasta'
            else:link=pasta
            try:
                if os.name=='nt':
                    r=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(link),str(fora)],capture_output=True)
                    self.assertEqual(r.returncode,0,r.stderr)
                else:link.symlink_to(fora,target_is_directory=True)
                self.m.tarefas['web_vinculo']={'estado':'falhou'}
                self.assertEqual(self.client.get('/api/experimentos/exclusao').status_code,400)
                self.assertEqual(sentinela.read_text(),'intacto')
                self.assertTrue(self.cli.exists())
            finally:
                self.m.tarefas.pop('web_vinculo',None)
                if os.name=='nt':link.rmdir()
                else:link.unlink()
                if descendente:pasta.rmdir()

    def test_falha_de_permissao_explicita_e_historico_coerente(self):
        real=shutil.rmtree
        def remover(path,*args,**kw):
            if Path(path)==self.cli:raise PermissionError('arquivo em uso')
            return real(path,*args,**kw)
        with patch('web_local.tarefas.shutil.rmtree',side_effect=remover):
            r=self.excluir(self.previa()['confirmacao'])
        self.assertEqual(r.status_code,207)
        self.assertEqual((r.json['removidos'],r.json['restantes'],len(r.json['falhas'])),(1,1,1))
        self.assertTrue(self.cli.exists());self.assertFalse((self.m.base/self.ident).exists())

    def test_historico_vazio(self):
        self.excluir(self.previa()['confirmacao'])
        pre=self.previa();self.assertEqual(pre['quantidade'],0)
        self.assertEqual(self.excluir(pre['confirmacao']).json['removidos'],0)

    def test_evidencias_oficiais_cli_web_sao_preservadas(self):
        import hashlib
        oficiais=self.raiz/'evidencias'
        shutil.copytree(self.cli,oficiais/'resultados'/self.cli.name)
        shutil.copytree(self.m.base/self.ident,oficiais/'resultados_web'/self.ident)
        antes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in oficiais.rglob('*') if p.is_file()}
        self.m.close();self.m=Gerenciador(self.raiz/'resultados_web',raiz_cli=self.raiz)
        self.client=create_app(self.m).test_client()
        self.assertEqual(self.previa()['quantidade'],0)
        novo=self.m.criar({'tipo':'demo','n':3})['id'];self.m.thread.join(15)
        pre=self.previa();self.assertEqual((pre['quantidade'],pre['protegidos']),(1,2))
        self.assertEqual(self.excluir(pre['confirmacao']).json['removidos'],1)
        self.assertEqual(len(self.m.listar()['tarefas']),2)
        self.assertTrue(all(t['protegida'] for t in self.m.listar()['tarefas']))
        self.assertFalse((self.m.base/novo).exists())
        for p,h in antes.items():self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),h)

    def test_snapshot_excluido_do_historico_nao_e_regravado(self):
        import json
        ident='web_20261105_183530_38bc995a46'
        pasta=self.m.base/ident;pasta.mkdir()
        estado=pasta/'estado.json';estado.write_text('{"estado":"calculando"}',encoding='utf-8')
        indice=self.raiz/'evidencias/indice.json';indice.parent.mkdir()
        indice.write_text(json.dumps({'ignorar_historico':[ident]}),encoding='utf-8')
        antes=estado.read_bytes()
        self.m.close();self.m=Gerenciador(self.raiz/'resultados_web',raiz_cli=self.raiz)
        self.assertNotIn(ident,[t['id'] for t in self.m.listar()['tarefas']])
        self.assertEqual(estado.read_bytes(),antes)


if __name__=='__main__':unittest.main()
