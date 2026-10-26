import json
from cadagent.pcb import kicad_report,evidence_bundle,evidence_is_current,check_jlc_files

def test_missing_and_empty_reports_fail_closed(tmp_path):
    p=tmp_path/'report.json'
    assert not kicad_report(p,'erc')['pass']
    p.write_text('{}')
    assert not kicad_report(p,'drc')['pass']
    p.write_text('{"sheets":[]}')
    assert not kicad_report(p,'erc')['pass']

def test_unconnected_and_parity_are_not_hidden_by_clean_violations(tmp_path):
    p=tmp_path/'drc.json'
    p.write_text(json.dumps({'violations':[],'unconnected_items':[{}],'schematic_parity':[{}]}))
    r=kicad_report(p,'drc')
    assert not r['pass'] and r['unconnected']==1 and r['parity']==1

def test_unknown_severity_and_exclusions_do_not_turn_green(tmp_path):
    p=tmp_path/'erc.json'
    for severity in ['mystery','exclusion']:
        p.write_text(json.dumps({'sheets':[{'violations':[{'severity':severity}]}]}))
        assert not kicad_report(p,'erc')['pass']

def test_source_and_report_changes_invalidate_evidence(tmp_path):
    (tmp_path/'board').write_text('original')
    (tmp_path/'erc').write_text('{"sheets":[{"violations":[]}]}')
    bundle=evidence_bundle(tmp_path,{'erc':'erc'},['board'],[{'pass':'true'}])
    assert not bundle['pass'] and not bundle['production_ready']
    assert evidence_is_current(tmp_path,bundle)
    (tmp_path/'board').write_text('changed')
    assert not evidence_is_current(tmp_path,bundle)
    (tmp_path/'board').write_text('original')
    (tmp_path/'erc').write_text('{}')
    assert not evidence_is_current(tmp_path,bundle)

def test_cpl_dnp_or_duplicate_reference_is_rejected(tmp_path):
    b=tmp_path/'bom';c=tmp_path/'cpl'
    b.write_text('Comment,Designator,Footprint,LCSC Part #\nTVS,D1,SOT23,C404012\n')
    c.write_text('Designator,Mid X,Mid Y,Layer,Rotation\nD1,1,2,top,0\nDNP,2,3,top,0\n')
    assert not check_jlc_files(b,c)['pass']
    c.write_text('Designator,Mid X,Mid Y,Layer,Rotation\nD1,1,2,top,0\n')
    assert check_jlc_files(b,c)['pass']
    c.write_text('Designator,Mid X,Mid Y,Layer,Rotation\nD1,nan,2,top,0\n')
    assert not check_jlc_files(b,c)['pass']


def test_incomplete_evidence_cannot_qualify(tmp_path):
    assert not evidence_bundle(tmp_path,{},[],[{'pass':True}])['production_ready']


def test_binding_rejects_reports_older_than_source(tmp_path):
    import os
    (tmp_path/'erc').write_text('{"sheets":[{"violations":[]}]}')
    (tmp_path/'drc').write_text('{"violations":[],"unconnected_items":[],"schematic_parity":[]}')
    (tmp_path/'board').write_text('changed after checks')
    os.utime(tmp_path/'board', ns=(2000000000000000000,2000000000000000000))
    bundle=evidence_bundle(tmp_path,{'erc':'erc','drc':'drc'},['board'],[{'pass':True}])
    assert not bundle['pass'] and not bundle['production_ready']
    assert set(bundle['reports_older_than_source'])=={'erc','drc'}
