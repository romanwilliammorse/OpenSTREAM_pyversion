"""Vercel entrypoint. Local launchers continue to use openstream.gui unchanged."""
from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent/'src'))

from openstream.cloud.app import create_app
from openstream.cloud.gateway import SandboxGateway, provenance
from openstream.cloud.manager import CloudRunManager
from openstream.cloud.storage import CloudStore

store = CloudStore.from_env()
source, environment = provenance()
manager = CloudRunManager(store, SandboxGateway(int(os.getenv('OPENSTREAM_CLOUD_JOB_SECONDS', '2400'))),
                          source=source, environment=environment,
                          max_active=int(os.getenv('OPENSTREAM_CLOUD_MAX_ACTIVE', '2')))


def login_limit(key):
    return store.claim_login_attempt(key.removeprefix('login:'), os.environ['OPENSTREAM_SESSION_SECRET'])


app = create_app(manager, limiter=login_limit)


class VercelRequestContext:
    """Trust only headers overwritten by Vercel, and only on Vercel itself.

    No host rewriting; the Flask adapter validates the configured exact host.
    OIDC request context remains alive for streamed private downloads.
    """
    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __call__(self, environ, start_response):
        from vercel.headers import set_headers
        if os.getenv('VERCEL') == '1':
            raw_ip = environ.get('HTTP_X_VERCEL_FORWARDED_FOR', environ.get('HTTP_X_FORWARDED_FOR', ''))
            try:
                environ['REMOTE_ADDR'] = str(ipaddress.ip_address(raw_ip))
            except ValueError:
                start_response('400 Bad Request', [('Content-Type', 'text/plain'), ('Cache-Control', 'no-store')])
                return [b'Unrecognized client address']
            if environ.get('HTTP_X_FORWARDED_PROTO') == 'https':
                environ['wsgi.url_scheme'] = 'https'
        headers = {key[5:].replace('_', '-').lower(): value
                   for key, value in environ.items() if key.startswith('HTTP_')}
        set_headers(headers)
        try:
            iterable = self.wrapped(environ, start_response)
        except BaseException:
            set_headers(None)
            raise
        def stream():
            try:
                yield from iterable
            finally:
                if hasattr(iterable, 'close'):
                    iterable.close()
                set_headers(None)
        return stream()


app.wsgi_app = VercelRequestContext(app.wsgi_app)
