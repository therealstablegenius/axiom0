"""v0.7: retrieval ranking, excerpt labelling, forbidden-action guardrail, optional 3-6-9 module."""
import pytest
from fastapi.testclient import TestClient

from axiom0.api import app, compat, core
from axiom0.core import Axiom0
from axiom0.engine import LivingCity
from axiom0.municipal import forbidden_action


def _doc(city, title, content, version='1'):
    city.add_document(title=title, authority='policy', jurisdiction='Test City', citation=title,
                      version=version, content=content, source_url='local://test')


def test_bm25_prefers_focused_source_over_long_wordy_one(tmp_path):
    city = LivingCity(tmp_path)
    filler = ' '.join(['The city and the council and the department shall have the duties of the office.'] * 60)
    _doc(city, 'General Duties', filler + ' Records are kept.')
    _doc(city, 'Public Records Policy', 'Public records requests must be answered within three business days.')
    found = city.search_documents('How fast must public records requests be answered?')
    assert found[0]['title'] == 'Public Records Policy'
    assert 'three business days' in found[0]['excerpt'] and found[0]['retrieval_score'] > 0


def test_stop_words_alone_retrieve_nothing(tmp_path):
    city = LivingCity(tmp_path)
    _doc(city, 'Anything', 'The and the of the with the.')
    assert city.search_documents('what are the and of the') == []


def test_excerpt_centres_on_best_sentence(tmp_path):
    city = LivingCity(tmp_path)
    body = ('Intro text about procedures. ' * 120) + 'Chamber reservations are approved by the City Clerk in order received.'
    _doc(city, 'Chamber Rules', body)
    hit = city.search_documents('who approves chamber reservations')[0]
    assert 'approved by the City Clerk' in hit['excerpt']


def test_ask_findings_are_labelled_as_excerpts(tmp_path):
    ax = Axiom0(tmp_path)
    ax.set_admin('howard')
    ax.library.ingest_file('examples/SIMULATED_charter.md', actor='howard')
    out = ax.ask('howard', 'What does the charter say about public records?')
    assert out['findings'] and all(f['kind'] == 'source_excerpt' for f in out['findings'])
    assert 'does NOT' in out['how_to_read']


@pytest.mark.parametrize('text', ['Issue citations to owners on Prospect', 'Cite the property owner',
                                  'Approve $25,000 in funds for repairs', 'release the grant money',
                                  'Tow the abandoned cars', 'Amend the council minutes from March',
                                  'Score residents by complaint history', 'build a watch list of households',
                                  'issue_citation now', 'ISSUE   CITATION!!'])
def test_guardrail_blocks_rephrased_forbidden_actions(text):
    assert forbidden_action(text) is not None


@pytest.mark.parametrize('text', ['Inspect storm drains on Prospect', 'Schedule a site visit with Public Works',
                                  'Notify the neighborhood association about the pothole spike',
                                  "Request the budget office's published FY27 figures",
                                  'Review public records request turnaround times'])
def test_guardrail_allows_human_followup(text):
    assert forbidden_action(text) is None


def test_propose_reports_which_rule_blocked(tmp_path):
    ax = Axiom0(tmp_path)
    with pytest.raises(ValueError, match='authorize_spending'):
        ax.municipal.propose(proposed_by='howard', recommendation='Disburse grant money to the vendor',
                             evidence_refs=['x'])


def test_symbolic_features_off_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv('AXIOM0_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('AXIOM0_API_KEY', 'A' * 48)
    monkeypatch.setenv('AXIOM0_REVIEWER_KEY', 'B' * 48)
    monkeypatch.delenv('AXIOM0_ENABLE_SYMBOLIC', raising=False)
    core.cache_clear(); compat.cache_clear()
    try:
        c = TestClient(app)
        h = {'X-AXIOM0-Key': 'A' * 48}
        assert c.get('/health').json()['features'] == {'symbolic_369': False}
        assert c.get('/v1/369/intentions', headers=h).status_code == 404
        assert c.post('/v1/symbolic-state', headers=h, json={'vector': [1, 2, 8, 7, 5]}).status_code == 404
        assert 'id="intention-lab"' in c.get('/').text and 'hidden>' in c.get('/').text
        monkeypatch.setenv('AXIOM0_ENABLE_SYMBOLIC', '1')
        assert c.get('/health').json()['features'] == {'symbolic_369': True}
        assert c.post('/v1/symbolic-state', headers=h, json={'vector': [1, 2, 8, 7, 5]}).status_code == 200
    finally:
        core.cache_clear(); compat.cache_clear()
