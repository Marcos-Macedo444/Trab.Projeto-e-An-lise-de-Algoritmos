"""Adaptador somente leitura das coletas CLI; não migra nem regrava originais."""
import csv
import json
import math
from pathlib import Path

import tsp_forca_bruta as b


def ler_csv(path):
    with path.open(encoding='utf-8', newline='') as f:
        linhas = list(csv.DictReader(f, delimiter=';'))
    for r in linhas:
        for k, v in list(r.items()):
            if not v:
                r[k] = None
            elif k == 'n' or k == 'repeticao' or 'rotas' in k or 'arestas' in k or k == 'repeticoes_concluidas':
                r[k] = int(v)
            elif k.endswith('_s') or k == 'custo_otimo':
                r[k] = float(v)
    return linhas


def _carregar_cli(raiz, protegido=False):
    historico = {}
    for base in ('resultados', 'meus_resultados'):
        for p in sorted((Path(raiz)/base).glob('execucao_*/metadados.json')):
            meta = json.loads(p.read_text(encoding='utf-8'))
            pasta = p.parent
            ident = 'cli_' + base + '_' + pasta.name
            config = meta['argumentos']
            amostras = ler_csv(pasta/'repeticoes.csv')
            resumo = ler_csv(pasta/'resultados_tsp.csv')
            inst = {}
            for n, d in meta.get('instancias', {}).items():
                cidades = b.gerar_cidades(int(n), config.get('semente', 42))
                regenerada = b.matriz_de_custos(cidades)
                confere = len(d) == len(regenerada) and all(len(x) == len(y) and
                    all(math.isclose(a, b_, rel_tol=1e-12, abs_tol=1e-12) for a, b_ in zip(x,y))
                    for x,y in zip(d,regenerada))
                inst[n] = dict(matriz=d, coordenadas=cidades if confere else None,
                    origem_coordenadas='reconstruídas da semente; matriz conferida' if confere else
                    'sem coordenadas verificadas; somente matriz disponível')
            for a in amostras:
                a.update(algoritmo='bruta', custo=a['custo_otimo'],
                    rota_indices=[int(x.strip()[1:])-1 for x in a['rota_otima'].split('->')][:-1])
            for r in resumo:
                r['repeticoes_previstas'] = config['repeticoes']
                r['parcial'] = r['repeticoes_concluidas'] < config['repeticoes']
            arquivos = {nome:pasta/nome for nome in ('repeticoes.csv','resultados_tsp.csv',
                'projecoes.csv','metadados.json','grafico_tsp.png') if (pasta/nome).is_file()}
            planejadas = (config['nmax']-config['nmin']+1)*config['repeticoes']
            if config.get('sem_fixar'):
                planejadas += max(0, min(config['nmax'],config['nmax_sem_fixar'])-config['nmin']+1)*config['repeticoes']
            historico[ident] = dict(arquivos=arquivos, protegido=protegido,
                snapshot=dict(id=ident, origem='cli', protegida=protegido, config=config, inicio=meta['inicio'],
                    fim=meta.get('fim'), estado='interrompido' if meta.get('interrompido') else 'concluido',
                    razao='Execução pela interface de terminal.',
                    sequencia=len(amostras), concluidas=len(amostras), planejadas=planejadas,
                    atual=None, arquivos=list(arquivos), duracao_total_s=None),
                resultados=dict(schema=1, origem='cli', config=config, amostras=amostras,
                    resumo=resumo, c=meta.get('c'), c_provisorio=False,
                    projecoes=ler_csv(pasta/'projecoes.csv'), instancias=inst, plano=[]))
    return historico


def carregar_cli(raiz):
    """Evidências oficiais prevalecem sobre cópias de trabalho do mesmo conjunto."""
    raiz = Path(raiz)
    historico = _carregar_cli(raiz)
    oficiais = raiz/'evidencias'
    historico.update(_carregar_cli(oficiais, protegido=True))
    for estado in sorted((oficiais/'resultados_web').glob('web_*/estado.json')):
        pasta = estado.parent
        snapshot = json.loads(estado.read_text(encoding='utf-8'))
        if snapshot['estado'] not in ('concluido', 'interrompido', 'cancelado'):
            continue
        dados = json.loads((pasta/'resultados.json').read_text(encoding='utf-8'))
        nomes = [n for n in snapshot['arquivos'] if Path(n).name == n and (pasta/n).is_file()]
        snapshot.update(protegida=True, arquivos=nomes, atual=None)
        historico[snapshot['id']] = dict(protegido=True, snapshot=snapshot,
            resultados=dados, arquivos={n:pasta/n for n in nomes})
    return historico
