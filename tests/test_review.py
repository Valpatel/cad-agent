from cadagent.review import review_html

def test_embedded_review_assets_are_local_and_missing_is_visible(tmp_path):
    (tmp_path/'schematic.pdf').write_bytes(b'%PDF-1.4')
    h=review_html(tmp_path,{'groups':[{'title':'PCB <unsafe>','views':[{'kind':'pdf','title':'Circuit','file':'schematic.pdf'},{'kind':'svg','title':'Absent','file':'missing.svg'},{'kind':'html','file':'../outside.html'}]}]})
    assert '<iframe' in h and 'schematic.pdf' in h
    assert 'Pending asset: missing.svg' in h and 'Pending asset: ../outside.html' in h
    assert '&lt;unsafe&gt;' in h
    assert 'data-review-panel="1"' in h and ' hidden' not in h.split('<script>')[0]

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


def test_generic_source_hash_report_is_current_without_pcb_bundle(tmp_path):
    import json, hashlib
    source = tmp_path / 'board.dat'
    source.write_bytes(b'reviewed geometry')
    report = tmp_path / 'routing.json'
    report.write_text(json.dumps({'pass': True, 'source_sha256': {'board.dat': hashlib.sha256(source.read_bytes()).hexdigest()}}))
    manifest = {'groups': [{'reports': [{'file': 'routing.json'}]}]}
    assert '>PASS<' in review_html(tmp_path, manifest)
    source.write_bytes(b'changed geometry')
    assert '>STALE<' in review_html(tmp_path, manifest)


def test_changed_assembly_artifact_cannot_show_pass(tmp_path):
    import json, hashlib
    artifact = tmp_path / 'lid.step'
    artifact.write_bytes(b'original solid')
    (tmp_path / 'fit.json').write_text(json.dumps({'pass': True, 'artifact_sha256': {'lid.step': hashlib.sha256(artifact.read_bytes()).hexdigest()}}))
    manifest = {'groups': [{'reports': [{'file': 'fit.json'}]}]}
    assert '>PASS<' in review_html(tmp_path, manifest)
    artifact.write_bytes(b'changed solid')
    assert '>STALE<' in review_html(tmp_path, manifest)


def test_report_outside_root_is_unavailable(tmp_path):
    import json
    root = tmp_path / 'project'; root.mkdir()
    (tmp_path / 'x.json').write_text(json.dumps({'pass': True}))
    (root / 'link.json').symlink_to(tmp_path / 'x.json')
    for rel in ('../x.json', 'link.json', str(tmp_path / 'x.json')):
        h = review_html(root, {'groups': [{'reports': [{'title': 'DRC', 'file': rel}]}]})
        assert 'UNAVAILABLE' in h and '>PASS<' not in h


def test_downloads_without_file_or_missing_are_pending(tmp_path):
    (tmp_path / 'board.kicad_pcb').write_text('board')
    h = review_html(tmp_path, {'groups': [{'title': 'x', 'downloads': [
        {'title': 'PCB source'}, {'title': 'Gerbers', 'file': 'missing.zip'}, {'file': '../outside.zip'},
        {'title': 'Board', 'file': 'board.kicad_pcb'}]}]})
    assert 'Pending download: PCB source' in h and 'Pending download: Gerbers' in h
    assert 'Pending download: outside.zip' in h and 'href="../missing.zip"' not in h
    assert '<a href="../board.kicad_pcb">Board</a>' in h


def test_workbench_works_as_a_static_page(tmp_path):
    (tmp_path / 'a.svg').write_text('<svg/>'); (tmp_path / 'b.svg').write_text('<svg/>')
    h = review_html(tmp_path, {'groups': [{'title': 'One', 'views': [{'kind': 'svg', 'file': 'a.svg'}, {'kind': 'svg', 'file': 'b.svg'}]},
                                          {'title': 'Two', 'views': [{'kind': 'model', 'file': 'b.svg'}]}]})
    markup, script = h.split('<script>')
    assert ' hidden' not in markup and 'data-review-group-panel="1"' in markup   # every panel reachable without JS
    assert '/_cadagent/kit/' not in script and 'data-review-group-panel' in script   # inlined, no server path
    assert 'cad-agent site --serve' in markup   # the model view says it needs the local server


def test_view_group_cannot_clobber_the_main_manifest_or_fail_after_writing(tmp_path):
    from types import SimpleNamespace
    from cadagent.project import CadConfigError
    from cadagent.view import export_view
    import json, pytest
    exports = tmp_path / 'exports'; exports.mkdir()
    (exports / 'a_base.step').write_text('not read: validation runs first')
    (tmp_path / 'parts.json').write_text(json.dumps({'a_base': {}}))
    for groups, message in (([{'id': 'view', 'prefix': 'a_'}], 'reserved'), ([{'id': 'two', 'prefix': '2port_'}], 'no parts')):
        project = SimpleNamespace(view={'groups': groups}, exports_dir=exports, parts_file=tmp_path / 'parts.json',
                                  root=tmp_path, part_ids={}, title='T')
        with pytest.raises(CadConfigError, match=message):
            export_view(project)
        assert not (exports / 'view').exists()


def test_bad_view_group_is_a_clean_cli_error(tmp_path, capsys):
    import json
    from cadagent.cli import main
    (tmp_path / 'cad-agent.yaml').write_text('cad:\n  title: T\n  parts_file: parts.json\n  view:\n    groups: [{id: view, prefix: a_}]\n')
    (tmp_path / 'parts.json').write_text(json.dumps({'a_base': {}}))
    (tmp_path / 'exports').mkdir(); (tmp_path / 'exports' / 'a_base.step').write_text('x')
    assert main(['view', '--project', str(tmp_path)]) == 2
    assert 'reserved' in capsys.readouterr().err
