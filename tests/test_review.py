from cadagent.review import review_html

def test_embedded_review_assets_are_local_and_missing_is_visible(tmp_path):
    (tmp_path/'schematic.pdf').write_bytes(b'%PDF-1.4')
    h=review_html(tmp_path,{'groups':[{'title':'PCB <unsafe>','views':[{'kind':'pdf','title':'Circuit','file':'schematic.pdf'},{'kind':'svg','title':'Absent','file':'missing.svg'},{'kind':'html','file':'../outside.html'}]}]})
    assert '<iframe' in h and 'schematic.pdf' in h
    assert 'Pending asset: missing.svg' in h and 'Pending asset: ../outside.html' in h
    assert '&lt;unsafe&gt;' in h
    assert 'data-review-panel="1" hidden' in h

def test_missing_check_cannot_show_pass(tmp_path):
    h=review_html(tmp_path,{'groups':[{'reports':[{'title':'DRC','file':'missing.json'}]}]})
    assert 'UNAVAILABLE' in h and '>PASS<' not in h


def test_model_review_uses_existing_toolkit_viewer(tmp_path):
    (tmp_path/'view.json').write_text('{}')
    h=review_html(tmp_path,{'groups':[{'views':[{'kind':'model','title':'Assembly','file':'view.json'}]}]})
    assert '/_cadagent/kit/viewer.html?manifest=/view.json' in h and '<iframe' in h


def test_variant_manifests_do_not_mix_assemblies():
    from cadagent.view import group_manifests
    import pytest
    source={'parts':[{'name':'a_base','visible':False},{'name':'b_base','visible':True}]}
    groups=group_manifests(source,[{'id':'a','prefix':'a_'}])
    assert groups['a']['parts']==[{'name':'a_base','visible':True}]
    assert source['parts'][0]['visible'] is False
    with pytest.raises(ValueError):group_manifests(source,[{'id':'../bad','prefix':'a_'}])
    with pytest.raises(ValueError):group_manifests(source,[{'id':'empty','prefix':'missing_'}])


def test_changed_mechanical_source_cannot_show_pass(tmp_path):
    import json,hashlib
    source=tmp_path/'parameters.json';source.write_text('{"width": 10}')
    report=tmp_path/'fit.json';report.write_text(json.dumps({'pass':True, 'mechanical_sources':{'parameters.json':hashlib.sha256(source.read_bytes()).hexdigest()}}))
    manifest={'groups':[{'reports':[{'file':'fit.json'}]}]}
    assert '>PASS<' in review_html(tmp_path,manifest)
    source.write_text('{"width": 20}')
    assert '>STALE<' in review_html(tmp_path,manifest)
