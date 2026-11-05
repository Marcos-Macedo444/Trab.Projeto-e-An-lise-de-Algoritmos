"""Coordenador local: aceitação serial, checkpoints e processos spawn isolados."""
import copy
from datetime import datetime
import hashlib
import importlib.metadata
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import threading
import time
import uuid
import zipfile
import shutil

import tsp_forca_bruta as b
from tsp_experimentos import (ROOT, SCHEMA, ATIVOS, AMOSTRA_CAMPOS, PROJECAO_CAMPOS, RESUMO_CAMPOS,
    validar_config, planejar, instancias, validar_amostra, analisar, amostras_csv,
    atomico, hashes_codigo, api_exata, TETOS_PADRAO)
from web_local.worker import executar_grupo


def agora():
    return datetime.now().astimezone().isoformat()


def versao_pacote(nome):
    try:
        return importlib.metadata.version(nome)
    except importlib.metadata.PackageNotFoundError:
        return None


class Ocupado(RuntimeError):
    pass


class Cancelado(Exception):
    pass


class LimiteTempo(Exception):
    pass


class BloqueioLocal:
    """Lock de SO: não depende de PID possivelmente reutilizado; liberado ao morrer."""
    def __init__(self, caminho):
        self.f = Path(caminho).open('a+b')
        if self.f.seek(0, 2) == 0:
            self.f.write(b'0')
            self.f.flush()
        self.f.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            raise Ocupado('Outra instância já usa esta pasta de tarefas. Encerre-a primeiro.') from None

    def close(self):
        if not self.f.closed:
            if os.name == 'nt':
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()


class Gerenciador:
    def __init__(self, base=None, tetos=None, worker=executar_grupo, raiz_cli=ROOT):
        self.base = Path(base or ROOT/'resultados_web').resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.bloqueio = BloqueioLocal(self.base/'.instancia.lock')
        self.lock = threading.RLock()
        self.ctx = multiprocessing.get_context('spawn')
        self.worker = worker
        self.tetos = dict(tetos or TETOS_PADRAO)
        self.raiz_cli = Path(raiz_cli)
        self.tarefas = {}
        self.ativa = None
        self.thread = None
        self.filho = None
        self.encerrado = False
        try:
            from web_local.historico import carregar_cli
            self.cli = carregar_cli(self.raiz_cli)
            self._recuperar()
        except BaseException:
            self.bloqueio.close()
            raise

    def _pasta(self, t):
        return self.base/t['id']

    def _manifesto(self, t):
        campos = ('id', 'config', 'inicio', 'fim', 'estado', 'razao', 'sequencia',
                  'concluidas', 'planejadas', 'atual', 'cancelamento', 'arquivos',
                  'duracao_total_s', 'origem', 'interrupcao')
        atomico(self._pasta(t)/'estado.json', {'schema': SCHEMA, **{k:t[k] for k in campos}})

    def _checkpoint(self, t, amostras):
        dados = {k:copy.deepcopy(t[k]) for k in ('id', 'config', 'inicio', 'instancias',
                    'plano', 'ambiente', 'hashes_codigo')}
        dados.update(schema=SCHEMA, sequencia=len(amostras), amostras=amostras)
        digest = hashlib.sha256(json.dumps(dados, sort_keys=True, ensure_ascii=False,
                                          allow_nan=False).encode('utf-8')).hexdigest()
        path = self._pasta(t)/f'checkpoint_{len(amostras):06d}.json'
        atomico(path, {'sha256': digest, 'dados': dados})
        # Um checkpoint anterior é conservado para recuperação de arquivo corrompido.
        for antigo in sorted(self._pasta(t).glob('checkpoint_*.json'))[:-2]:
            try:
                antigo.unlink()
            except OSError:
                # Retenção extra é preferível a rejeitar um checkpoint já persistido.
                pass

    def _novo_registro(self, dados):
        return {**dados, 'amostras': dados.get('amostras', []), 'origem': 'web',
            'estado': 'pendente', 'razao': None, 'fim': None, 'atual': None,
            'cancelamento': False, 'arquivos': [], 'duracao_total_s': 0.0, 'interrupcao': None,
            'concluidas': len(dados.get('amostras', [])),
            'sequencia': len(dados.get('amostras', [])),
            'planejadas': sum(g['repeticoes'] for g in dados['plano'])}

    def _recuperar(self):
        indice = self.raiz_cli/'evidencias/indice.json'
        ignorados = set(json.loads(indice.read_text(encoding='utf-8')).get('ignorar_historico', [])) if indice.is_file() else set()
        for pasta in sorted(self.base.glob('web_*')):
            if not pasta.is_dir():
                continue
            if pasta.name in self.cli or pasta.name in ignorados:
                continue
            t = None
            for p in sorted(pasta.glob('checkpoint_*.json'), reverse=True):
                try:
                    envelope = json.loads(p.read_text(encoding='utf-8'))
                    d = envelope['dados']
                    digest = hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False,
                                             allow_nan=False).encode('utf-8')).hexdigest()
                    if digest != envelope['sha256'] or d['schema'] != SCHEMA or d['id'] != pasta.name or d['sequencia'] != len(d['amostras']):
                        raise ValueError('Checkpoint inconsistente')
                    esperadas = [(g, r) for g in d['plano'] for r in range(1, g['repeticoes']+1)]
                    if len(d['amostras']) > len(esperadas):
                        raise ValueError('Amostras excedem o plano')
                    for a, (g, r) in zip(d['amostras'], esperadas):
                        validar_amostra(a, g, r, d['instancias'][str(g['n'])]['matriz'])
                    t = self._novo_registro(d)
                    break
                except (OSError, ValueError, KeyError, TypeError):
                    continue
            if t is None:
                # Sem checkpoint válido: não inventa configuração, medição ou retomada.
                self.tarefas[pasta.name] = dict(id=pasta.name, origem='web', estado='falhou',
                    razao='Nenhum checkpoint válido; arquivos preservados para inspeção.',
                    config={}, inicio=None, fim=agora(), concluidas=0, planejadas=0,
                    sequencia=0, atual=None, cancelamento=False, arquivos=[],
                    duracao_total_s=0., amostras=[], plano=[], instancias={}, interrupcao=None)
                continue
            try:
                manifesto = json.loads((pasta/'estado.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                manifesto = {}
            terminal = manifesto.get('estado') not in ATIVOS and manifesto.get('estado') in ('concluido', 'cancelado', 'falhou', 'interrompido')
            consistente = manifesto.get('sequencia') == t['sequencia'] and manifesto.get('concluidas') == t['concluidas']
            if terminal and consistente:
                for k in ('estado', 'razao', 'fim', 'arquivos', 'duracao_total_s', 'cancelamento', 'interrupcao'):
                    if k in manifesto:
                        t[k] = manifesto[k]
                # ZIPs de tarefa não são aninhados no ZIP de distribuição. Recria localmente.
                if t['arquivos'] and not (pasta/'tarefa.zip').exists():
                    self._bundle(t)
            else:
                t.update(estado='interrompido', fim=agora(), duracao_total_s=None,
                         razao='Recuperado do último checkpoint válido; cálculo não retomado.')
                try:
                    self._exportar(t, 'interrompido')
                    self._manifesto(t)
                except Exception as exc:
                    t.update(estado='falhou', razao=f'Recuperação preservada; exportação falhou: {exc}')
            self.tarefas[t['id']] = t

    def criar(self, dados):
        config = validar_config(dados, self.tetos)
        plano = planejar(config)
        with self.lock:
            if self.encerrado:
                raise Ocupado('Aplicativo está encerrando.')
            if self.ativa:
                raise Ocupado('Já existe uma tarefa ativa. Aguarde ou cancele-a.')
            ident = 'web_' + datetime.now().strftime('%Y%m%d_%H%M%S_') + uuid.uuid4().hex[:10]
            t = self._novo_registro(dict(id=ident, config=config, plano=plano,
                inicio=agora(), instancias=instancias(config, plano), hashes_codigo=hashes_codigo(),
                ambiente=dict(python=platform.python_version(), sistema=platform.platform(),
                    processador=platform.processor() or None,
                    dependencias={n:versao_pacote(n) for n in ['Flask', 'waitress', 'matplotlib']})))
            self._pasta(t).mkdir()
            self._checkpoint(t, [])
            self._manifesto(t)
            self.tarefas[ident] = t
            self.ativa = ident
            self.thread = threading.Thread(target=self._executar, args=(t,), name='TSP-coordenador', daemon=False)
            self.thread.start()
            return self.snapshot(ident)

    def snapshot(self, ident):
        with self.lock:
            if ident in self.cli:
                return copy.deepcopy(self.cli[ident]['snapshot'])
            t = self.tarefas[ident]
            campos = ('id', 'origem', 'config', 'inicio', 'fim', 'estado', 'razao',
                      'sequencia', 'concluidas', 'planejadas', 'atual', 'arquivos', 'interrupcao')
            s = {k:copy.deepcopy(t[k]) for k in campos}
            s['duracao_total_s'] = (time.monotonic()-t['_inicio_clock']) if t['estado'] in ATIVOS and '_inicio_clock' in t else t['duracao_total_s']
            s['duracao_chamada_s'] = (time.monotonic()-t['_inicio_chamada']) if t['estado'] == 'calculando' and '_inicio_chamada' in t else None
            return s

    def listar(self):
        with self.lock:
            ids = list(self.tarefas) + list(self.cli)
            return dict(ativa=self.ativa, tarefas=[self.snapshot(i) for i in reversed(ids)],
                        tetos=self.tetos)

    def _exclusao_livre(self):
        if self.encerrado or self.ativa or any(t['estado'] in ATIVOS for t in self.tarefas.values()) or (self.thread and self.thread.is_alive()):
            raise Ocupado('Exclusão indisponível durante cálculo, exportação ou finalização. Aguarde o término da tarefa.')

    def prever_exclusao(self):
        from web_local.exclusao import alvos_registrados, token_alvos
        with self.lock:
            self._exclusao_livre()
            alvos = alvos_registrados(self)
            return dict(quantidade=len(alvos), web=sum(a[3]=='web' for a in alvos),
                        cli=sum(a[3]=='cli' for a in alvos),
                        protegidos=sum(r.get('protegido', False) for r in self.cli.values()),
                        confirmacao=token_alvos(alvos))

    def excluir_experimentos(self, confirmacao):
        from web_local.exclusao import alvos_registrados, token_alvos, validar_diretorio
        if not isinstance(confirmacao, str) or len(confirmacao) != 64:
            raise ValueError('Confirmação obrigatória. Consulte a quantidade de experimentos antes de excluir.')
        with self.lock:
            self._exclusao_livre()
            alvos = alvos_registrados(self)  # todos são conferidos antes da primeira remoção
            if confirmacao != token_alvos(alvos):
                raise Ocupado('O histórico mudou. Confira novamente a quantidade antes de confirmar a exclusão.')
            removidos, falhas = 0, []
            for ident, path, base, origem in alvos:
                try:
                    alvo = validar_diretorio(path, base)
                    shutil.rmtree(alvo)
                except OSError:
                    falhas.append(dict(id=ident, erro='Não foi possível remover completamente esta execução. Verifique as permissões e arquivos em uso.'))
                    continue
                (self.tarefas if origem=='web' else self.cli).pop(ident)
                removidos += 1
            return dict(removidos=removidos, falhas=falhas, restantes=len(self.tarefas)+len(self.cli))

    def resultados(self, ident):
        with self.lock:
            if ident in self.cli:
                return copy.deepcopy(self.cli[ident]['resultados'])
            t = self.tarefas[ident]
            amostras = copy.deepcopy(t['amostras'])
            resumo, c, proj = analisar(t['config'], amostras) if t['config'] else ([], None, [])
            for r in resumo:
                r['repeticoes_previstas'] = t['config']['repeticoes']
                r['parcial'] = r['repeticoes_concluidas'] < t['config']['repeticoes']
            return dict(schema=SCHEMA, origem='web', config=t['config'], amostras=amostras,
                        resumo=resumo, c=c, c_provisorio=t['estado'] in ATIVOS,
                        projecoes=proj, instancias=copy.deepcopy(t['instancias']),
                        plano=copy.deepcopy(t['plano']))

    def cancelar(self, ident):
        with self.lock:
            if ident in self.cli:
                raise ValueError('Esta execução histórica não está em andamento.')
            t = self.tarefas[ident]
            if t['estado'] in ATIVOS:
                t['cancelamento'] = True
                t['razao'] = 'Cancelamento solicitado pelo usuário.'
                t['estado'] = 'cancelando'
            return self.snapshot(ident)

    def _fase(self, t, fase, atual=None):
        with self.lock:
            t['estado'] = 'cancelando' if t['cancelamento'] and fase != 'exportando' else fase
            t['atual'] = atual
            if fase == 'calculando':
                t['_inicio_chamada'] = time.monotonic()
            else:
                t.pop('_inicio_chamada', None)
            self._manifesto(t)

    def _registrar_interrupcao(self, t, motivo):
        inicio = t.get('_inicio_chamada')
        t['interrupcao'] = dict(motivo=motivo, chamada=copy.deepcopy(t['atual']),
            duracao_observada_s=time.monotonic()-inicio if inicio is not None else None,
            natureza='Interrupção; duração observada pelo coordenador, sem tempo completo do solver.')

    def _receber(self, t, canal, proc):
        while True:
            with self.lock:
                if t['cancelamento']:
                    self._registrar_interrupcao(t, 'cancelamento')
                    raise Cancelado()
                limite = t['config'].get('limite_segundos', 0)
                if limite and t['estado'] == 'calculando' and time.monotonic()-t['_inicio_chamada'] >= limite:
                    self._registrar_interrupcao(t, 'limite_de_tempo')
                    raise LimiteTempo()
            if canal.poll(.1):
                try:
                    msg = canal.recv()
                except (EOFError, OSError):
                    raise RuntimeError('Worker encerrou o canal sem resultado completo.') from None
                if msg.get('evento') == 'erro':
                    raise RuntimeError(msg.get('mensagem', 'Falha do worker.'))
                return msg
            if not proc.is_alive():
                raise RuntimeError(f'Worker terminou inesperadamente (código {proc.exitcode}).')

    def _aceitar(self, t, a, grupo, rep):
        validar_amostra(a, grupo, rep, t['instancias'][str(grupo['n'])]['matriz'])
        with self.lock:
            # Ordem determinística: cancelamento registrado antes deste lock vence.
            if t['cancelamento']:
                raise Cancelado()
            novas = t['amostras'] + [a]
            self._checkpoint(t, novas)
            t['amostras'] = novas
            t['sequencia'] = t['concluidas'] = len(novas)
            self._manifesto(t)

    @staticmethod
    def _encerrar_filho(proc):
        if proc is None:
            return
        proc.join(.2)
        if proc.is_alive():
            proc.terminate()
            proc.join(2)
        if proc.is_alive():
            proc.kill()
            proc.join(2)
        if proc.is_alive():
            raise RuntimeError('Não foi possível encerrar o worker.')
        proc.close()

    def _executar(self, t):
        t['_inicio_clock'] = time.monotonic()
        terminal = 'concluido'
        try:
            for grupo in t['plano']:
                with self.lock:
                    if t['cancelamento']:
                        raise Cancelado()
                self._fase(t, 'preparando', {**grupo, 'repeticao': 1})
                pai, filho = self.ctx.Pipe(duplex=True)
                proc = self.ctx.Process(target=self.worker,
                    args=(filho, t['instancias'][str(grupo['n'])]['matriz'], grupo))
                try:
                    proc.start()
                    self.filho = proc
                    filho.close()
                    while True:
                        msg = self._receber(t, pai, proc)
                        if msg['evento'] == 'aquecendo':
                            self._fase(t, 'aquecendo', {**grupo, 'repeticao': 0})
                        elif msg['evento'] == 'pronto':
                            break
                        else:
                            raise RuntimeError('Protocolo de preparação inválido.')
                    for rep in range(1, grupo['repeticoes']+1):
                        with self.lock:
                            if t['cancelamento']:
                                raise Cancelado()
                        self._fase(t, 'calculando', {**grupo, 'repeticao': rep})
                        pai.send({'comando': 'executar', 'repeticao': rep})
                        msg = self._receber(t, pai, proc)
                        if msg.get('evento') != 'resultado':
                            raise RuntimeError('Resposta de cálculo inválida.')
                        self._aceitar(t, msg['amostra'], grupo, rep)
                        # O próximo comando só é enviado após checkpoint + manifesto.
                    pai.send({'comando': 'encerrar'})
                finally:
                    pai.close()
                    filho.close()
                    if proc.pid is not None:
                        self._encerrar_filho(proc)
                    self.filho = None
        except Cancelado:
            terminal = 'cancelado'
        except LimiteTempo:
            terminal = 'interrompido'
            t['razao'] = ('Limite de tempo por repetição atingido. A chamada em andamento foi descartada; '
                          'somente chamadas completas anteriores foram preservadas. Não é falha da máquina.')
        except Exception as exc:
            terminal = 'falhou'
            t['razao'] = f'{type(exc).__name__}: {exc}'
        finally:
            try:
                self._fase(t, 'exportando')
                self._exportar(t, terminal)
                with self.lock:
                    if t['cancelamento'] and terminal == 'concluido':
                        terminal = 'cancelado'
                    t.update(estado=terminal, atual=None, fim=agora(),
                             duracao_total_s=time.monotonic()-t['_inicio_clock'])
                    # Inclui cancelamento ocorrido enquanto exportava.
                    atomico(self._pasta(t)/'resultados.json', self.resultados(t['id']))
                    self._metadados(t, terminal)
                    self._bundle(t)
                    self._manifesto(t)
            except Exception as exc:
                with self.lock:
                    t.update(estado='falhou', fim=agora(), atual=None,
                             razao=f'Exportação falhou; checkpoints preservados: {type(exc).__name__}: {exc}',
                             duracao_total_s=time.monotonic()-t['_inicio_clock'])
                    try:
                        permitidos = ['repeticoes.csv','resultados_tsp.csv','projecoes.csv',
                            'comparacao_repeticoes.csv','comparacao_resumo.csv',
                            'resultados.json','metadados.json','grafico_tsp.png']
                        t['arquivos'] = [n for n in permitidos if (self._pasta(t)/n).is_file()]
                        self._metadados(t, 'falhou')
                        if 'metadados.json' not in t['arquivos']:
                            t['arquivos'].append('metadados.json')
                        self._bundle(t)
                        self._manifesto(t)
                    except OSError:
                        pass
            finally:
                with self.lock:
                    self.ativa = None

    def _metadados(self, t, terminal):
        _, c, _ = analisar(t['config'], t['amostras'])
        dados = dict(schema=SCHEMA, origem='web', id=t['id'], inicio=t['inicio'],
            fim=t['fim'] or agora(), fuso=datetime.now().astimezone().tzname(),
            estado=terminal, razao=t['razao'], interrupcao=t.get('interrupcao'), configuracao=t['config'], ambiente=t['ambiente'],
            hashes_codigo=t['hashes_codigo'], sequencia_checkpoint=t['sequencia'],
            repeticoes_concluidas=t['concluidas'], chamadas_planejadas=t['planejadas'],
            estatistica='mediana', c=c, duracao_total_tarefa_s=t['duracao_total_s'],
            cronometro='perf_counter apenas ao redor do solver no filho; inclui validações e contadores internos',
            cronometro_guloso='somente vizinho_mais_proximo; custo do ciclo conferido após parar o relógio',
            aquecimento='força bruta: uma vez no próprio filho por n/modo para n<=5; opcionais: nenhum',
            processo='spawn; um filho por (n, modo, algoritmo), mantido entre repetições; sem paralelismo',
            instancias=t['instancias'],
            contagens=[{k:a[k] for k in ('n','modo','algoritmo','repeticao','rotas_observadas','arestas_observadas')} for a in t['amostras']])
        atomico(self._pasta(t)/'metadados.json', dados)

    def _exportar(self, t, terminal):
        pasta = self._pasta(t)
        resumo, c, proj = analisar(t['config'], t['amostras'])
        nomes = []
        if t['config']['tipo'] == 'comparacao':
            b.escrever_csv(t['amostras'], pasta/'comparacao_repeticoes.csv',
                list(t['amostras'][0]) if t['amostras'] else ['n','algoritmo','repeticao','tempo_s','custo'])
            b.escrever_csv(resumo, pasta/'comparacao_resumo.csv',
                list(resumo[0]) if resumo else ['n','algoritmo','tempo_s','custo'])
            nomes += ['comparacao_repeticoes.csv', 'comparacao_resumo.csv']
        else:
            b.escrever_csv(amostras_csv(t['amostras']), pasta/'repeticoes.csv', AMOSTRA_CAMPOS)
            if resumo:
                b.salvar_csv(resumo, c, pasta/'resultados_tsp.csv')
            else:
                b.escrever_csv([], pasta/'resultados_tsp.csv', RESUMO_CAMPOS)
            b.escrever_csv(proj, pasta/'projecoes.csv', PROJECAO_CAMPOS)
            nomes += ['repeticoes.csv','resultados_tsp.csv','projecoes.csv']
        exportado = dict(schema=SCHEMA, origem='web', config=t['config'],
            amostras=t['amostras'], resumo=resumo, c=c, c_provisorio=False,
            instancias=t['instancias'], projecoes=proj, plano=t['plano'])
        atomico(pasta/'resultados.json', exportado)
        self._metadados(t, terminal)
        nomes += ['resultados.json','metadados.json']
        t['arquivos'] = nomes
        if t['config']['tipo'] != 'comparacao':
            # Nunca há solver ativo neste ponto; somente o coordenador usa matplotlib.
            if b.plotar(resumo, c, pasta/'grafico_tsp.png'):
                t['arquivos'].append('grafico_tsp.png')
            elif c is not None:
                raise RuntimeError('Gráfico obrigatório não produzido. Instale requirements-web.txt.')

    def _bundle(self, t):
        pasta = self._pasta(t)
        nomes = [n for n in t['arquivos'] if n != 'tarefa.zip' and (pasta/n).is_file()]
        tmp = pasta/'tarefa.zip.tmp'
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
            for n in nomes:
                z.write(pasta/n, n)
            for p in sorted(pasta.glob('checkpoint_*.json'))[-1:]:
                z.write(p, p.name)
        os.replace(tmp, pasta/'tarefa.zip')
        t['arquivos'] = nomes + ['tarefa.zip']

    def arquivo(self, ident, nome):
        with self.lock:
            if ident in self.cli:
                return self.cli[ident]['arquivos'].get(nome)
            t = self.tarefas[ident]
            if t['estado'] in ATIVOS or nome not in t['arquivos'] or Path(nome).name != nome:
                return None
            caminho = self._pasta(t)/nome
            return caminho if caminho.is_file() else None

    def close(self):
        with self.lock:
            self.encerrado = True
            if self.ativa:
                self.cancelar(self.ativa)
                self.tarefas[self.ativa]['razao'] = 'Encerramento normal do aplicativo.'
        if self.thread:
            self.thread.join(15)
            if self.thread.is_alive():
                # Não libera a base para um segundo escritor enquanto o coordenador vive.
                raise RuntimeError('Coordenador ainda finalizando; aguarde a exportação.')
        self.bloqueio.close()
