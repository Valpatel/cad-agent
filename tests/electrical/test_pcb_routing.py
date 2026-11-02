import pytest
from cadagent.electrical.pcb_routing import copper_graph,shortest_path,path_segments,pair_geometry

def seg(a,b,layer='F.Cu',width=.25):return dict(a=a,b=b,layer=layer,width=width)

def test_trunk_length_excludes_a_termination_branch():
    graph=copper_graph([seg((0,0),(20,0)),seg((5,0),(5,4))],[])
    length,path=shortest_path(graph,(0,0,'F.Cu'),(20,0,'F.Cu'))
    assert length==20
    assert (5,0,'F.Cu') in path
    assert (5,4,'F.Cu') not in path

def test_crossing_layers_do_not_connect_without_via():
    segments=[seg((0,0),(5,0)),seg((5,0),(10,0),'B.Cu')]
    graph=copper_graph(segments,[])
    with pytest.raises(ValueError,match='Disconnected'):shortest_path(graph,(0,0,'F.Cu'),(10,0,'B.Cu'))
    graph=copper_graph(segments,[dict(xy=(5,0),layers=['F.Cu','B.Cu'])])
    assert shortest_path(graph,(0,0,'F.Cu'),(10,0,'B.Cu'))[0]==pytest.approx(11.6)

def test_pair_measurement_detects_separated_tracks_and_missing_layer():
    h=[seg((0,0),(10,0))];l=[seg((0,.5),(10,.5))]
    good=pair_geometry(h,l)
    assert good['edge_gap_min_mm']==pytest.approx(.25)
    assert good['edge_gap_max_mm']==pytest.approx(.25)
    bad=pair_geometry(h,[seg((0,.5),(10,3))])
    assert bad['edge_gap_max_mm']>2
    assert pair_geometry(h,[seg((0,.5),(10,.5),'B.Cu')])['missing_peer_layer_mm']==pytest.approx(20)
