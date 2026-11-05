"""Força bruta integral do TSP e benchmark pela CLI.

Origem fixa: (n−1)! ciclos e n! somas de arestas. Cada ciclo inclui
a volta à origem; as duas orientações são contadas.
"""

import argparse
import csv
import math
import random
import time
import json
import platform
import statistics
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from numbers import Real


# ----------------------------------------------------------------------
# Modelagem do grafo
# ----------------------------------------------------------------------

def gerar_cidades(n, semente=42):
    """Gera n cidades com coordenadas (x, y) aleatórias num plano 100 x 100."""
    rng = random.Random(semente + n)
    return [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(n)]


def matriz_de_custos(cidades):
    """Matriz d[i][j] = distância euclidiana entre as cidades i e j."""
    n = len(cidades)
    d = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                (x1, y1), (x2, y2) = cidades[i], cidades[j]
                d[i][j] = math.hypot(x1 - x2, y1 - y2)
    return d


# ----------------------------------------------------------------------
# Geração de permutações (implementação própria, sem itertools)
# ----------------------------------------------------------------------

def permutacoes(elementos):
    """
    Gera todas as permutações da lista por backtracking (trocas in-place).
    Produz len(elementos)! permutações.
    """
    lista = list(elementos)
    k = len(lista)

    def backtrack(inicio):
        if inicio == k:
            yield tuple(lista)
            return
        for i in range(inicio, k):
            lista[inicio], lista[i] = lista[i], lista[inicio]
            yield from backtrack(inicio + 1)
            lista[inicio], lista[i] = lista[i], lista[inicio]

    yield from backtrack(0)


# ----------------------------------------------------------------------
# Avaliação de uma rota - Θ(n)
# ----------------------------------------------------------------------

def custo_da_rota(rota, d, contador):
    """
    Soma os custos das n arestas do ciclo: rota[0]->rota[1]->...->rota[n-1]->rota[0].
    'contador' acumula quantas arestas foram somadas (para validar Θ(n) por rota).
    """
    n = len(rota)
    total = 0.0
    for i in range(n):
        total += d[rota[i]][rota[(i + 1) % n]]
        contador["arestas"] += 1
    return total


# ----------------------------------------------------------------------
# Força bruta
# ----------------------------------------------------------------------

def validar_matriz(d):
    """API: matriz completa n >= 3, real, finita, não negativa; diagonal zero.

    Matrizes assimétricas são aceitas. Não modifica a entrada.
    """
    if not isinstance(d, (list, tuple)) or len(d) < 3:
        raise ValueError("a matriz deve ter pelo menos 3 cidades")
    n = len(d)
    for i, linha in enumerate(d):
        if not isinstance(linha, (list, tuple)) or len(linha) != n:
            raise ValueError("a matriz deve ser quadrada")
        for j, valor in enumerate(linha):
            if isinstance(valor, bool) or not isinstance(valor, Real):
                raise ValueError("os custos devem ser números reais")
            try:
                valido = math.isfinite(valor) and valor >= 0
            except OverflowError:
                valido = False
            if not valido or (i == j and valor != 0):
                raise ValueError("custos devem ser finitos, não negativos e a diagonal zero")
    if max(map(max, d)) > sys.float_info.max / n:
        raise ValueError("custos grandes demais para somar um ciclo em ponto flutuante")


def tsp_forca_bruta(d, fixar_inicio=True):
    """
    Resolve o TSP testando todas as rotas.

    fixar_inicio=True  -> fixa v1 (índice 0) e permuta as n-1 restantes: (n-1)! rotas
    fixar_inicio=False -> permuta todas as n cidades: n! rotas (versão sem a redução)

    Retorna (melhor_rota, melhor_custo, contador).
    """
    validar_matriz(d)
    n = len(d)
    contador = {"rotas": 0, "arestas": 0}
    melhor_custo = math.inf
    melhor_rota = None

    if fixar_inicio:
        for perm in permutacoes(range(1, n)):
            rota = [0] + list(perm)
            contador["rotas"] += 1
            c = custo_da_rota(rota, d, contador)
            if c < melhor_custo:
                melhor_custo, melhor_rota = c, rota[:]
    else:
        for perm in permutacoes(range(n)):
            contador["rotas"] += 1
            c = custo_da_rota(perm, d, contador)
            if c < melhor_custo:
                melhor_custo, melhor_rota = c, list(perm)

    esperadas = math.factorial(n - 1 if fixar_inicio else n)
    assert contador["rotas"] == esperadas
    assert contador["arestas"] == n * esperadas
    return melhor_rota, melhor_custo, contador


# Benchmark: somente o solver está no intervalo cronometrado.

def benchmark(n_min, n_max, repeticoes, fixar_inicio=True, semente=42,
              amostras=None):
    if n_min < 3 or n_max < n_min or repeticoes < 1:
        raise ValueError("use 3 <= nmin <= nmax e repeticoes >= 1")
    if amostras is None:
        amostras = []
    modo = "fixo" if fixar_inicio else "sem_fixar"
    for n in range(n_min, n_max + 1):
        d = matriz_de_custos(gerar_cidades(n, semente))
        if n <= 5:
            tsp_forca_bruta(d, fixar_inicio)  # uma execução não cronometrada
        for rep in range(1, repeticoes + 1):
            t0 = time.perf_counter()
            rota, custo, cont = tsp_forca_bruta(d, fixar_inicio)
            tempo = time.perf_counter() - t0
            amostras.append(dict(n=n, modo=modo, repeticao=rep, tempo_s=tempo,
                rotas_observadas=cont["rotas"], arestas_observadas=cont["arestas"],
                custo_otimo=custo, rota_otima=" -> ".join(
                    f"v{x+1}" for x in rota + [rota[0]])))
        print(f"n={n:2} {modo}: mediana={statistics.median([a['tempo_s'] for a in amostras if a['n']==n and a['modo']==modo]):.6f} s", flush=True)
    return resumir(amostras)


def resumir(amostras):
    linhas = []
    for n, modo in sorted({(a["n"], a["modo"]) for a in amostras}):
        grupo = [a for a in amostras if a["n"] == n and a["modo"] == modo]
        tempos = [a["tempo_s"] for a in grupo]
        rotas = math.factorial(n-1 if modo == "fixo" else n)
        assert all(a["rotas_observadas"] == rotas and a["arestas_observadas"] == n*rotas for a in grupo)
        linhas.append(dict(n=n, modo=modo, repeticoes_concluidas=len(grupo),
            tempo_s=statistics.median(tempos), minimo_s=min(tempos), maximo_s=max(tempos),
            rotas_observadas_por_execucao=grupo[0]["rotas_observadas"],
            arestas_observadas_por_execucao=grupo[0]["arestas_observadas"],
            rotas_esperadas_por_execucao=rotas, arestas_esperadas_por_execucao=n*rotas,
            custo_otimo=grupo[0]["custo_otimo"], rota_otima=grupo[0]["rota_otima"]))
    return linhas


def calibrar_c(resultados):
    """MQ sem intercepto: c = soma(n! * mediana) / soma((n!)²).

    Usa todos os pontos fixos completos, sem descartar tempos pequenos.
    """
    pts = [(math.factorial(r["n"]), r["tempo_s"]) for r in resultados if r["modo"] == "fixo"]
    return sum(f*t for f,t in pts) / sum(f*f for f,t in pts) if pts else None


def escrever_csv(linhas, caminho, campos=None):
    with Path(caminho).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos or list(linhas[0]), delimiter=";")
        w.writeheader()
        w.writerows(linhas)


def salvar_csv(resultados, c, caminho):
    linhas = [{**r, "tempo_modelo_c_n_fatorial_s": c*math.factorial(r["n"]) if c is not None and r["modo"] == "fixo" else ""} for r in resultados]
    escrever_csv(linhas, caminho, list(linhas[0]) if linhas else ["n", "modo", "tempo_s", "tempo_modelo_c_n_fatorial_s"])


def tabela_extrapolada(c, n_ate=20, medidos=()):
    if c is None:
        return []
    return [dict(n=n, rotas_fixas=math.factorial(n-1), rotas_sem_fixar=math.factorial(n),
        arestas_fixas=math.factorial(n), arestas_sem_fixar=n*math.factorial(n),
        tempo_estimado_s=c*math.factorial(n), natureza="ajuste_na_amostra" if n in medidos else "estimativa_extrapolada")
        for n in range(3, max(n_ate, max(medidos, default=3))+1)]


def plotar(resultados, c, caminho, resultados_sem_fixar=None):
    if c is None:
        return False
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("Gráfico obrigatório NÃO produzido. Instale: python -m pip install -r requirements.txt")
        return False
    fixos = [r for r in resultados if r["modo"] == "fixo"]
    sem = resultados_sem_fixar or [r for r in resultados if r["modo"] == "sem_fixar"]
    ns = [r["n"] for r in fixos]
    xs = [x/10 for x in range(min(ns)*10, max(ns)*10+1)]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    try:
        for ax, log in zip(axes, (False, True)):
            ax.plot(ns, [r["tempo_s"] for r in fixos], "o", label="Mediana medida, v1 fixa")
            ax.plot(xs, [c*math.gamma(x+1) for x in xs], label=f"Ajuste c·n!, c={c:.3e} s")
            if sem:
                ax.plot([r["n"] for r in sem], [r["tempo_s"] for r in sem], "s--", label="Mediana medida, sem fixar")
            ax.set(xlabel="Número de cidades (n)", ylabel="Tempo do solver (s)", title="Escala logarítmica" if log else "Escala linear")
            ax.set_xticks(ns)
            if log:
                ax.set_yscale("log")
            ax.grid(alpha=.3)
            ax.legend()
        fig.tight_layout()
        fig.savefig(caminho, dpi=150)
    finally:
        plt.close(fig)
    return True


def demo(n):
    if n < 3:
        raise ValueError("demo exige n >= 3")
    d = matriz_de_custos(gerar_cidades(n))
    rota, custo, cont = tsp_forca_bruta(d)
    print("Matriz de custos:")
    for linha in d:
        print(" ".join(f"{x:.4f}" for x in linha))
    print("Rota ótima:", " -> ".join(f"v{x+1}" for x in rota+[rota[0]]))
    print("Custo:", custo, "Contagens:", cont)


def main(argv=None):
    p = argparse.ArgumentParser(description="TSP: força bruta didática e medições reais")
    p.add_argument("--nmin", type=int, default=3)
    p.add_argument("--nmax", type=int, default=10)
    p.add_argument("--repeticoes", type=int, default=3)
    p.add_argument("--sem-fixar", action="store_true")
    p.add_argument("--nmax-sem-fixar", type=int, default=8)
    p.add_argument("--semente", type=int, default=42)
    p.add_argument("--saida", type=Path, default=Path("resultados"))
    p.add_argument("--demo", type=int)
    args = p.parse_args(argv)
    if args.nmin < 3 or args.nmax < args.nmin:
        p.error("exige 3 <= nmin <= nmax")
    if args.repeticoes < 1:
        p.error("repeticoes deve ser >= 1")
    if args.nmax_sem_fixar < 3:
        p.error("nmax-sem-fixar deve ser >= 3")
    if args.demo is not None:
        if args.demo < 3:
            p.error("demo exige n >= 3")
        demo(args.demo)
        return 0
    agora = datetime.now(timezone(timedelta(hours=-3)))
    pasta = args.saida / agora.strftime("execucao_%Y%m%d_%H%M%S_%f")
    pasta.mkdir(parents=True, exist_ok=False)
    amostras = []
    interrompido = False
    try:
        benchmark(args.nmin, args.nmax, args.repeticoes, True, args.semente, amostras)
        if args.sem_fixar and args.nmin <= args.nmax_sem_fixar:
            benchmark(args.nmin, min(args.nmax, args.nmax_sem_fixar), args.repeticoes, False, args.semente, amostras)
    except KeyboardInterrupt:
        interrompido = True
        print("Interrompido: salvando apenas repetições completas.")
    resultados = resumir(amostras)
    c = calibrar_c(resultados)
    escrever_csv(amostras, pasta/"repeticoes.csv", list(amostras[0]) if amostras else ["n", "modo", "repeticao", "tempo_s"])
    salvar_csv(resultados, c, pasta/"resultados_tsp.csv")
    proj = tabela_extrapolada(c, medidos=[r["n"] for r in resultados if r["modo"] == "fixo"])
    escrever_csv(proj, pasta/"projecoes.csv", list(proj[0]) if proj else ["n", "tempo_estimado_s", "natureza"])
    grafico = plotar(resultados, c, pasta/"grafico_tsp.png")
    meta = dict(inicio=agora.isoformat(), fim=datetime.now(agora.tzinfo).isoformat(),
        python=sys.version, sistema=platform.platform(), processador=platform.processor() or None,
        argumentos={k:str(v) if isinstance(v, Path) else v for k,v in vars(args).items()},
        estatistica="mediana", c=c, ajuste="MQ sem intercepto, todos os pontos fixos completos",
        contagens="por execução completa; arestas incrementadas dentro do laço",
        aquecimento="uma execução por n e modo para n <= 5; fora dos tempos",
        cronometro="perf_counter; somente solver, incluindo validação e asserções",
        interrompido=interrompido, grafico_produzido=grafico,
        repeticoes_concluidas=len(amostras),
        instancias={str(n):matriz_de_custos(gerar_cidades(n,args.semente)) for n in sorted({a["n"] for a in amostras})})
    (pasta/"metadados.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Saídas:", pasta)
    return 130 if interrompido else 0


if __name__ == "__main__":
    raise SystemExit(main())
