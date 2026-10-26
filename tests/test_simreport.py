"""Simulation report page: comparison words, media and limits."""

from __future__ import annotations

from cadagent.simreport import metric, render, write_report


def test_changes_are_judged_and_worded():
    page = render('T', [{'id': 'a', 'title': 'A', 'metrics': [
        metric('grams', 100, 80, 'g', better='lower'),
        metric('safety factor', 3.0, 2.0, '', better='higher'),
        metric('same', 1.0, 1.0),
        metric('neutral', 1.0, 2.0, better=None)]}])
    assert 'better' in page and 'worse' in page and '= same' in page
    assert '(-20 %)' in page and '(-33 %)' in page


def test_media_limits_and_escaping(tmp_path):
    p = write_report(tmp_path / 'r.html', 'Title <x>', [{'id': 's', 'title': 'S', 'figures': [{'src': 'a.png', 'caption': 'cap'}],
                                                        'videos': [{'src': 'v.mp4', 'caption': 'vid'}], 'limits': ['steady RANS']}])
    t = p.read_text()
    assert 'Title &lt;x&gt;' in t and '<video src="v.mp4"' in t and 'steady RANS' in t and 'prefers-color-scheme' in t
