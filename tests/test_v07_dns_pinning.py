"""v0.7: fetcher connects to the DNS answer it validated (closes the rebinding window)."""
import datetime
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from axiom0.fetcher import ResilientFetcher, _pinned_url, _resolve_public

PUBLIC = '93.184.215.14'


def test_pinned_url_forms():
    assert _pinned_url('https://feeds.example.gov/a/b?x=1', PUBLIC) == f'https://{PUBLIC}/a/b?x=1'
    assert _pinned_url('https://feeds.example.gov/a', '2606:2800:21f:cb07:6820:80da:af6b:8b2c') == \
        'https://[2606:2800:21f:cb07:6820:80da:af6b:8b2c]/a'


def test_request_goes_to_validated_ip_with_real_host_and_sni(tmp_path):
    seen = {}

    def responder(request):
        seen['url'] = str(request.url)
        seen['host'] = request.headers['host']
        seen['sni'] = request.extensions.get('sni_hostname')
        return httpx.Response(200, text='Section 1. Records\nAll public records are open for inspection.',
                              headers={'content-type': 'text/plain'})

    calls = []

    def rebinding_resolver(*a, **k):
        # First answer is public; any later lookup would point inside the network.
        calls.append(1)
        ip = PUBLIC if len(calls) == 1 else '10.0.0.5'
        return [(None, None, None, None, (ip, 443))]

    with httpx.Client(transport=httpx.MockTransport(responder)) as client:
        f = ResilientFetcher(tmp_path, client=client, resolver=rebinding_resolver, sleep_fn=lambda s: None)
        f.register(feed_id='charter', url='https://feeds.example.gov/charter', doc_id='kc-charter',
                   authority='charter', title='Charter')
        calls.clear()
        f.poll('charter', bypass_ttl=True)
    assert seen['url'].startswith(f'https://{PUBLIC}/')        # connected to the validated address
    assert seen['host'] == 'feeds.example.gov' and seen['sni'] == 'feeds.example.gov'
    assert len(calls) == 1                                        # no second, unchecked lookup


def test_private_answer_still_refused():
    with pytest.raises(PermissionError):
        _resolve_public('https://feeds.example.gov/x', {'feeds.example.gov'},
                        lambda *a, **k: [(None, None, None, None, ('127.0.0.1', 443))])


def _self_signed(hostname, tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_path, key_path = tmp_path / 'c.pem', tmp_path / 'k.pem'
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    return cert_path, key_path


def test_real_tls_verifies_certificate_against_hostname_when_pinned(tmp_path):
    """The mechanism the fix relies on, over a real TLS handshake."""
    cert, key = _self_signed('feeds.example.test', tmp_path)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = self.headers['Host'].encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(('127.0.0.1', 0), H)
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(cert, key)
    server.socket = sctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    trust = ssl.create_default_context(cafile=str(cert))
    url = f'https://127.0.0.1:{server.server_port}/'
    try:
        with httpx.Client(verify=trust, trust_env=False) as c:
            ok = c.get(url, headers={'Host': 'feeds.example.test'}, extensions={'sni_hostname': 'feeds.example.test'})
            assert ok.status_code == 200 and ok.text == 'feeds.example.test'
            with pytest.raises(httpx.ConnectError):        # wrong name -> certificate check fails
                c.get(url, headers={'Host': 'evil.example.test'}, extensions={'sni_hostname': 'evil.example.test'})
    finally:
        server.shutdown()
