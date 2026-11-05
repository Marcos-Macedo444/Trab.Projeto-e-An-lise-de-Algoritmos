"""Prepara distribuições usando somente código e evidências selecionadas."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARQUIVOS = ['.gitignore', '.gitattributes', 'README.md', 'RELATORIO.md', 'DADOS_ACADEMICOS.md',
    'RESULTADOS_SELECIONADOS.md', 'LICENCAS_DEPENDENCIAS.md', 'ALTERACOES.md',
    'requirements.txt', 'requirements-web.txt', 'iniciar_web.py', 'iniciar_web.bat',
    'tsp_forca_bruta.py', 'tsp_eficiente.py', 'tsp_experimentos.py']
PASTAS = ['web_local', 'tests', 'tools', 'docs', 'evidencias']
PESSOAL = re.compile(r'(?<![A-Za-z0-9])(?:[A-Za-z]:[\\/]|/(?:Users|home)/)', re.I)


def fontes():
    arquivos = [ROOT/n for n in ARQUIVOS]
    for nome in PASTAS:
        arquivos.extend(p for p in (ROOT/nome).rglob('*') if p.is_file()
            and not any(x in p.parts for x in ('__pycache__', 'validacao_curta'))
            and p.suffix.lower() not in ('.zip', '.pyc', '.pyo', '.tmp', '.lock'))
    return sorted(arquivos)


def manifesto(conteudos, nome):
    return json.dumps(dict(pacote=nome, preparado_em=datetime.now().astimezone().isoformat(),
        arquivos=[dict(arquivo=n, sha256=hashlib.sha256(b).hexdigest())
                  for n,b in sorted(conteudos.items())]),ensure_ascii=False,indent=2).encode('utf-8')


def gerar(identificacao=None, destino=ROOT):
    destino=Path(destino); destino.mkdir(parents=True,exist_ok=True)
    base={p.relative_to(ROOT).as_posix():p.read_bytes() for p in fontes()}
    for professor in (False, True):
        nome='TSP_Entrega_Professor' if professor else 'TSP_Compartilhamento_Grupo'
        dados=dict(base)
        if professor and identificacao:
            dados['DADOS_ACADEMICOS.md']=Path(identificacao).read_bytes()
        for n,b in dados.items():
            if n.endswith(('.md','.txt','.py','.json','.html','.js','.css','.csv','.bat')):
                if PESSOAL.search(b.decode('utf-8')):
                    raise ValueError('Caminho pessoal em '+n)
        dados['DISTRIBUICAO.json']=manifesto(dados,nome)
        saida=destino/(nome+'.zip')
        with zipfile.ZipFile(saida,'w',zipfile.ZIP_DEFLATED) as z:
            for n,b in sorted(dados.items()):z.writestr(nome+'/'+n,b)
        with zipfile.ZipFile(saida) as z:assert z.testzip() is None
        print(nome+'.zip: '+str(saida.stat().st_size)+' bytes')
    (ROOT/'DISTRIBUICAO.json').write_bytes(manifesto(base,'Repositorio'))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--identificacao',type=Path,help='Identificação completa para a distribuição acadêmica')
    p.add_argument('--destino',type=Path,default=ROOT)
    args=p.parse_args();gerar(args.identificacao,args.destino)
