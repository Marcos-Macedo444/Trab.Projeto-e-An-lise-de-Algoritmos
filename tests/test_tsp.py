import contextlib
import copy
import csv
import io
import itertools
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import tsp_forca_bruta as b
import tsp_eficiente as e


def oraculo(d):
    return min(sum(d[r[i]][r[(i+1) % len(r)]] for i in range(len(r)))
               for p in itertools.permutations(range(1, len(d))) for r in [(0,) + p])


class Correção(unittest.TestCase):
    def verificar(self, d, esperado):
        original = copy.deepcopy(d)
        for fixo in (True, False):
            rota, valor, cont = b.tsp_forca_bruta(d, fixo)
            self.assertEqual(sorted(rota), list(range(len(d))))
            if fixo:
                self.assertEqual(rota[0], 0)
            self.assertAlmostEqual(valor, esperado)
            self.assertAlmostEqual(valor, sum(d[rota[i]][rota[(i+1)%len(d)]] for i in range(len(d))))
            self.assertEqual(cont['rotas'], math.factorial(len(d)-1 if fixo else len(d)))
            self.assertEqual(cont['arestas'], len(d)*cont['rotas'])
        rota, valor = e.tsp_held_karp(d)
        self.assertEqual(sorted(rota), list(range(len(d))))
        self.assertEqual(rota[0], 0)
        self.assertAlmostEqual(e.custo(rota,d), valor)
        self.assertAlmostEqual(valor, esperado)
        self.assertEqual(d, original)

    def test_otimos_conhecidos(self):
        for d, otimo in [(b.matriz_de_custos([(0,0),(1,0),(1,1),(0,1)]),4),
            ([[0,10,15,20],[10,0,35,25],[15,35,0,30],[20,25,30,0]],80),
            ([[0,1,9],[9,0,1],[1,9,0]],3), ([[0]*4 for _ in range(4)],0)]:
            with self.subTest(d=d):
                self.verificar(d,otimo)

    def test_oraculo_aleatorio(self):
        rng = random.Random(713)
        for n in range(3,7):
            for simetrico in (False, True):
                d = [[0 if i==j else rng.randrange(20) for j in range(n)] for i in range(n)]
                if simetrico:
                    for i in range(n):
                        for j in range(i):
                            d[i][j] = d[j][i]
                self.verificar(d,oraculo(d))
                if simetrico:
                    original = copy.deepcopy(d)
                    rota, valor = e.tsp_heuristica(d)
                    self.assertEqual(sorted(rota), list(range(n)))
                    self.assertGreaterEqual(valor+1e-9,oraculo(d))
                    self.assertLessEqual(valor,e.custo(e.vizinho_mais_proximo(d),d)+1e-9)
                    self.assertEqual(original,d)

    def test_contagem_e_retorno(self):
        for n in range(3,8):
            d=b.matriz_de_custos(b.gerar_cidades(n))
            fixo=b.tsp_forca_bruta(d)[2]
            livre=b.tsp_forca_bruta(d,False)[2]
            self.assertEqual(livre['rotas'],n*fixo['rotas'])
            self.assertEqual(fixo['arestas'],math.factorial(n))
        cont={'arestas':0}
        self.assertEqual(b.custo_da_rota([0,1,2],[[0,1,9],[9,0,1],[1,9,0]],cont),3)
        self.assertEqual(cont['arestas'],3)

    def test_permutacoes(self):
        entrada=[1,2,3]
        ps=list(b.permutacoes(entrada))
        self.assertEqual(set(ps),set(itertools.permutations(entrada)))
        self.assertEqual(len(ps),6)
        self.assertTrue(all(isinstance(p,tuple) for p in ps))
        self.assertEqual(entrada,[1,2,3])
        self.assertEqual(list(b.permutacoes([])),[()])

    def test_invalidos(self):
        for d in [[], [[0]], [[0,1,2],[1,0],[2,1,0]],
                  [[1,1,1],[1,0,1],[1,1,0]],
                  [[0,-1,1],[1,0,1],[1,1,0]],
                  [[0,float('inf'),1],[1,0,1],[1,1,0]],
                  [[0,float('nan'),1],[1,0,1],[1,1,0]],
                  [[0,'a',1],[1,0,1],[1,1,0]],
                  [[0,True,1],[1,0,1],[1,1,0]]]:
            for solver in [b.tsp_forca_bruta,e.tsp_held_karp,e.tsp_heuristica]:
                with self.subTest(d=d,solver=solver), self.assertRaises(ValueError):
                    solver(d)
        with self.assertRaises(ValueError):
            e.dois_opt([0,1,2],[[0,1,9],[9,0,1],[1,9,0]])
        with self.assertRaises(ValueError):
            e.dois_opt([0,1,1],[[0]*3 for _ in range(3)])
        for inicio in [-1,3,True]:
            with self.assertRaises(ValueError):
                e.vizinho_mais_proximo([[0]*3 for _ in range(3)],inicio)

    def test_guloso_e_zero(self):
        d=b.matriz_de_custos([(4,0),(4,2),(0,2),(2,4),(5,2)])
        rota=e.vizinho_mais_proximo(d)
        self.assertEqual(rota,[0,1,4,3,2])
        self.assertAlmostEqual(e.custo(rota,d),13.9061143552,places=5)
        self.assertAlmostEqual(b.tsp_forca_bruta(d)[1],13.36505818199,places=5)
        self.assertGreater(e.custo(rota,d),b.tsp_forca_bruta(d)[1])
        self.assertEqual(e.erro_percentual(0,0),0)
        self.assertIsNone(e.erro_percentual(1,0))
        self.assertEqual(e.tsp_heuristica([[0]*3 for _ in range(3)])[1],0)


class Exportação(unittest.TestCase):
    def test_cli_invalida(self):
        for args in [['--nmin','5','--nmax','3'],['--repeticoes','0'],['--demo','0'],['--demo','-1'],['--nmin','2']]:
            proc=subprocess.run([sys.executable,'tsp_forca_bruta.py',*args],capture_output=True,text=True)
            self.assertEqual(proc.returncode,2)
            self.assertNotIn('Traceback',proc.stderr)

    def test_execucao_completa(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(b.main(['--nmax','4','--sem-fixar','--repeticoes','2','--saida',tmp]),0)
            pasta=next(Path(tmp).iterdir())
            meta=json.loads((pasta/'metadados.json').read_text(encoding='utf-8'))
            def ler(nome):
                with (pasta/nome).open(encoding='utf-8',newline='') as f:
                    return list(csv.DictReader(f,delimiter=';'))
            amostras=ler('repeticoes.csv'); resumo=ler('resultados_tsp.csv')
            self.assertEqual(len(amostras),8)
            self.assertEqual({a['modo'] for a in amostras},{'fixo','sem_fixar'})
            self.assertEqual(len(resumo),4)
            for r in resumo:
                ts=sorted(float(a['tempo_s']) for a in amostras if a['n']==r['n'] and a['modo']==r['modo'])
                self.assertEqual(float(r['tempo_s']),sum(ts)/2)
                self.assertEqual(float(r['minimo_s']),ts[0])
                self.assertEqual(float(r['maximo_s']),ts[-1])
                if r['modo']=='fixo':
                    self.assertEqual(float(r['tempo_modelo_c_n_fatorial_s']),meta['c']*math.factorial(int(r['n'])))
                else:
                    self.assertEqual(r['tempo_modelo_c_n_fatorial_s'],'')
            fixos=[r for r in resumo if r['modo']=='fixo']
            esperado=sum(math.factorial(int(r['n']))*float(r['tempo_s']) for r in fixos)/sum(math.factorial(int(r['n']))**2 for r in fixos)
            self.assertEqual(meta['c'],esperado)
            self.assertTrue(meta['grafico_produzido'])
            self.assertGreater((pasta/'grafico_tsp.png').stat().st_size,1000)
            self.assertTrue(any(r['natureza']=='estimativa_extrapolada' for r in ler('projecoes.csv')))
            with contextlib.redirect_stdout(io.StringIO()):
                b.main(['--nmax','3','--saida',tmp])
            self.assertEqual(len(list(Path(tmp).iterdir())),2)

    def test_interrupcao(self):
        real=b.tsp_forca_bruta
        chamadas=[]
        def solver(d,fixar=True):
            chamadas.append((copy.deepcopy(d),fixar))
            if len(chamadas)==3: # aquecimento, rep 1 completa, rep 2 interrompida
                raise KeyboardInterrupt
            return real(d,fixar)
        with tempfile.TemporaryDirectory() as tmp, patch.object(b,'tsp_forca_bruta',solver), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.main(['--nmax','3','--saida',tmp]),130)
            pasta=next(Path(tmp).iterdir())
            meta=json.loads((pasta/'metadados.json').read_text(encoding='utf-8'))
            self.assertTrue(meta['interrompido'])
            self.assertEqual(meta['repeticoes_concluidas'],1)
            with (pasta/'repeticoes.csv').open(encoding='utf-8') as f:
                self.assertEqual(len(list(csv.DictReader(f,delimiter=';'))),1)

    def test_mesma_matriz_e_sem_amostras(self):
        real=b.tsp_forca_bruta
        chamadas=[]
        def solver(d,fixar=True):
            chamadas.append((copy.deepcopy(d),fixar))
            return real(d,fixar)
        with tempfile.TemporaryDirectory() as tmp, patch.object(b,'tsp_forca_bruta',solver), contextlib.redirect_stdout(io.StringIO()):
            b.main(['--nmax','3','--sem-fixar','--repeticoes','1','--saida',tmp])
        self.assertEqual(len(chamadas),4)
        self.assertTrue(all(d==chamadas[0][0] for d,_ in chamadas))
        with tempfile.TemporaryDirectory() as tmp, patch.object(b,'tsp_forca_bruta',side_effect=KeyboardInterrupt), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(b.main(['--nmax','3','--saida',tmp]),130)
            meta=json.loads(next(Path(tmp).glob('*/metadados.json')).read_text(encoding='utf-8'))
            self.assertIsNone(meta['c'])
            self.assertFalse(meta['grafico_produzido'])


if __name__=='__main__':
    unittest.main()
