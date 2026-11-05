"""Um processo por grupo; nenhum IPC, callback ou clock no laço acadêmico."""
import time


def preparar_solver(matriz, grupo):
    from tsp_forca_bruta import tsp_forca_bruta
    from tsp_eficiente import tsp_held_karp, vizinho_mais_proximo, tsp_heuristica
    alg = grupo['algoritmo']
    if alg == 'bruta':
        return tsp_forca_bruta, (matriz, grupo['modo'] == 'fixo'), 'triplo'
    if alg == 'held_karp':
        return tsp_held_karp, (matriz,), 'par'
    elif alg == 'guloso':
        return vizinho_mais_proximo, (matriz,), 'rota'
    elif alg == 'dois_opt':
        return tsp_heuristica, (matriz,), 'par'
    else:
        raise ValueError('Algoritmo desconhecido.')


def executar_grupo(canal, matriz, grupo, solver=None, clock=None):
    """Entradas injetáveis só para testar limites do cronômetro/protocolo."""
    clock = clock or time.perf_counter
    try:
        # Imports, seleção do algoritmo e preparação dos argumentos fora do clock.
        if solver is None:
            solver, argumentos, formato = preparar_solver(matriz, grupo)
        else:
            argumentos, formato = (matriz, grupo), 'triplo'
        if grupo['algoritmo'] == 'bruta' and grupo['n'] <= 5:
            canal.send({'evento': 'aquecendo'})
            solver(*argumentos)
        # Métodos opcionais: sem aquecimento, protocolo registrado nos metadados.
        canal.send({'evento': 'pronto'})
        while True:
            comando = canal.recv()
            if comando.get('comando') == 'encerrar':
                break
            if comando.get('comando') != 'executar':
                raise ValueError('Comando de worker inválido.')
            t0 = clock()
            resultado = solver(*argumentos)
            t1 = clock()
            # Tudo a partir daqui fica fora da medição científica.
            if formato == 'triplo':
                rota, valor, contador = resultado
            elif formato == 'par':
                (rota, valor), contador = resultado, None
            else:
                from tsp_eficiente import custo
                rota, contador = resultado, None
                valor = custo(rota, matriz)
            amostra = {k: grupo[k] for k in ('n', 'modo', 'algoritmo')}
            amostra.update(repeticao=comando['repeticao'], tempo_s=t1-t0,
                rota_indices=list(rota), custo=valor,
                rotas_observadas=contador['rotas'] if contador else None,
                arestas_observadas=contador['arestas'] if contador else None)
            canal.send({'evento': 'resultado', 'amostra': amostra})
    except (EOFError, BrokenPipeError):
        pass
    except BaseException as exc:
        try:
            canal.send({'evento': 'erro', 'mensagem': f'{type(exc).__name__}: {exc}'})
        except (OSError, EOFError):
            pass
    finally:
        canal.close()
