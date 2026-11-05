"""Factory HTTP. Handlers nunca executam solver, PNG ou ZIP."""
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException

from tsp_experimentos import validar_config, planejar, api_exata
from web_local.tarefas import Gerenciador, Ocupado


def create_app(gerenciador=None, **opcoes):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=16384)
    manager = gerenciador or Gerenciador(**opcoes)
    app.extensions['tsp'] = manager

    @app.before_request
    def somente_local():
        host = request.host.split(':')[0].lower()
        if host not in ('127.0.0.1', 'localhost'):
            return jsonify(erro='Host permitido: localhost ou 127.0.0.1.'), 403
        origem = request.headers.get('Origin')
        if origem:
            try:
                url = urlsplit(origem)
                valido = url.scheme == 'http' and url.netloc == request.host and url.hostname in ('127.0.0.1','localhost')
            except ValueError:
                valido = False
            if not valido:
                return jsonify(erro='Origem HTTP não permitida.'), 403
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return jsonify(erro='Requisição de outra origem recusada.'), 403

    @app.after_request
    def cabecalhos(resp):
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'"
        resp.headers['Cache-Control'] = 'no-store'
        return resp

    @app.errorhandler(Exception)
    def erros(exc):
        if isinstance(exc, KeyError):
            return jsonify(erro='Tarefa não encontrada.'), 404
        if isinstance(exc, Ocupado):
            return jsonify(erro=str(exc)), 409
        if isinstance(exc, ValueError):
            return jsonify(erro=str(exc)), 400
        if isinstance(exc, HTTPException):
            return jsonify(erro=exc.description), exc.code
        app.logger.exception('Falha HTTP')
        return jsonify(erro='Falha interna. Consulte o terminal; checkpoints preservados.'), 500

    @app.get('/')
    def pagina():
        return render_template('index.html')

    @app.get('/api/tarefas')
    def lista():
        return jsonify(api_exata(manager.listar()))

    @app.post('/api/planejar')
    def plano():
        config = validar_config(request.get_json(), manager.tetos)
        grupos = planejar(config)
        return jsonify(api_exata(dict(config=config, grupos=grupos,
            chamadas=sum(g['repeticoes'] for g in grupos),
            avisos=(['Crescimento fatorial: esta configuração pode exigir minutos, horas ou mais. '
                     'As contagens do plano são exatas; não representam previsão de duração.']
                    if any(g['n'] >= 12 for g in grupos) else []),
            aviso='O intervalo não produz chamadas sem fixar.' if config.get('sem_fixar') and not any(g['modo']=='sem_fixar' for g in grupos) else None)))

    @app.post('/api/tarefas')
    def criar():
        return jsonify(api_exata(manager.criar(request.get_json()))), 202

    @app.get('/api/experimentos/exclusao')
    def prever_exclusao():
        return jsonify(manager.prever_exclusao())

    @app.post('/api/experimentos/excluir-todos')
    def excluir_experimentos():
        dados = request.get_json()
        if not isinstance(dados, dict) or set(dados) != {'confirmacao'}:
            raise ValueError('Envie somente a confirmação da exclusão apresentada pelo sistema.')
        resultado = manager.excluir_experimentos(dados['confirmacao'])
        return jsonify(resultado), 207 if resultado['falhas'] else 200

    @app.get('/api/tarefas/<ident>')
    def estado(ident):
        return jsonify(api_exata(manager.snapshot(ident)))

    @app.get('/api/tarefas/<ident>/resultados')
    def resultados(ident):
        return jsonify(api_exata(manager.resultados(ident)))

    @app.post('/api/tarefas/<ident>/cancelar')
    def cancelar(ident):
        return jsonify(api_exata(manager.cancelar(ident))), 202

    @app.get('/api/tarefas/<ident>/arquivos/<nome>')
    def baixar(ident, nome):
        path = manager.arquivo(ident, nome)
        if path is None:
            return jsonify(erro='Arquivo indisponível; confira o estado e as exportações da tarefa.'), 404
        return send_file(path, as_attachment=True, download_name=nome)

    return app
