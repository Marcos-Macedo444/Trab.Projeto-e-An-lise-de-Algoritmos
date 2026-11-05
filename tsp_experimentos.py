"""Adaptadores estruturados da web; preserva os contratos e a CLI acadêmica."""
import hashlib
import json
import math
import os
from pathlib import Path
import statistics

import tsp_forca_bruta as bruta

ROOT = Path(__file__).resolve().parent
SCHEMA = 1
ATIVOS = {'pendente', 'preparando', 'aquecendo', 'calculando', 'exportando', 'cancelando'}
TETOS_PADRAO = {'fixo': 20, 'livre': 20, 'comparacao': 10}
AMOSTRA_CAMPOS = ['n', 'modo', 'repeticao', 'tempo_s', 'rotas_observadas',
                  'arestas_observadas', 'custo_otimo', 'rota_otima']
PROJECAO_CAMPOS = ['n', 'rotas_fixas', 'rotas_sem_fixar', 'arestas_fixas',
                   'arestas_sem_fixar', 'tempo_estimado_s', 'natureza']
RESUMO_CAMPOS = ['n','modo','repeticoes_concluidas','tempo_s','minimo_s','maximo_s',
    'rotas_observadas_por_execucao','arestas_observadas_por_execucao',
    'rotas_esperadas_por_execucao','arestas_esperadas_por_execucao','custo_otimo',
    'rota_otima','tempo_modelo_c_n_fatorial_s']


def validar_config(dados, tetos=None):
    tetos = tetos or TETOS_PADRAO
    if not isinstance(dados, dict):
        raise ValueError('Envie um objeto JSON com a configuração.')
    permitidos = {'tipo', 'nmin', 'nmax', 'n', 'repeticoes', 'semente', 'sem_fixar',
                 'nmax_sem_fixar', 'avancado', 'limite_segundos'}
    if set(dados) - permitidos:
        raise ValueError('Campos desconhecidos na configuração.')
    tipo = dados.get('tipo', 'benchmark')
    if tipo not in ('benchmark', 'demo', 'comparacao'):
        raise ValueError('Tipo deve ser benchmark, demo ou comparacao.')

    def inteiro(nome, padrao, minimo, maximo):
        v = dados.get(nome, padrao)
        if type(v) is not int or not minimo <= v <= maximo:
            raise ValueError(f'{nome}: informe inteiro entre {minimo} e {maximo}.')
        return v

    for nome in ('avancado', 'sem_fixar'):
        if nome in dados and type(dados[nome]) is not bool:
            raise ValueError(f'{nome}: informe verdadeiro ou falso.')
    avancado = dados.get('avancado', False)
    limite = tetos['fixo'] if avancado else min(10, tetos['fixo'])
    livre = tetos['livre'] if avancado else min(8, tetos['livre'])
    c = dict(tipo=tipo, semente=inteiro('semente', 42, -1000000000, 1000000000),
             repeticoes=inteiro('repeticoes', 3 if tipo == 'benchmark' else 1, 1, 100),
             avancado=avancado, limite_segundos=inteiro('limite_segundos', 0, 0, 604800))
    if tipo == 'benchmark':
        c.update(nmin=inteiro('nmin', 3, 3, limite), nmax=inteiro('nmax', 10, 3, limite),
                 sem_fixar=dados.get('sem_fixar', False),
                 nmax_sem_fixar=inteiro('nmax_sem_fixar', min(8, livre), 3, livre))
        if c['nmin'] > c['nmax']:
            raise ValueError('nmin deve ser menor ou igual a nmax.')
    else:
        c['n'] = inteiro('n', 8 if tipo == 'comparacao' else 5, 3,
                         min(limite, tetos['comparacao']) if tipo == 'comparacao' else limite)
    return c


def planejar(c):
    if c['tipo'] == 'benchmark':
        grupos = [dict(n=n, modo='fixo', algoritmo='bruta', repeticoes=c['repeticoes'])
                  for n in range(c['nmin'], c['nmax'] + 1)]
        if c['sem_fixar']:
            grupos += [dict(n=n, modo='sem_fixar', algoritmo='bruta', repeticoes=c['repeticoes'])
                       for n in range(c['nmin'], min(c['nmax'], c['nmax_sem_fixar']) + 1)]
    else:
        algoritmos = ['bruta', 'held_karp', 'guloso', 'dois_opt'] if c['tipo'] == 'comparacao' else ['bruta']
        grupos = [dict(n=c['n'], modo='fixo', algoritmo=a, repeticoes=c['repeticoes']) for a in algoritmos]
    for g in grupos:
        if g['algoritmo'] == 'bruta':
            g['rotas_esperadas'] = math.factorial(g['n'] - (g['modo'] == 'fixo'))
            g['arestas_esperadas'] = g['n'] * g['rotas_esperadas']
    return grupos


def instancias(c, grupos):
    resultado = {}
    for n in sorted({g['n'] for g in grupos}):
        cidades = bruta.gerar_cidades(n, c['semente'])
        resultado[str(n)] = dict(coordenadas=cidades, matriz=bruta.matriz_de_custos(cidades),
                                 origem_coordenadas='geradas nesta tarefa')
    return resultado


def validar_amostra(a, grupo, rep, matriz):
    if not isinstance(a, dict) or any(a.get(k) != grupo[k] for k in ('n', 'modo', 'algoritmo')):
        raise ValueError('Resultado do worker não corresponde ao grupo.')
    if a.get('repeticao') != rep:
        raise ValueError('Sequência de repetição inválida.')
    n = grupo['n']
    rota = a.get('rota_indices')
    if not isinstance(rota, list) or any(type(x) is not int for x in rota) or sorted(rota) != list(range(n)):
        raise ValueError('Worker retornou rota inválida.')
    if grupo['modo'] == 'fixo' and rota[0] != 0:
        raise ValueError('Origem fixa não preservada.')
    for k in ('tempo_s', 'custo'):
        v = a.get(k)
        if isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0:
            raise ValueError('Tempo/custo inválido no resultado.')
    custo = sum(matriz[rota[i]][rota[(i+1) % n]] for i in range(n))
    if not math.isclose(custo, a['custo'], rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError('Custo não corresponde à rota fechada.')
    if grupo['algoritmo'] == 'bruta':
        if a.get('rotas_observadas') != grupo['rotas_esperadas'] or a.get('arestas_observadas') != grupo['arestas_esperadas']:
            raise ValueError('Contagens observadas incorretas.')
    elif a.get('rotas_observadas') is not None or a.get('arestas_observadas') is not None:
        raise ValueError('Contadores não disponíveis para este algoritmo.')


def amostras_csv(amostras):
    return [dict(n=a['n'], modo=a['modo'], repeticao=a['repeticao'], tempo_s=a['tempo_s'],
                 rotas_observadas=a['rotas_observadas'], arestas_observadas=a['arestas_observadas'],
                 custo_otimo=a['custo'], rota_otima=' -> '.join(f'v{x+1}' for x in a['rota_indices']+[a['rota_indices'][0]]))
            for a in amostras]


def analisar(config, amostras):
    if config['tipo'] != 'comparacao':
        resumo = bruta.resumir(amostras_csv(amostras))
        c = bruta.calibrar_c(resumo)
        proj = bruta.tabela_extrapolada(c, medidos=[r['n'] for r in resumo if r['modo'] == 'fixo'])
        return resumo, c, proj
    from tsp_eficiente import erro_percentual
    exatos = [a['custo'] for a in amostras if a['algoritmo'] in ('bruta', 'held_karp')]
    otimo = exatos[0] if exatos else None
    if any(not math.isclose(x, otimo, rel_tol=1e-9, abs_tol=1e-9) for x in exatos):
        raise ValueError('Métodos exatos divergiram.')
    resumo = []
    for alg in dict.fromkeys(a['algoritmo'] for a in amostras):
        grupo = [a for a in amostras if a['algoritmo'] == alg]
        ts = [a['tempo_s'] for a in grupo]
        resumo.append(dict(algoritmo=alg, n=grupo[0]['n'], modo='fixo',
            repeticoes_concluidas=len(grupo), tempo_s=statistics.median(ts),
            minimo_s=min(ts), maximo_s=max(ts), custo=grupo[0]['custo'],
            exato=alg in ('bruta', 'held_karp'),
            erro_percentual=erro_percentual(grupo[0]['custo'], otimo) if otimo is not None else None,
            rotas_observadas_por_execucao=grupo[0]['rotas_observadas'],
            arestas_observadas_por_execucao=grupo[0]['arestas_observadas']))
    return resumo, None, []


def atomico(caminho, valor):
    caminho = Path(caminho)
    tmp = caminho.with_suffix(caminho.suffix + '.tmp')
    with tmp.open('w', encoding='utf-8') as f:
        json.dump(valor, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, caminho)


def hashes_codigo():
    nomes = ['tsp_forca_bruta.py', 'tsp_eficiente.py', 'tsp_experimentos.py',
             'web_local/worker.py', 'web_local/tarefas.py', 'web_local/app.py',
             'web_local/exclusao.py']
    return {n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in nomes}


def api_exata(valor, chave=''):
    """Contagens em strings decimais, mesmo abaixo de 2**53; índices ficam int."""
    if isinstance(valor, dict):
        return {k: api_exata(v, k) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [api_exata(v, chave) for v in valor]
    if type(valor) is int and ('rotas' in chave or 'arestas' in chave):
        return str(valor)
    return valor
