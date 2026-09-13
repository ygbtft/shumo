"""Q3 certificates must bind reception, source domain, route, and full partition."""
import copy
import pytest
from integer_visibility_certificate import certify_integer_omni_stations,verify_integer_omni_certificate
from visibility_certificate import verify_omni_cells

POINTS=[[0,0],[1099,0],[573,945],[-514,978],[-1104,63],[-624,-923],[600,-1119]]

@pytest.fixture
def certificate():
    result=certify_integer_omni_stations(POINTS)
    assert result['covered']
    return result

@pytest.mark.parametrize('verifier',[verify_integer_omni_certificate,verify_omni_cells])
def test_full_partition_with_outside_leaves(certificate,verifier):
    result=verifier(POINTS,certificate,route=POINTS[::-1])
    assert result['full_root_partition']

@pytest.mark.parametrize('verifier',[verify_integer_omni_certificate,verify_omni_cells])
@pytest.mark.parametrize('mutation',['inside_gap','outside_gap','duplicate','false_outside',
                                   'bad_id','wrong_radius','wrong_problem','moved_station','missing_route_point'])
def test_reject_false_guarantees(certificate,verifier,mutation):
    c=copy.deepcopy(certificate);points=copy.deepcopy(POINTS);route=copy.deepcopy(POINTS)
    inside=next(i for i,v in enumerate(c['cells']) if v[3])
    outside=next(i for i,v in enumerate(c['cells']) if not v[3])
    if mutation=='inside_gap':c['cells'].pop(inside)
    elif mutation=='outside_gap':c['cells'].pop(outside)
    elif mutation=='duplicate':c['cells'].append(c['cells'][inside])
    elif mutation=='false_outside':c['cells'][inside][3]=[]
    elif mutation=='bad_id':c['cells'][inside][3]=[-1]
    elif mutation=='wrong_radius':c['receive_radius']=1500
    elif mutation=='wrong_problem':c['problem']=4
    elif mutation=='moved_station':points[1]=[1950,1950];route=points
    elif mutation=='missing_route_point':route.pop()
    with pytest.raises(ValueError):verifier(points,c,route=route)

def test_center_hole_cannot_pass():
    # Boundary cover by itself is insufficient when the origin scan is removed.
    result=certify_integer_omni_stations(POINTS[1:])
    assert result['covered'] is False
