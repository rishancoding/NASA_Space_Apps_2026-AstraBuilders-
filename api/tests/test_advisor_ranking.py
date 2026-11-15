"""The advisor has one fixed, disclosed evidence-ranking method."""
from fastapi.testclient import TestClient
from api.main import app
from api import core

client = TestClient(app)


def test_only_original_fixed_ranking_remains():
    options = client.get('/api/options').json()['priorities']
    assert [o['value'] for o in options] == ['evidence_strength']
    for old in ['safety_screening','closest_conditions','nearby_tests','reviewed_outcomes','fewest_sustained_flames']:
        assert client.post('/api/advisor',json={'oxygen_pct':21,'priority':old}).status_code == 422


def test_original_closeness_weighted_evidence_order_and_disclosure():
    result = core.advisor(21,10)
    rows = result['candidates']
    scores = [r['evidence']['score'] for r in rows]
    assert scores == sorted(scores,reverse=True)
    assert [r['rank'] for r in rows] == list(range(1,len(rows)+1))
    for row in rows:
        matches = core.find_similar_solid(21,10,material=row['material'],k=len(core.solids()))['matches']
        expected = sum(m['similarity'] for m in matches if m['distance']<=2.5)
        assert abs(row['evidence']['score']-expected)<.002
        assert row['rank_reason'] and 'screening' not in row
    assert 'not a safety ranking' in result['rank_basis']
    assert 'exp(−distance)' in result['ranking']['method']


def test_pinning_selection_does_not_change_its_evidence_rank():
    last = core.advisor(21,10)['candidates'][-1]
    first = core.advisor(21,10,mode='analyze',material=last['material'])['candidates'][0]
    assert first['pinned_selected'] and first['rank']==last['rank'] and first['rank']>1
