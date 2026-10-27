import pytest
from cadagent.markings import PanelMarkings

def test_shared_artwork_proof_escapes_labels_and_preserves_world_axes():
    m=PanelMarkings();m.text('A&B <male>',10,20,3,bold=True);m.line([(1,2),(3,4)],.5)
    svg=m.svg((0,0,40,30))
    assert 'A&amp;B &lt;male&gt;' in svg
    assert 'y="-20"' in svg and '1,-2 3,-4' in svg

def test_marking_strokes_reject_impossible_dimensions():
    m=PanelMarkings()
    with pytest.raises(ValueError):m.circle(0,0,1,3)
    with pytest.raises(ValueError):m.line([(0,0)],.5)

def test_overlapping_strokes_engrave_as_one_valid_part():
    cq=pytest.importorskip('cadquery')
    m=PanelMarkings();m.line([(2,2),(8,2),(8,8)],.6);m.circle(8,8,1,.5)
    source=cq.Solid.makeBox(12,12,2)
    result=m.engrave(source,2,.4)
    assert result.isValid() and len(result.Solids())==1
    assert 0<result.Volume()<source.Volume()
