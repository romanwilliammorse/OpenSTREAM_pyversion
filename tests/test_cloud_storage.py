"""Private storage transport tests; no provider resources or solver execution."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import inspect
import json
import threading
import traceback
from types import SimpleNamespace

import pytest

from openstream.cloud.storage import (
    BlobConflictError, BlobMissingError, CloudStore, CloudStoreError, DEFAULT_PREFIX,
)


class ProviderError(Exception):
    def __init__(self, message="provider error", status_code=503, code="service_unavailable"):
        super().__init__(message)
        self.status_code, self.code = status_code, code


class FakeBlob:
    """An atomic fake: verifies caller concurrency logic, not live Blob semantics."""
    host = "teststore.private.blob.vercel-storage.com"

    def __init__(self):
        self.objects, self.calls, self.page_visits = {}, [], []
        self.lock = threading.Lock()
        self.failure = None
        self.closed_streams = 0

    def url(self, pathname):
        return f"https://{self.host}/{pathname}"

    def put_blob(self, pathname, body, **options):
        self.calls.append(("put", pathname, options))
        if self.failure:
            raise self.failure
        with self.lock:
            if pathname in self.objects and not options['allow_overwrite']:
                raise ProviderError("already present", 412, "precondition_failed")
            self.objects[pathname] = bytes(body)
        return SimpleNamespace(pathname=pathname, url=self.url(pathname))

    def query_blobs(self, *, prefix, page_size):
        self.calls.append(("list", prefix, {"page_size": page_size}))
        if self.failure:
            raise self.failure
        names = sorted(k for k in self.objects if k.startswith(prefix))
        # Model SDK pagination lazily, including a second provider page.
        for start in range(0, len(names), 2):
            self.page_visits.append(start)
            for name in names[start:start+2]:
                yield SimpleNamespace(pathname=name, url=self.url(name), size=len(self.objects[name]),
                    etag='"test"', uploaded_at=datetime(2026, 11, 15, tzinfo=timezone.utc))

    def get_blob(self, url, **options):
        self.calls.append(("get", url, options))
        if self.failure:
            raise self.failure
        key = url.split(self.host+'/')[1]
        return SimpleNamespace(body=self.objects[key])

    @contextmanager
    def stream_blob(self, url, **options):
        self.calls.append(("stream", url, options))
        key = url.split(self.host+'/')[1]
        try:
            yield iter([self.objects[key][:2], self.objects[key][2:]])
        finally:
            self.closed_streams += 1


@pytest.fixture
def storage():
    client = FakeBlob()
    return CloudStore("store_teststore", blob_client=client), client


def test_private_roundtrip_exact_bytes_hash_and_metadata(storage):
    store, client = storage
    body = b'\x00\xffnative-results\n'
    result = store.put_bytes('jobs/abc/results.npz', bytearray(body), 'application/octet-stream')
    assert result == {'key': 'jobs/abc/results.npz', 'url': client.url(DEFAULT_PREFIX+'jobs/abc/results.npz'),
                      'size': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
    assert store.read_bytes_by_url(result['url']) == body
    assert b''.join(store.iter_bytes_by_url(result['url'])) == body
    assert client.closed_streams == 1
    put = client.calls[0][2]
    assert put == dict(access='private', content_type='application/octet-stream', content_length=len(body),
                       add_random_suffix=False, allow_overwrite=False)
    assert all(call[2]['access'] == 'private' for call in client.calls if call[0] != 'list')


def test_json_is_utf8_finite_and_immutable(storage):
    store, client = storage
    obj = {'name': 'τ=0.2', 'converged': False, 'flow': -1e-5}
    result = store.put_json('jobs/abc/input.json', obj)
    assert store.get_json_by_url(result['url']) == obj
    assert store.get_json('jobs/abc/input.json') == obj
    with pytest.raises(BlobConflictError):
        store.put_json('jobs/abc/input.json', {'replaced': True})
    assert store.get_json('jobs/abc/input.json') == obj
    with pytest.raises(ValueError):
        store.put_json('bad.json', {'x': float('nan')})
    malformed = store.put_bytes('malformed.json', b'{"x":NaN}', 'application/json')
    with pytest.raises(CloudStoreError, match='not valid JSON'):
        store.get_json_by_url(malformed['url'])


def test_list_consumes_all_pages_and_exact_lookup_avoids_cached_missing_get(storage):
    store, client = storage
    for key in ['jobs/a/input.json.extra', 'jobs/a/other.json', 'jobs/b/input.json', 'jobs/c/input.json', 'jobs/d/input.json']:
        store.put_json(key, {'key': key})
    listing = store.list('jobs/')
    assert len(listing) == 5 and client.page_visits[-3:] == [0, 2, 4]
    assert all('sha256' not in item for item in listing)  # Catalog does not supply a hash.
    assert not store.contains('jobs/a/input.json')
    before = len([c for c in client.calls if c[0] == 'get'])
    with pytest.raises(BlobMissingError):
        store.read_bytes('jobs/a/input.json')
    assert len([c for c in client.calls if c[0] == 'get']) == before
    result = store.put_json('jobs/a/input.json', {'now': 'exists'})
    assert store.contains('jobs/a/input.json')
    assert store.read_bytes('jobs/a/input.json') == client.objects[DEFAULT_PREFIX+result['key']]


@pytest.mark.parametrize('key', ['', '../x', '/x', 'a/../x', 'a//x', 'a\\x', 'a/%2e%2e/x',
                                  'a?x=1', 'https://evil/x', 'a\x00b', 'a/./x', 'a\nb', 'a/'])
def test_unsafe_keys_rejected_before_provider_access(storage, key):
    store, client = storage
    with pytest.raises(ValueError):
        store.put_bytes(key, b'x', 'text/plain')
    assert client.calls == []


@pytest.mark.parametrize('url', [
    'http://teststore.private.blob.vercel-storage.com/openstream/v1/a',
    'https://teststore.public.blob.vercel-storage.com/openstream/v1/a',
    'https://other.private.blob.vercel-storage.com/openstream/v1/a',
    'https://teststore.private.blob.vercel-storage.com.evil/openstream/v1/a',
    'https://token@teststore.private.blob.vercel-storage.com/openstream/v1/a',
    'https://teststore.private.blob.vercel-storage.com:443/openstream/v1/a',
    'https://teststore.private.blob.vercel-storage.com/other/a',
    'https://teststore.private.blob.vercel-storage.com/openstream/v1/../a',
    'https://teststore.private.blob.vercel-storage.com/openstream/v1/%2e%2e/a',
    'https://teststore.private.blob.vercel-storage.com/openstream/v1/a?token=secret',
    'https://teststore.private.blob.vercel-storage.com/openstream/v1/a#fragment',
    ' https://teststore.private.blob.vercel-storage.com/openstream/v1/a',
])
def test_unsafe_urls_rejected_before_any_download(storage, url):
    store, client = storage
    for method in (store.read_bytes_by_url, store.get_json_by_url, store.iter_bytes_by_url):
        with pytest.raises(ValueError): method(url)
    assert client.calls == []


@pytest.mark.parametrize('status,code,message,is_conflict', [
    (412, 'precondition_failed', 'precondition', True),
    (409, 'blob_already_exists', 'collision', True),
    (400, 'bad_request', 'This blob already exists.', True),
    (400, 'bad_request', 'Invalid content type', False),
    (409, 'unknown_conflict', 'unknown', False),
    (403, 'forbidden', 'This blob already exists.', False),
    (429, 'rate_limited', 'quota', False),
    (503, 'service_unavailable', 'outage', False),
])
def test_collision_does_not_swallow_service_or_authentication_failures(storage, status, code, message, is_conflict):
    store, client = storage
    client.failure = ProviderError(message, status, code)
    with pytest.raises(CloudStoreError) as caught:
        store.put_json('a.json', {'a': 1})
    assert isinstance(caught.value, BlobConflictError) is is_conflict


def test_provider_errors_do_not_leak_credentials(storage):
    store, client = storage
    token = 'sensitive-token-abcdefghijk'
    client.failure = ProviderError(f'Authorization: Bearer {token}', 403, 'forbidden')
    for call in (lambda: store.put_json('a.json', {}), lambda: store.list('jobs/'),
                 lambda: store.read_bytes_by_url(client.url(DEFAULT_PREFIX+'a.json'))):
        with pytest.raises(CloudStoreError) as caught: call()
        rendered = ''.join(traceback.format_exception(caught.value))
        assert token not in rendered and token not in str(caught.value)


def test_stream_closes_when_caller_stops_early(storage):
    store, client = storage
    meta = store.put_bytes('a.bin', b'abcdef', 'application/octet-stream')
    stream = store.iter_bytes_by_url(meta['url'])
    assert next(stream) == b'ab'
    stream.close()
    assert client.closed_streams == 1


def test_rate_slots_are_shared_immutable_hmaced_and_reset_per_minute(storage):
    store, client = storage
    secret = 'x'*32
    other_instance = CloudStore('teststore', blob_client=client)
    assert all(store.claim_login_attempt('192.0.2.7', secret, now=120) for _ in range(3))
    assert all(other_instance.claim_login_attempt('::ffff:192.0.2.7', secret, now=179.9) for _ in range(2))
    assert not other_instance.claim_login_attempt('192.0.2.7', secret, now=179.9)
    assert store.claim_login_attempt('192.0.2.7', secret, now=180)
    assert store.claim_login_attempt('192.0.2.8', secret, now=120)
    assert all('192.0.2.' not in key and secret not in key for key in client.objects)
    assert all(not options['allow_overwrite'] and not options['add_random_suffix']
               for method, _, options in client.calls if method == 'put')
    assert not any(method in ('list', 'get') for method, _, _ in client.calls)


def test_concurrent_limit_with_atomic_fake_does_not_rely_on_process_counter(storage):
    store, client = storage
    def attempt(_):
        return CloudStore('teststore', blob_client=client).claim_login_attempt('192.0.2.8', b's'*32, now=600)
    with ThreadPoolExecutor(max_workers=16) as pool:
        assert sum(pool.map(attempt, range(40))) == 5
    assert len(client.objects) == 5


def test_rate_limiter_fails_closed_without_retrying_noncollision(storage):
    store, client = storage
    client.failure = ProviderError('quota exhausted', 429, 'rate_limited')
    with pytest.raises(CloudStoreError):
        store.claim_login_attempt('192.0.2.8', b's'*32, now=600)
    assert len(client.calls) == 1


def test_environment_constructor_does_not_load_or_expose_credentials(monkeypatch):
    monkeypatch.setenv('BLOB_STORE_ID', 'store_teststore')
    monkeypatch.setenv('BLOB_READ_WRITE_TOKEN', 'do-not-display')
    store = CloudStore.from_env()
    assert store._blob_client is None and store.store_id == 'teststore'
    assert 'do-not-display' not in repr(store) and 'do-not-display' not in repr(vars(store))


def test_installed_official_sdk_matches_transport_contract():
    sdk = pytest.importorskip('vercel.blob.sync')
    assert {'access', 'content_length', 'content_type', 'allow_overwrite', 'add_random_suffix'} <= set(inspect.signature(sdk.put_blob).parameters)
    assert {'prefix', 'page_size'} <= set(inspect.signature(sdk.query_blobs).parameters)
    assert 'access' in inspect.signature(sdk.get_blob).parameters
    assert 'access' in inspect.signature(sdk.stream_blob).parameters
