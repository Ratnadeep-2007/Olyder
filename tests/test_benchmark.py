from olyder.benchmark import scenarios, benchmark


def test_ten_executable_scenarios():
    cases=scenarios()
    assert len(cases)>=10
    assert len({c['id'] for c in cases})==len(cases)
    assert any(c['expected']=='failed' for c in cases)
    assert any(c['expected']=='blocked' for c in cases)


def test_real_paired_fixture(tmp_path):
    result=benchmark(tmp_path/'bench.json',repetitions=1,task_ids={'calculation'})
    assert len(result['rows'])==4
    assert all(r['status']=='passed' for r in result['rows'])
    assert result['actual_provider_usd'] is None
    assert result['cost_savings_claim']=='inconclusive'
