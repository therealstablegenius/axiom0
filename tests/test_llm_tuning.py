"""Hardware-tuning knobs for the local Ollama adapter (Raspberry Pi 5 edition)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

import pytest

from axiom0 import llm
from axiom0.llm import LocalMindError, OllamaMind

TUNING_VARS = ('AXIOM0_LLM_TIMEOUT', 'AXIOM0_LLM_SOURCES', 'AXIOM0_NUM_CTX',
               'AXIOM0_NUM_THREAD', 'AXIOM0_NUM_PREDICT', 'AXIOM0_KEEP_ALIVE')


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in TUNING_VARS:
        monkeypatch.delenv(name, raising=False)


DOC = {'id': 'doc1', 'title': 'T', 'citation': 'C', 'authority': 'A', 'version': '1',
       'source_url': '', 'source_reviewed': True, 'excerpt': 'records are public'}


def test_defaults_unchanged_from_v06():
    mind = OllamaMind()
    assert mind.timeout == 90
    assert mind.source_limit == 6
    payload = mind.build_payload('q', [DOC])
    assert payload['options'] == {'temperature': 0}
    assert 'keep_alive' not in payload


def test_pi5_profile_values_reach_payload(monkeypatch):
    monkeypatch.setenv('AXIOM0_LLM_TIMEOUT', '420')
    monkeypatch.setenv('AXIOM0_LLM_SOURCES', '4')
    monkeypatch.setenv('AXIOM0_NUM_CTX', '4096')
    monkeypatch.setenv('AXIOM0_NUM_THREAD', '4')
    monkeypatch.setenv('AXIOM0_NUM_PREDICT', '512')
    monkeypatch.setenv('AXIOM0_KEEP_ALIVE', '30m')
    mind = OllamaMind()
    assert mind.timeout == 420 and mind.source_limit == 4
    payload = mind.build_payload('q', [DOC])
    assert payload['options'] == {'temperature': 0, 'num_ctx': 4096, 'num_thread': 4, 'num_predict': 512}
    assert payload['keep_alive'] == '30m'


@pytest.mark.parametrize('value,expected', [('-1', -1), ('0', 0), ('600', 600), ('2h', '2h')])
def test_keep_alive_forms(monkeypatch, value, expected):
    monkeypatch.setenv('AXIOM0_KEEP_ALIVE', value)
    assert OllamaMind().build_payload('q', [DOC])['keep_alive'] == expected


@pytest.mark.parametrize('name,value', [('AXIOM0_NUM_CTX', 'lots'), ('AXIOM0_NUM_CTX', '64'),
                                        ('AXIOM0_LLM_SOURCES', '9'), ('AXIOM0_LLM_TIMEOUT', '1'),
                                        ('AXIOM0_KEEP_ALIVE', '30 minutes; rm')])
def test_invalid_tuning_fails_closed(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(LocalMindError):
        OllamaMind()


class _FakeCity:
    def __init__(self):
        self.limits = []

    def search_documents(self, question, limit=6):
        self.limits.append(limit)
        return [DOC]


def _serve(handler_cls):
    server = HTTPServer(('127.0.0.1', 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_end_to_end_with_fake_ollama(monkeypatch):
    seen = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            seen['body'] = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            content = json.dumps({'answer': 'Records are public.', 'cited_source_ids': ['doc1'],
                                  'uncertainties': []})
            body = json.dumps({'message': {'content': content}}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = _serve(Handler)
    monkeypatch.setenv('AXIOM0_LLM_SOURCES', '3')
    monkeypatch.setenv('AXIOM0_NUM_THREAD', '4')
    mind = OllamaMind()
    mind.endpoint = f'http://127.0.0.1:{server.server_port}'  # test-only bypass of the fixed port
    city = _FakeCity()
    try:
        result = mind.answer(city, 'Are records public?')
    finally:
        server.shutdown()
    assert city.limits == [3]
    assert seen['body']['options']['num_thread'] == 4
    assert result['cited_source_ids'] == ['doc1']
    assert result['classification'] == 'unverified_model_draft'


def test_timeout_reports_tuning_hint(monkeypatch):
    monkeypatch.setenv('AXIOM0_LLM_TIMEOUT', '10')
    mind = OllamaMind()

    class Opener:
        def open(self, *a, **k):
            raise TimeoutError('timed out')

    with mock.patch('urllib.request.build_opener', return_value=Opener()):
        with pytest.raises(LocalMindError, match='AXIOM0_LLM_TIMEOUT'):
            mind.answer(_FakeCity(), 'Are records public?')
