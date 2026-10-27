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
    p.write_text(json.dumps({'included_severities':['error','warning','exclusion'],'violations':[],'unconnected_items':[{}],'schematic_parity':[{}]}))
    r=kicad_report(p,'drc')
    assert not r['pass'] and r['unconnected']==1 and r['parity']==1

def test_unknown_severity_and_exclusions_do_not_turn_green(tmp_path):
    p=tmp_path/'erc.json'
    for severity in ['mystery','exclusion']:
        p.write_text(json.dumps({'included_severities':['error','warning','exclusion'],'sheets':[{'violations':[{'severity':severity}]}]}))
        r=kicad_report(p,'erc')
        assert not r['pass'] and 'filtered' not in r['reason']

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


ALL = ['error', 'warning', 'exclusion']
CLEAN_ERC = {'included_severities': ALL, 'ignored_checks': [], 'sheets': [{'violations': []}]}
CLEAN_DRC = {'included_severities': ALL, 'ignored_checks': [], 'violations': [], 'unconnected_items': [], 'schematic_parity': []}


def _clean_reports(root):
    (root/'erc.json').write_text(json.dumps(CLEAN_ERC))
    (root/'drc.json').write_text(json.dumps(CLEAN_DRC))
    (root/'board.kicad_pcb').write_text('board')
    import os
    os.utime(root/'board.kicad_pcb', ns=(1, 1))
    return {'erc': 'erc.json', 'drc': 'drc.json'}


def test_clean_full_severity_reports_pass(tmp_path):
    bundle = evidence_bundle(tmp_path, _clean_reports(tmp_path), ['board.kicad_pcb'], [{'id': 'fit', 'pass': True}])
    assert bundle['pass'] and bundle['production_ready'] and evidence_is_current(tmp_path, bundle)


def test_filtered_severities_fail(tmp_path):
    # kicad-cli --severity-error writes included_severities ["error"]; the default run omits exclusions
    p = tmp_path/'drc.json'
    for severities in (['error'], ['error', 'warning'], None):
        p.write_text(json.dumps(dict(CLEAN_DRC, included_severities=severities)))
        r = kicad_report(p, 'drc')
        assert not r['pass'] and 'filtered severities' in r['reason']
    p.write_text(json.dumps({k: v for k, v in CLEAN_DRC.items() if k != 'included_severities'}))
    assert not kicad_report(p, 'drc')['pass']


def test_ignored_and_excluded_checks_fail_unless_waived_by_name(tmp_path):
    p = tmp_path/'drc.json'
    p.write_text(json.dumps(dict(CLEAN_DRC, ignored_checks=[{'key': 'missing_courtyard', 'description': 'x'}],
                                 violations=[{'severity': 'exclusion', 'type': 'clearance'}])))
    r = kicad_report(p, 'drc')
    assert not r['pass'] and r['ignored_checks'] == ['missing_courtyard'] and r['excluded_checks'] == ['clearance']
    assert r['unwaived'] == ['clearance', 'missing_courtyard']
    r = kicad_report(p, 'drc', {'missing_courtyard': 'logos have no courtyard'})
    assert not r['pass'] and r['unwaived'] == ['clearance']
    r = kicad_report(p, 'drc', {'missing_courtyard': 'logos have no courtyard', 'clearance': 'reviewed net tie'})
    assert r['pass'] and r['waived'] == {'missing_courtyard': 'logos have no courtyard', 'clearance': 'reviewed net tie'}
    assert not kicad_report(p, 'drc', {'missing_courtyard': ' ', 'clearance': 'x'})['pass']   # a waiver needs a reason


def test_waiver_counts_cap_and_unused_waivers(tmp_path):
    p = tmp_path/'drc.json'
    p.write_text(json.dumps(dict(CLEAN_DRC, violations=[{'severity': 'exclusion', 'type': 'clearance'}] * 3)))
    r = kicad_report(p, 'drc', {'clearance': 'reviewed net ties', 'silk_overlap': 'logos'})
    assert r['pass'] and r['waived_counts'] == {'clearance': 3} and r['unused_waivers'] == ['silk_overlap']
    r = kicad_report(p, 'drc', {'clearance': {'reason': 'two reviewed net ties', 'max': 2}})
    assert not r['pass'] and r['unwaived'] == ['clearance'] and '3 excluded, waiver allows 2' in r['reason']
    assert kicad_report(p, 'drc', {'clearance': {'reason': 'three reviewed net ties', 'max': 3}})['pass']
    for bad in ({'clearance': {'reason': 'x', 'max': -1}}, {'clearance': {'reason': 'x', 'max': True}},
                {'clearance': {'max': 3}}, {'clearance': {'reason': 'x', 'cap': 3}}):
        assert not kicad_report(p, 'drc', bad)['pass']


def test_paths_outside_the_root_fail(tmp_path):
    import os
    root = tmp_path/'project'; root.mkdir()
    reports = _clean_reports(root)
    (tmp_path/'outside.kicad_pcb').write_text('outside')
    os.utime(tmp_path/'outside.kicad_pcb', ns=(1, 1))
    bundle = evidence_bundle(root, reports, ['../outside.kicad_pcb'], [])
    assert not bundle['pass'] and 'outside the project root' in bundle['problems'][0]
    (root/'link.kicad_pcb').symlink_to(tmp_path/'outside.kicad_pcb')
    bundle = evidence_bundle(root, reports, ['link.kicad_pcb'], [])
    assert not bundle['pass'] and not evidence_is_current(root, bundle)
    # a hand-written bundle pointing outside is never current
    good = evidence_bundle(root, reports, ['board.kicad_pcb'], [])
    import hashlib
    forged = dict(good, source_sha256={'../outside.kicad_pcb': hashlib.sha256(b'outside').hexdigest()})
    assert evidence_is_current(root, good) and not evidence_is_current(root, forged)


def test_malformed_manifest_fails_cleanly(tmp_path):
    reports = _clean_reports(tmp_path)
    (tmp_path/'hardware').mkdir()
    for args in [(dict(reports, sch='x.json'), ['board.kicad_pcb'], []),
                 (reports, ['board.kicad_pcb'], ['physical-fit']),
                 (reports, 'board.kicad_pcb', []),
                 (['erc.json'], ['board.kicad_pcb'], []),
                 (reports, ['board.kicad_pcb'], [], {'missing_courtyard': ''})]:
        bundle = evidence_bundle(tmp_path, *args)
        assert not bundle['pass'] and bundle['problems']
    bundle = evidence_bundle(tmp_path, reports, ['hardware'], [])
    assert not bundle['pass'] and 'not a regular file' in bundle['problems'][0]


def test_pcb_check_cli_rejects_malformed_manifest(tmp_path, capsys):
    from cadagent.cli import main
    (tmp_path/'cad-agent.yaml').write_text('cad:\n  title: Board\n')
    reports = _clean_reports(tmp_path)
    (tmp_path/'m.json').write_text(json.dumps({'reports': dict(reports, sch='x'), 'sources': ['board.kicad_pcb'],
                                               'release_gates': ['physical-fit']}))
    assert main(['pcb-check', 'm.json', '--project', str(tmp_path)]) == 2
    assert 'unknown report kinds' in capsys.readouterr().err and not (tmp_path/'exports').exists()
    (tmp_path/'m.json').write_text('not json')
    assert main(['pcb-check', 'm.json', '--project', str(tmp_path)]) == 2
    (tmp_path/'m.json').write_text(json.dumps({'reports': reports, 'sources': ['board.kicad_pcb'], 'release_gates': []}))
    assert main(['pcb-check', 'm.json', '--project', str(tmp_path)]) == 0


def test_short_or_long_csv_rows_are_reported_not_raised(tmp_path):
    b = tmp_path/'bom'; c = tmp_path/'cpl'
    b.write_text('Comment,Designator,Footprint,LCSC Part #\n100n,C1\n')
    c.write_text('Designator,Mid X,Mid Y,Layer,Rotation\nC1,1,2,top,0\n')
    r = check_jlc_files(b, c)
    assert not r['pass'] and any('LCSC' in e for e in r['errors'])
    b.write_text('Comment,Designator\n100n\n')
    c.write_text('Designator,Mid X\n\nC1\n')
    assert not check_jlc_files(b, c)['pass']
    b.write_text('Comment,Designator,Footprint,LCSC Part #\n100n,C1,0402,C1525,extra\n')
    r = check_jlc_files(b, c)
    assert not r['pass'] and any('more fields' in e for e in r['errors'])
