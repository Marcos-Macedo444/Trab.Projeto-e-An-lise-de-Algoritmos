"""Lançador local sem efeitos ao importar. Ctrl+C finaliza cálculo e checkpoints."""
import argparse
from pathlib import Path
import sys
import socket
import os


def main(argv=None):
    p = argparse.ArgumentParser(description='TSP — Laboratório local (somente 127.0.0.1)')
    p.add_argument('--porta', type=int, default=5000)
    p.add_argument('--base', type=Path, help='Base de tarefas; padrão: resultados_web junto ao projeto')
    p.add_argument('--max-fixo', type=int, default=20)
    p.add_argument('--max-livre', type=int, default=20)
    p.add_argument('--max-comparacao', type=int, default=10)
    args = p.parse_args(argv)
    if not 1 <= args.porta <= 65535:
        p.error('porta deve estar entre 1 e 65535')
    if min(args.max_fixo, args.max_livre, args.max_comparacao) < 3:
        p.error('tetos devem ser >=3')
    try:
        from waitress.server import create_server
        from web_local.app import create_app
        from web_local.tarefas import Gerenciador, Ocupado
    except ImportError as exc:
        print(f'Dependência ausente: {exc}. Instale: python -m pip install -r requirements-web.txt', file=sys.stderr)
        return 1
    manager = None
    server = None
    reserva = None
    try:
        manager = Gerenciador(base=args.base, tetos={'fixo':args.max_fixo,
            'livre':args.max_livre, 'comparacao':args.max_comparacao})
        app = create_app(manager)
        # Reserva sem SO_REUSEADDR: no Windows, dois servidores com reuse podem
        # aceitar o mesmo endereço. O socket exclusivo evita isso e não há janela
        # de fechar/reabrir entre a validação da porta e o Waitress.
        reserva = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name == 'nt':
            reserva.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        reserva.bind(('127.0.0.1', args.porta))
        server = create_server(app, sockets=[reserva], threads=4)
        print(f'Abra http://127.0.0.1:{args.porta}', flush=True)
        print(f'Resultados: {manager.base}\nEncerre com Ctrl+C; aguarde a finalização.', flush=True)
        server.run()
    except Ocupado as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f'Não foi possível abrir a porta {args.porta}: {exc}. Tente --porta {args.porta+1}.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Encerrando e preservando checkpoints...', flush=True)
    finally:
        if server:
            server.close()
        if reserva:
            reserva.close()
        if manager:
            manager.close()
    return 0


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    raise SystemExit(main())
