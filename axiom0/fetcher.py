"""Opt-in, allowlisted municipal source fetcher with ETag/TTL and signed audit.

No crawling by default; no arbitrary URL ingestion exposed through the API.
The registry is local-operator controlled.

DNS rebinding (v0.7): the hostname is resolved once, every address is checked to
be public, and the connection is then made to that exact validated address. TLS
still verifies the certificate against the real hostname (SNI), so a DNS answer
that changes between the check and the connection cannot redirect the request to
a private or internal address. Rendered (browser) fetches pin the same address
with Chromium's host-resolver rules. This is pilot security, not a
network-isolated crawler; review robots/terms of use before scale.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import random
import socket
import time
from urllib.parse import urlparse
from typing import Callable, Any
import httpx
from .core import Axiom0
from .store import now, digest, canonical

MAX_BYTES=1_500_000
USER_AGENT='AXIOM0-LivingCity/0.7 (+local-operator; read-only; opt-in feed)'


def _atomic_json(path: Path, value: Any):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(value,f,indent=2,sort_keys=True,ensure_ascii=False)
        f.flush();os.fsync(f.fileno())
    tmp.replace(path)


def _public_host(url: str, allowed_hosts: set[str], resolver: Callable | None = None) -> str:
    return _resolve_public(url, allowed_hosts, resolver)[0]


def _resolve_public(url: str, allowed_hosts: set[str], resolver: Callable | None = None) -> tuple[str, str]:
    """Validate the URL and its DNS answer; return (hostname, one validated public IP to pin)."""
    parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Only public HTTPS URLs without credentials or fragments are accepted')
    if parsed.port not in (None,443):
        raise ValueError('Only HTTPS port 443 is permitted')
    host=parsed.hostname.lower().rstrip('.')
    if host not in allowed_hosts:
        raise PermissionError('URL hostname not registered on the source allowlist')
    resolver=resolver or socket.getaddrinfo
    try:
        addresses=resolver(host,443,type=socket.SOCK_STREAM)
        ip_values=[a[4][0] for a in addresses]
    except (OSError,ValueError) as e:
        raise ConnectionError('Unable to resolve approved feed hostname') from e
    if not ip_values:
        raise ConnectionError('Approved hostname has no DNS records')
    for ip_string in ip_values:
        ip=ipaddress.ip_address(ip_string)
        if not ip.is_global:
            raise PermissionError('Approved feed resolves to a non-public network address')
    return host, ip_values[0]


def _pinned_url(url: str, ip: str) -> str:
    """Same URL, with the hostname replaced by the validated IP literal."""
    parsed=urlparse(url)
    literal=f'[{ip}]' if ':' in ip else ip
    return parsed._replace(netloc=literal).geturl()


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines=[];self.buf=[];self.ignore=0;self.heading=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript','svg','iframe','form'}:
            self.ignore+=1
        elif not self.ignore:
            if tag in {'h1','h2','h3','h4','p','li','div','section','article','br','tr'}:
                self._flush()
            if tag in {'h1','h2','h3'}: self.heading+=1
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript','svg','iframe','form'} and self.ignore:
            self.ignore-=1
        elif not self.ignore:
            if tag in {'h1','h2','h3'}:
                self._flush();self.heading=max(0,self.heading-1)
            elif tag in {'p','li','tr','br','div','article','section'}: self._flush()
    def handle_data(self, data):
        if not self.ignore and data.strip():
            self.buf.append(data.strip())
    def _flush(self):
        s=' '.join(self.buf).strip()
        if s:
            self.lines.append(('' if s.startswith(('Section ','Sec. ','§ ')) else '## ' if self.heading else '')+s)
        self.buf=[]
    def get_text(self):
        self._flush()
        return '\n'.join(self.lines)


def extract_text(raw: bytes, content_type: str) -> str:
    try:
        text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise ValueError('Feed content must decode as UTF-8')
    if 'html' in content_type:
        parser=_TextExtractor();parser.feed(text);text=parser.get_text()
    elif not any(t in content_type for t in ('text/plain','text/markdown','application/json')):
        raise ValueError('Unsupported response media type: '+content_type[:80])
    text=text.strip()
    if len(text)<20: raise ValueError('Fetched source text too short for meaningful ingestion')
    return text[:1_500_000]


class ResilientFetcher:
    def __init__(self, data_dir: str | Path, *, client: httpx.Client | None = None,
                 resolver: Callable | None = None, sleep_fn: Callable[[float], None] = time.sleep):
        self.ax=Axiom0(data_dir)
        self.base=self.ax.data_dir
        self.registry_path=self.base/'feeds.json'
        self.state_path=self.base/'fetch_state.json'
        self.cache_dir=self.base/'feed_cache'
        self.cache_dir.mkdir(parents=True,exist_ok=True)
        self.client=client
        self.resolver=resolver
        self.sleep_fn=sleep_fn

    def _read(self,path:Path) -> dict:
        if not path.exists(): return {}
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict): raise ValueError('Feed registry/state is malformed')
        return data

    def feeds(self) -> list[dict]:
        return list(self._read(self.registry_path).values())

    def register(self, *, feed_id:str, url:str, doc_id:str, authority:str,
                 title:str, effective:str|None=None, render:bool=False,
                 ttl_minutes:int=60) -> dict:
        if not isinstance(feed_id,str) or not feed_id.replace('_','').replace('-','').isalnum() or len(feed_id)>64:
            raise ValueError('Use an alphanumeric feed ID (hyphen/underscore allowed)')
        if not isinstance(doc_id,str) or not doc_id.replace('_','').replace('-','').isalnum() or len(doc_id)>120:
            raise ValueError('Use an alphanumeric document ID (hyphen/underscore allowed)')
        if authority not in ('charter','ordinance','policy','procedure'):
            raise ValueError('Authority must be charter, ordinance, policy or procedure')
        if not isinstance(title,str) or not title.strip() or len(title)>160 or '\n' in title:
            raise ValueError('Invalid feed title')
        if effective is not None:
            datetime.strptime(effective,'%Y-%m-%d')
        if type(ttl_minutes) is not int or not 5<=ttl_minutes<=10080:
            raise ValueError('ttl_minutes must be between 5 and 10080')
        parsed=urlparse(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):
            raise ValueError('Only HTTPS URLs on port 443 without user-info are allowed')
        # Network DNS is checked at fetch time. Registration is a local operator action.
        record={'feed_id':feed_id,'url':url,'allowed_host':parsed.hostname.lower().rstrip('.'),
                'doc_id':doc_id,'authority':authority,'title':title,'effective':effective,
                'render':bool(render),'ttl_minutes':ttl_minutes}
        registry=self._read(self.registry_path)
        if feed_id in registry and registry[feed_id]['url']!=url:
            raise ValueError('Feed ID already used; do not silently point source identity at another URL')
        registry[feed_id]=record
        _atomic_json(self.registry_path,registry)
        with self.ax.store.write() as db:
            self.ax.store.append(db,'feed_registered',{'feed_id':feed_id,'url':url,
                                   'authority_claimed':authority,'render':bool(render)})
        return record

    def _fetch_static(self, feed:dict, headers:dict, pinned_ip:str|None=None) -> tuple[int,bytes,str,dict]:
        kwargs={'timeout':httpx.Timeout(25.0,connect=8.0),'follow_redirects':False,
                'trust_env':False,'headers':headers}
        client=self.client or httpx.Client(**kwargs)
        url=feed['url'];extensions={}
        if pinned_ip:
            # Connect to the address that was validated, never to a fresh DNS answer.
            host=urlparse(url).hostname
            url=_pinned_url(url,pinned_ip)
            headers={**headers,'Host':host}
            extensions={'sni_hostname':host}   # TLS SNI + certificate check use the real hostname
        try:
            with client.stream('GET',url,headers=headers,extensions=extensions) as response:
                if response.status_code==304:
                    return 304,b'',response.headers.get('content-type',''),dict(response.headers)
                if response.is_redirect: raise ValueError('Redirect refused; register reviewed canonical destination')
                response.raise_for_status()
                size=0;parts=[]
                for part in response.iter_bytes():
                    size+=len(part)
                    if size>MAX_BYTES: raise ValueError('Feed exceeded configured size limit')
                    parts.append(part)
                return response.status_code,b''.join(parts),response.headers.get('content-type','text/plain'),dict(response.headers)
        finally:
            if self.client is None: client.close()

    def _fetch_browser(self, feed:dict, pinned_ip:str|None=None) -> tuple[int,bytes,str,dict]:
        # Opt-in only; network requests except the explicitly allowed hostname are blocked.
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError('Install AXIOM0[render], then playwright install chromium') from e
        with sync_playwright() as p:
            args=[]
            if pinned_ip:
                literal=f'[{pinned_ip}]' if ':' in pinned_ip else pinned_ip
                args.append(f"--host-resolver-rules=MAP {feed['allowed_host']} {literal}")
            browser=p.chromium.launch(headless=True,args=args)
            try:
                page=browser.new_page()
                host=feed['allowed_host']
                def route_handler(route):
                    u=urlparse(route.request.url)
                    if u.scheme != 'https' or u.hostname != host or u.port not in (None,443):
                        route.abort()
                    else: route.continue_()
                page.route('**/*',route_handler)
                response=page.goto(feed['url'],wait_until='domcontentloaded',timeout=30000)
                if not response or response.status>=400:
                    raise RuntimeError('Browser did not return a valid page')
                if urlparse(page.url).hostname!=host:
                    raise PermissionError('Browser navigation escaped allowed host')
                content=page.content().encode('utf-8')
                if len(content)>MAX_BYTES: raise ValueError('Rendered source exceeded size limit')
                return 200,content,'text/html',{}
            finally: browser.close()

    def _audit(self, payload:dict):
        with self.ax.store.write() as db:
            self.ax.store.append(db,'feed_cycle',payload)

    def poll(self, feed_id:str, *, bypass_ttl:bool=False, jitter_seconds:float=0.0) -> dict:
        registry=self._read(self.registry_path)
        if feed_id not in registry: raise ValueError('Unknown feed')
        feed=registry[feed_id]; state=self._read(self.state_path)
        entry=state.get(feed_id,{})
        stamp=now()
        fresh=False
        if entry.get('checked_at') and not bypass_ttl:
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(entry['checked_at'])).total_seconds()
            fresh=age < feed['ttl_minutes']*60
        if fresh:
            report={'feed_id':feed_id,'status':'fresh_cache_no_request','content_sha256':entry.get('content_hash'), 'checked_at':stamp}
            self._audit(report)
            return report
        try:
            _host,pinned_ip=_resolve_public(feed['url'],{feed['allowed_host']},self.resolver)
            if jitter_seconds:
                if not 0<=jitter_seconds<=30: raise ValueError('Jitter must be in 0..30 seconds')
                self.sleep_fn(random.uniform(0,jitter_seconds))
            headers={'User-Agent':USER_AGENT,'Accept':'text/html, text/plain, text/markdown, application/json'}
            if entry.get('etag') and not feed['render']: headers['If-None-Match']=entry['etag']
            if entry.get('last_modified') and not feed['render']: headers['If-Modified-Since']=entry['last_modified']
            code,raw,media,hdr=(self._fetch_browser(feed,pinned_ip) if feed['render']
                                else self._fetch_static(feed,headers,pinned_ip))
            if code==304:
                report={'feed_id':feed_id,'status':'http_not_modified','content_sha256':entry.get('content_hash'),'checked_at':stamp}
            else:
                content=extract_text(raw,media)
                h=digest(content)
                if entry.get('content_hash')==h:
                    report={'feed_id':feed_id,'status':'same_content_hash','content_sha256':h,'checked_at':stamp}
                else:
                    metadata=['---',f"doc_id: {feed['doc_id']}",f"title: {feed['title']}",
                              f"authority: {feed['authority']}"]
                    if feed['effective']: metadata.append(f"effective: {feed['effective']}")
                    metadata.extend([f"source_url: {feed['url']}",'---'])
                    if not any(line.lstrip().startswith(('## ','### ','Sec. ','Section ','§ ')) for line in content.splitlines()):
                        content='## body Extracted page text\n'+content
                    full='\n'.join(metadata)+'\n'+content+'\n'
                    # Do not update fetch cache/etag if structured legal ingestion failed.
                    legal=self.ax.library.ingest_text(full,actor='fetcher')
                    self.ax.city.add_document(title=feed['title'],authority=feed['authority'],
                        jurisdiction='Operator-provided feed; jurisdiction unverified',
                        citation=feed['doc_id'],version=h[:16],content=content,
                        source_url=feed['url'],source_reviewed=False)
                    self.ax.semisoul.remember(statement=(
                        f"The monitored source {feed['feed_id']} had a new text revision with SHA-256 {h}; "
                        "its legal authenticity and factual accuracy remain unverified."),
                        memory_type='observation', epistemic_status='source_claim',
                        source_type='document', source_ref=feed['url'], actor='fetcher')
                    cache_path=self.cache_dir/(h+'.txt')
                    if not cache_path.exists():
                        cache_path.write_text(content,encoding='utf-8')
                    report={'feed_id':feed_id,'status':'changed','content_sha256':h,
                            'legal_versions':legal,'checked_at':stamp}
                entry['content_hash']=h
            entry['checked_at']=stamp
            entry['etag']=hdr.get('etag',entry.get('etag'))
            entry['last_modified']=hdr.get('last-modified',entry.get('last_modified'))
            state[feed_id]=entry
            _atomic_json(self.state_path,state)
            self._audit(report)
            return report
        except Exception as e:
            report={'feed_id':feed_id,'status':'failed','reason':type(e).__name__,
                    'checked_at':stamp,'message':str(e)[:240]}
            self._audit(report)
            return report

    def poll_all(self, *, bypass_ttl:bool=False, jitter_seconds:float=0.5) -> list[dict]:
        return [self.poll(f['feed_id'],bypass_ttl=bypass_ttl,jitter_seconds=jitter_seconds)
                for f in self.feeds()]

    async def continuous(self, hours:float=6):
        if not 0.25<=hours<=168: raise ValueError('Interval must be 0.25..168 hours')
        while True:
            await asyncio.to_thread(self.poll_all)
            await asyncio.sleep(hours*3600)
