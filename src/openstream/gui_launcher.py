"""Launch or reopen the local GUI without requiring an internet connection."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import socket
import threading
import time
from urllib.request import urlopen
import webbrowser


def main(argv=None):
    parser = argparse.ArgumentParser(description='OpenSTREAM local graphical interface')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--output-root', type=Path, default=Path.home()/'Documents'/'OpenSTREAM'/'runs')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535: parser.error('port must be between 1024 and 65535')
    url = f'http://127.0.0.1:{args.port}'
    try:
        with urlopen(url+'/api/health', timeout=2) as response: health = json.load(response)
        if health.get('app') == 'openstream-gui':
            if not args.no_browser: webbrowser.open(url)
            return 0
    except (OSError, ValueError):
        pass
    args.output_root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.output_root.parent/'gui-server.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    # Reserve the port before importing/building the app, avoiding misleading
    # state changes if another program already occupies it.
    probe = socket.socket()
    try:
        probe.bind(('127.0.0.1', args.port))
    except OSError:
        logging.exception('Local port %s is occupied; use --port to select another', args.port)
        raise
    finally:
        probe.close()
    from waitress import create_server
    from .gui import create_app
    server = create_server(create_app(args.output_root), host='127.0.0.1', port=args.port, threads=4)
    if not args.no_browser:
        def open_when_ready():
            for _ in range(40):
                try:
                    with urlopen(url+'/api/health', timeout=1):
                        webbrowser.open(url)
                        return
                except OSError: time.sleep(.25)
        threading.Thread(target=open_when_ready, daemon=True).start()
    logging.info('OpenSTREAM GUI listening at %s; results at %s', url, args.output_root.resolve())
    server.run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
