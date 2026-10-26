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
