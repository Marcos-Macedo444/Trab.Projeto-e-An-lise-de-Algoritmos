"""Validação dos alvos de exclusão: somente execuções registradas no histórico."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat


def _sem_vinculo(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('Exclusão recusada: há link simbólico ou ponto de junção no experimento.')


def validar_diretorio(path, base):
    """Confere caminhos absolutos e árvore antes de qualquer remoção recursiva."""
    path, base = Path(path), Path(base)
    _sem_vinculo(base)
    _sem_vinculo(path)
    raiz, alvo = base.resolve(strict=True), path.resolve(strict=True)
    if raiz == Path(raiz.anchor) or alvo.parent != raiz or alvo == raiz:
        raise ValueError('Exclusão recusada: diretório fora da base de experimentos.')
    if not alvo.is_dir():
        raise ValueError('O alvo de exclusão deve ser uma pasta de experimento.')
    def visitar(diretorio):
        with os.scandir(diretorio) as entradas:
            for entrada in entradas:
                _sem_vinculo(Path(entrada.path))
                if entrada.is_dir(follow_symlinks=False):
                    visitar(Path(entrada.path))
    visitar(alvo)
    return alvo


def alvos_registrados(manager):
    alvos = []
    for ident in manager.tarefas:
        if not re.fullmatch(r'web_[A-Za-z0-9_]+', ident):
            raise ValueError('Identificador de experimento web inválido.')
        alvos.append((ident, manager.base/ident, manager.base, 'web'))
    bases_cli = [manager.raiz_cli/'resultados', manager.raiz_cli/'meus_resultados']
    for ident, registro in manager.cli.items():
        if registro.get('protegido'):
            continue
        pasta = registro['arquivos']['metadados.json'].parent
        if pasta.parent not in bases_cli or not re.fullmatch(r'execucao_[0-9_]+', pasta.name):
            raise ValueError('Diretório CLI não pertence às bases administradas.')
        alvos.append((ident, pasta, pasta.parent, 'cli'))
    vistos = set()
    conferidos = []
    for ident, pasta, base, origem in alvos:
        alvo = validar_diretorio(pasta, base)
        if alvo in vistos:
            raise ValueError('Diretório de experimento registrado mais de uma vez.')
        vistos.add(alvo)
        conferidos.append((ident, alvo, base.resolve(), origem))
    return conferidos


def token_alvos(alvos):
    versao = [(ident, str(path), path.stat().st_mtime_ns) for ident,path,_,_ in alvos]
    return hashlib.sha256(json.dumps(sorted(versao), ensure_ascii=False).encode('utf-8')).hexdigest()
