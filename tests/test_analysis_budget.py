import json

from olyder.analysis import run_analysis


class Provider:
    api_version=1
    calls=0
    def complete(self,*args,**kwargs):
        self.calls+=1
        return {'content':'[]','provider':'fixture','model':'fixture',
                'usage':{'input_tokens':10,'output_tokens':2,'total_tokens':12}}


def spec(tmp_path,budget):
    path=tmp_path/'olyder.json';path.write_text(json.dumps({'goal':'plan','budget':budget,
        'checks':[{'id':'file','type':'file','path':'value'}]}))
    return path


def test_planner_records_dollars_and_token_provenance(tmp_path):
    provider=Provider()
    result=run_analysis('plan',spec(tmp_path,{'max_cost_usd':'1','planner_upper_bound_usd':'0.1'}),
                        use_ai=True,model_provider=provider)
    assert result['status']=='planned_not_verified'
    assert result['accounting']['observations'][0]['role']=='planner'
    assert result['accounting']['observations'][0]['observed_tokens']==12
    assert result['budget_verdict']=='unknown'
    assert not result['verification_performed']
    assert provider.calls==1


def test_planner_cannot_bypass_monetary_cap(tmp_path):
    provider=Provider()
    result=run_analysis('plan',spec(tmp_path,{'max_cost_usd':'0.01','planner_upper_bound_usd':'0.1'}),
                        use_ai=True,model_provider=provider)
    assert result['status']=='budget_exhausted'
    assert provider.calls==0


def test_research_without_sources_does_not_call_model(tmp_path):
    provider=Provider()
    result=run_analysis('idea',spec(tmp_path,{'max_cost_usd':'1'}),use_ai=True,model_provider=provider)
    assert result['status']=='needs_research'
    assert provider.calls==0
    assert result['accounting']['observations']==[]
