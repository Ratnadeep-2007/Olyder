"""Policy decisions never select or omit acceptance checks."""
import pytest
from olyder.policy import RunPolicy, progress


@pytest.mark.parametrize('mode,patience', [('economy',1),('balanced',2),('thorough',3)])
def test_modes_bound_stagnation(mode, patience):
    policy = RunPolicy(mode)
    assert policy.no_progress_limit == patience


@pytest.mark.parametrize('mode', ['economy','balanced','thorough'])
def test_all_modes_reserve_final_time(mode):
    assert not RunPolicy(mode, final_seconds=10).admit_builder(9)
    assert RunPolicy(mode, final_seconds=10).admit_builder(11)


@pytest.mark.parametrize('status', ['blocked','needs_review','unexecuted'])
def test_unexecuted_is_not_progress(status):
    delta = progress([{'id':'x','status':'fail'}], [{'id':'x','status':status}])
    assert not delta['newly_passing']
    assert not delta['improved']


def test_progress_is_check_specific():
    delta = progress([{'id':'a','status':'fail'},{'id':'b','status':'pass'}],
                     [{'id':'a','status':'pass'},{'id':'b','status':'fail'}])
    assert delta['newly_passing'] == ['a']
    assert delta['regressions'] == ['b']
    assert not delta['improved']


def test_fewer_failures_with_real_pass_is_progress():
    assert progress([{'id':'a','status':'fail'}], [{'id':'a','status':'pass'}])['improved']


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        RunPolicy('cheap')
