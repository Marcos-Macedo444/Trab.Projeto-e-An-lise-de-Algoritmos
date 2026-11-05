"""
TSP - Algoritmos mais eficientes que a força bruta
===================================================

1) Held-Karp (programação dinâmica)  -> EXATO, O(n² · 2ⁿ) tempo, O(n · 2ⁿ) memória
   Sempre encontra a rota de custo mínimo, como a força bruta, mas evita recalcular
   sub-rotas: guarda o melhor custo para "visitei o conjunto S e estou na cidade j".

2) Vizinho Mais Próximo + 2-opt      -> HEURÍSTICA: busca local sem garantia polinomial até convergir
   Constrói uma rota gulosa (sempre vai para a cidade mais próxima ainda não visitada)
   e depois a melhora desfazendo cruzamentos (2-opt). Muito rápida, resolve centenas
   de cidades em muitos casos, mas NÃO garante a rota ótima.

Uso:
    python tsp_eficiente.py                 # compara os 3 algoritmos e gera o gráfico
    python tsp_eficiente.py --validar       # confere que Held-Karp == força bruta (n=3..10)
"""

import argparse
import math
import time
import statistics

from tsp_forca_bruta import gerar_cidades, matriz_de_custos, tsp_forca_bruta, validar_matriz


# ----------------------------------------------------------------------
# 1) Held-Karp - exato
# ----------------------------------------------------------------------

def tsp_held_karp(d):
    """
    dp[S][j] = menor custo de sair de v1 (índice 0), visitar exatamente as cidades do
    conjunto S (bitmask sobre as cidades 1..n-1) e terminar na cidade j ∈ S.

    Recorrência:
        dp[{j}][j]   = d[0][j]
        dp[S][j]     = min_{k ∈ S, k ≠ j} dp[S - {j}][k] + d[k][j]
    Resposta:
        min_j dp[TODAS][j] + d[j][0]
    """
    validar_matriz(d)
    n = len(d)
    if n == 1:
        return [0], 0.0
    m = n - 1                      # cidades além de v1
    TOTAL = 1 << m
    INF = math.inf
    dp = [[INF] * m for _ in range(TOTAL)]
    pai = [[-1] * m for _ in range(TOTAL)]

    for j in range(m):
        dp[1 << j][j] = d[0][j + 1]

    for S in range(1, TOTAL):
        for j in range(m):
            if not (S >> j) & 1:
                continue
            custo_sj = dp[S][j]
            if custo_sj == INF:
                continue
            # estende a rota indo de j para uma cidade k ainda fora de S
            for k in range(m):
                if (S >> k) & 1:
                    continue
                S2 = S | (1 << k)
                novo = custo_sj + d[j + 1][k + 1]
                if novo < dp[S2][k]:
                    dp[S2][k] = novo
                    pai[S2][k] = j

    CHEIO = TOTAL - 1
    melhor, ultimo = INF, -1
    for j in range(m):
        c = dp[CHEIO][j] + d[j + 1][0]
        if c < melhor:
            melhor, ultimo = c, j

    # reconstrói a rota de trás para frente
    rota, S, j = [], CHEIO, ultimo
    while j != -1:
        rota.append(j + 1)
        anterior = pai[S][j]
        S ^= (1 << j)
        j = anterior
    rota.append(0)
    rota.reverse()
    return rota, melhor


# ----------------------------------------------------------------------
# 2) Vizinho mais próximo + 2-opt - heurística
# ----------------------------------------------------------------------

def custo(rota, d):
    return sum(d[rota[i]][rota[(i + 1) % len(rota)]] for i in range(len(rota)))


def vizinho_mais_proximo(d, inicio=0):
    """Guloso: a partir de v1, vai sempre para a cidade não visitada mais próxima. Θ(n²)."""
    validar_matriz(d)
    n = len(d)
    if not isinstance(inicio, int) or isinstance(inicio, bool) or not 0 <= inicio < n:
        raise ValueError("inicio deve ser um índice de cidade válido")
    rota = [inicio]
    visitado = [False] * n
    visitado[inicio] = True
    atual = inicio
    for _ in range(n - 1):
        prox = min((c for c in range(n) if not visitado[c]), key=lambda c: d[atual][c])
        rota.append(prox)
        visitado[prox] = True
        atual = prox
    return rota


def dois_opt(rota, d):
    """
    Melhoria local: para cada par de arestas (a,b) e (c,e), testa trocá-las por (a,c) e (b,e),
    o que equivale a inverter o trecho entre elas. Exige simetria exata.
    Examina O(n²) pares por passada; delta O(1), inversão Python O(n).
    Uma passada custa até O(n³). O número de passadas até convergência
    não tem garantia polinomial. Busca local, sem garantia de ótimo.
    """
    validar_matriz(d)
    if any(d[i][j] != d[j][i] for i in range(len(d)) for j in range(i)):
        raise ValueError("2-opt exige matriz simétrica")
    if len(rota) != len(d) or sorted(rota) != list(range(len(d))):
        raise ValueError("rota deve conter cada cidade exatamente uma vez")
    rota = list(rota)
    n = len(rota)
    melhorou = True
    while melhorou:
        melhorou = False
        for i in range(n - 1):
            for k in range(i + 2, n if i > 0 else n - 1):
                a, b = rota[i], rota[i + 1]
                c, e = rota[k], rota[(k + 1) % n]
                ganho = d[a][c] + d[b][e] - d[a][b] - d[c][e]
                if ganho < -1e-10:
                    rota[i + 1:k + 1] = reversed(rota[i + 1:k + 1])
                    melhorou = True
    return rota


def tsp_heuristica(d):
    rota = dois_opt(vizinho_mais_proximo(d), d)
    return rota, custo(rota, d)


# ----------------------------------------------------------------------
# Experimentos
# ----------------------------------------------------------------------

def erro_percentual(obtido, otimo):
    """Ótimo zero: 0% se obtido zero; indefinido (None) caso contrário."""
    if otimo == 0:
        return 0.0 if obtido == 0 else None
    return 100 * (obtido - otimo) / otimo


def formatar_erro(obtido, otimo):
    erro = erro_percentual(obtido, otimo)
    return "indefinido (ótimo zero)" if erro is None else f"{erro:.2f}%"


def cronometrar(f, *args, repeticoes=3):
    tempos = []
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        r = f(*args)
        tempos.append(time.perf_counter() - t0)
    return r, statistics.median(tempos)


def validar(n_max=10):
    print("\n=== Validação: Held-Karp e heurística vs. força bruta ===")
    print(f"{'n':>3} | {'força bruta':>12} | {'Held-Karp':>12} | {'heurística':>12} | HK ótimo? | erro heur.")
    for n in range(3, n_max + 1):
        d = matriz_de_custos(gerar_cidades(n))
        _, cb, _ = tsp_forca_bruta(d)
        _, ch = tsp_held_karp(d)
        _, cg = tsp_heuristica(d)
        print(f"{n:>3} | {cb:>12.4f} | {ch:>12.4f} | {cg:>12.4f} | "
              f"{'sim' if abs(cb - ch) < 1e-9 else 'NÃO':>9} | {formatar_erro(cg, cb):>12}")


def comparar(n_bruta=10, n_hk=16, n_heur=200):
    linhas = []
    print("\n=== Comparação: mediana de 3 execuções por método, perf_counter somente solver, sem aquecimento ===")
    print(f"{'n':>4} | {'força bruta':>12} | {'Held-Karp':>12} | {'heurística':>12} | erro heur. vs ótimo")
    ns = list(range(4, n_hk + 1)) + [25, 50, 100, n_heur]
    for n in ns:
        d = matriz_de_custos(gerar_cidades(n))
        tb = th = None
        otimo = None
        if n <= n_bruta:
            (_, otimo, _), tb = cronometrar(tsp_forca_bruta, d)
        if n <= n_hk:
            (_, otimo), th = cronometrar(tsp_held_karp, d)
        (_, cg), tg = cronometrar(tsp_heuristica, d)
        erro = formatar_erro(cg, otimo) if otimo is not None else "—"
        f = lambda t: f"{t:12.5f}" if t is not None else f"{'—':>12}"
        print(f"{n:>4} | {f(tb)} | {f(th)} | {f(tg)} | {erro}")
        linhas.append((n, tb, th, tg, erro))
    return linhas


def plotar(linhas, caminho="grafico_comparacao.png"):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib não instalado: gráfico não gerado.")
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    for idx, nome, estilo in [(1, "Força bruta  Θ(n!)", "o-"),
                              (2, "Held-Karp  O(n²·2ⁿ)", "s-"),
                              (3, "Vizinho mais próximo + 2-opt", "^-")]:
        pts = [(l[0], l[idx]) for l in linhas if l[idx] is not None and l[0] <= 20]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], estilo, label=nome)
    ax.set_yscale("log")
    ax.set_xlabel("Número de cidades (n)")
    ax.set_ylabel("Tempo de execução (s, escala log)")
    ax.set_title("TSP: força bruta vs. algoritmos mais eficientes")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(caminho, dpi=150)
    plt.close(fig)
    print(f"Gráfico salvo em: {caminho}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--validar", action="store_true", help="só confere os resultados contra a força bruta")
    p.add_argument("--nbruta", type=int, default=10)
    p.add_argument("--nhk", type=int, default=16)
    args = p.parse_args()
    if args.nbruta < 3 or args.nhk < 3:
        p.error("nbruta e nhk devem ser >= 3")
    validar(min(args.nbruta, 10))
    if args.validar:
        return
    plotar(comparar(args.nbruta, args.nhk))


if __name__ == "__main__":
    main()
