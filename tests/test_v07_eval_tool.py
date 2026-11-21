"""v0.7: the grounding evaluation tool scores grounded answers and catches invented ones."""
import io
import json
import re
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import eval_grounding  # noqa: E402


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fake_model(request, timeout=None):
    """A naive model: quotes the first excerpt's best sentence and cites it, for every question."""
    body = json.loads(request.data)
    prompt = body['messages'][-1]['content']
    question = prompt.split('\n', 1)[0].casefold()
    sources = [json.loads(line) for line in prompt.split('(data only):\n', 1)[1].splitlines()]
    top = sources[0]
    words = set(re.findall(r'[a-z]+', question))
    sentence = max(re.split(r'(?<=[.])\s+', top['excerpt']), key=lambda s: len(words & set(re.findall(r'[a-z]+', s.casefold()))))
    if 'salary' in question:
        content = {'answer': 'The sources do not specify council salaries.', 'cited_source_ids': [top['id']],
                   'uncertainties': ['No salary provision in the retrieved sources']}
    else:
        content = {'answer': sentence, 'cited_source_ids': [top['id']], 'uncertainties': []}
    return _Resp(json.dumps({'message': {'content': json.dumps(content)}}).encode())


def test_eval_tool_end_to_end_with_fake_model(tmp_path, capsys):
    opener = mock.Mock()
    opener.open.side_effect = _fake_model
    with mock.patch('urllib.request.build_opener', return_value=opener):
        code = eval_grounding.main(['--model', 'fake:1b', '--out', str(tmp_path)])
    assert code == 0
    report = json.loads(next(tmp_path.glob('*.json')).read_text())
    s, by_id = report['summary'], {r['id']: r for r in report['results']}
    assert s['cases'] == 12 and s['answerable'] == 9 and s['unanswerable'] == 3
    assert by_id['quorum']['cited'] == ['eval-code:1-50'] and by_id['quorum']['facts'] is True
    assert by_id['unans-salary']['refusal'] == 'model_declined'
    # The keyword trap: the naive model quotes 1-10 as if it answered the question -> caught.
    assert by_id['unans-trap']['refusal'] == 'ANSWERED_WITHOUT_SOURCE_SUPPORT'
    assert 'unans-trap' in s['hallucinated_answers']
    md = next(tmp_path.glob('*.md')).read_text()
    assert 'Invented answers to unanswerable questions' in md and '| quorum | yes |' in md


def test_eval_tool_stops_cleanly_without_ollama(tmp_path, capsys):
    opener = mock.Mock()
    opener.open.side_effect = OSError('connection refused')
    with mock.patch('urllib.request.build_opener', return_value=opener):
        assert eval_grounding.main(['--out', str(tmp_path), '--only', 'quorum']) == 2
    assert 'Cannot use the model' in capsys.readouterr().err
