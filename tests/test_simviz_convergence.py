"""convergence_chart: the whole run, a solids panel only when there are solid regions, the monitored values the
convergence claim rests on with their units, a run that stopped early said so, and a panel with no data saying why.
Drawn from recorded-format runs (tests/fixtures/cfd_runs); no solver runs."""

from __future__ import annotations

import warnings

import pytest

matplotlib = pytest.importorskip('matplotlib')
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.text import Text  # noqa: E402

from cadagent.simulation import cfd, simviz  # noqa: E402

from .cfd_fixtures import recorded  # noqa: E402

FIELDS = ['Ux', 'Uy', 'Uz', 'h', 'k', 'omega', 'p_rgh']


def _figure(results):
    with warnings.catch_warnings():
        warnings.simplefilter('error', UserWarning)          # a missing glyph (° ³ −) or a layout that does not fit
        fig = simviz._convergence_figure(results, 'Solver convergence')
        fig.canvas.draw()
    box = fig.bbox
    ticks = {id(lb) for ax in fig.findobj(Axes) for axis in (ax.xaxis, ax.yaxis)
             for tk in axis.get_major_ticks() + axis.get_minor_ticks() for lb in (tk.label1, tk.label2)}
    for txt in fig.findobj(Text):                            # every caption and label fits on the page
        if txt.get_visible() and txt.get_text().strip() and id(txt) not in ticks:
            e = txt.get_window_extent(fig.canvas.get_renderer())
            assert box.x0 - 1 <= e.x0 and e.x1 <= box.x1 + 1 and box.y0 - 1 <= e.y0 and e.y1 <= box.y1 + 1, txt.get_text()
    return fig


def _panels(fig):
    return {ax.get_title(loc='left'): ax for ax in fig.findobj(Axes) if ax.get_title(loc='left')}


def _words(obj):
    return ' '.join(' '.join(t.get_text() for t in obj.findobj(Text)).split())      # wrapped lines read as one


def _vlines(ax, colour=None):
    return sorted(ln.get_xdata()[0] for ln in ax.get_lines()
                  if len(ln.get_xdata()) == 2 and ln.get_xdata()[0] == ln.get_xdata()[1]
                  and (colour is None or ln.get_color() == colour))


def test_a_case_without_solids_has_no_solids_panel_and_shows_the_whole_run(tmp_path):
    r = cfd.read_results(recorded('fins-no-solids', tmp_path))
    fig = _figure(r)
    p = _panels(fig)
    assert list(p) == ['Initial residuals of the air solution', 'Air temperature', 'Fan flow', 'Heat leaving with the air']
    res = p['Initial residuals of the air solution']
    lines = {ln.get_label(): ln for ln in res.get_lines() if ln.get_label() in FIELDS}
    assert sorted(lines) == sorted(FIELDS)                                  # p_rgh is no longer dropped
    for ln in lines.values():
        assert ln.get_xdata()[0] == 1 and ln.get_xdata()[-1] == 320
    assert res.get_yscale() == 'log' and res.get_ylabel() == 'initial residual (no unit)' and res.get_xlabel() == 'iteration'
    assert _vlines(res, simviz.MUTED) == [200, 260]                         # each continuation marked
    w0, w1 = r['convergence_window']
    head = _words(fig)
    assert 'Iterations 1–320 in 3 solves' in head and f'iterations {w0}–{w1}' in head
    assert [p[t].get_ylabel() for t in ('Air temperature', 'Fan flow', 'Heat leaving with the air')] == \
        ['temperature (°C)', 'flow (m³/h)', 'heat (W)']
    air = p['Air temperature']
    assert {ln.get_label() for ln in air.get_lines()} >= {'fins: mean in the block', 'fan: air through the fan'}
    assert 'Change over the shaded window: fins' in _words(air)
    assert f"fins {r['zones']['fins']['T_c']:.1f} °C" in _words(air)       # each line named at its end, with its unit
    # each change with the limit steady holds it to: 1 °C for the block's air and the fan's intake air alike
    assert _words(air).count('(limit ±1 °C)') == 2 and '(limit ±2 °C)' not in _words(air)
    assert '(limit ±2 %)' in _words(p['Fan flow'])
    heat = p['Heat leaving with the air']
    assert 'heat put in, 40 W' in [ln.get_label() for ln in heat.get_lines()]
    assert 'energy balance' in _words(heat) and '(limit ±5 %)' in _words(heat)
    assert 'not that the answer is right' in head
    matplotlib.pyplot.close(fig)


def test_a_multi_region_run_that_stopped_early(tmp_path):
    r = cfd.read_results(recorded('solids-ended-early', tmp_path))
    fig = _figure(r)
    p = _panels(fig)
    assert list(p) == ['Initial residuals of the air solution', 'Hottest temperature in each solid region',
                       'Heat leaving with the air']
    solids = p['Hottest temperature in each solid region']
    got = {ln.get_label(): ln for ln in solids.get_lines() if ln.get_label() in ('chip', 'plate')}
    assert set(got) == {'chip', 'plate'}
    for ln in got.values():
        assert ln.get_xdata()[0] == 10 and ln.get_xdata()[-1] == 230
    assert solids.get_ylabel() == 'temperature (°C)'
    assert 'Stopped early at iteration 236 of 300 planned' in _words(fig)
    for ax in p.values():
        assert _vlines(ax, simviz.ACCENT) == [236]                          # the stop, on every panel
    assert 'Change over the shaded window' not in _words(fig)               # nothing was measured, so nothing is claimed
    matplotlib.pyplot.close(fig)


def _shaded(ax):
    """The x range of the shaded convergence window."""
    for pt in ax.patches:
        if matplotlib.colors.to_hex(pt.get_facecolor()) == simviz.WINDOW:
            xs = pt.get_path().transformed(pt.get_patch_transform()).vertices[:, 0] if hasattr(pt, 'get_width') \
                else pt.get_xy()[:, 0]
            return [float(xs.min()), float(xs.max())]
    return None


def test_a_continuation_from_the_same_saved_time_is_drawn(tmp_path):
    # the stopped solve's run continued again from 200 and finished: the chart shows it, and no stop
    r = cfd.read_results(recorded('solids-continued-again', tmp_path))
    fig = _figure(r)
    p = _panels(fig)
    head = _words(fig)
    assert 'Iterations 1–300 in 4 solves (thin lines: continuations from 100, 200 (2×))' in head
    assert 'Stopped early' not in head
    solids = p['Hottest temperature in each solid region']
    for ln in solids.get_lines():
        if ln.get_label() in ('chip', 'plate'):
            assert ln.get_xdata()[-1] == 300
    for ax in p.values():
        assert _vlines(ax, simviz.ACCENT) == [] and _shaded(ax) == [240, 300]
    assert f"chip {simviz._change('chip_max_c_change', r['convergence']['chip_max_c_change'])} (limit ±1 °C)" in _words(solids)
    matplotlib.pyplot.close(fig)


def test_a_crashed_continuation_shades_rows_the_lines_show(tmp_path):
    # the continuation from 100 crashed at start; the window and the headline values are the first solve's last rows,
    # and so are the lines' ends
    r = cfd.read_results(recorded('solids-crashed-restart', tmp_path))
    fig = _figure(r)
    p = _panels(fig)
    assert 'Iterations 1–150. Shaded: the window the convergence check measured, iterations 120–150.' in _words(fig)
    assert 'Stopped early at iteration 150 of 300 planned' in _words(fig)
    for ax in p.values():
        assert _vlines(ax, simviz.ACCENT) == [150] and _vlines(ax, simviz.MUTED) == []
        assert _shaded(ax) == [120, 150]
        ends = [ln.get_xdata()[-1] for ln in ax.get_lines() if len(ln.get_xdata()) > 2]
        assert ends and max(ends) == 150
    matplotlib.pyplot.close(fig)


def test_a_continuation_that_stopped_before_its_first_sample_shades_nothing(tmp_path):
    # the continuation from 100 stopped at 104, before its first temperature sample: the lines stop at 100, where it
    # began, and the solve before it is not shaded as if it were the newest one
    r = cfd.read_results(recorded('solids-short-continuation', tmp_path))
    fig = _figure(r)
    p = _panels(fig)
    head = _words(fig)
    assert 'Iterations 1–104 in 2 solves (thin lines: continuations from 100).' in head and 'Shaded' not in head
    assert 'Stopped early at iteration 104 of 300 planned' in head
    assert 'Change over the shaded window' not in head
    for title, ax in p.items():
        assert _vlines(ax, simviz.ACCENT) == [104] and _vlines(ax, simviz.MUTED) == [100] and _shaded(ax) is None
        ends = [ln.get_xdata()[-1] for ln in ax.get_lines() if len(ln.get_xdata()) > 2]
        assert ends and max(ends) == (104 if title.startswith('Initial residuals') else 100)
    matplotlib.pyplot.close(fig)


def test_panels_without_data_say_why():
    fig = _figure({'solids': {'chip': {}}, 'T_max_history': {}, 'residuals': {}, 'monitors': {}, 'restarts': [],
                   'convergence': {}})
    p = _panels(fig)
    assert list(p) == ['Initial residuals of the air solution', 'Hottest temperature in each solid region', 'Monitored values']
    assert 'No residual output found' in _words(p['Initial residuals of the air solution'])
    assert 'No temperature history for the solid regions (chip)' in _words(p['Hottest temperature in each solid region'])
    assert 'No fan-zone, fin-zone or heat-flux output was found' in _words(p['Monitored values'])
    for ax in p.values():
        assert not ax.axison and not ax.get_lines()                         # no empty frames
    matplotlib.pyplot.close(fig)


def test_results_saved_before_whole_run_histories_say_what_they_hold(tmp_path):
    r = cfd.read_results(recorded('fins-no-solids', tmp_path))
    # what read_results returned before: the newest solve's residuals only, no monitors, restarts or window
    keep = [i for i, t in enumerate(r['residuals']['iteration']) if t > 260]
    r['residuals'] = {k: [v[i] for i in keep] for k, v in r['residuals'].items()}
    for k in ('restarts', 'monitors', 'convergence_window', 'residuals_every', 'planned_iterations'):
        del r[k]
    fig = _figure(r)
    p = _panels(fig)
    assert list(p) == ['Initial residuals of the air solution', 'Monitored values']
    assert 'These results hold iterations 261–320 only' in _words(fig)
    assert p['Initial residuals of the air solution'].get_xlabel() == \
        'iteration (261–320 only: earlier iterations are not in these results)'
    said = _words(p['Monitored values'])
    assert 'Their histories are not in these results' in said and 'fins air in the block' in said and 'fan flow' in said
    matplotlib.pyplot.close(fig)


def test_the_chart_is_written_on_the_site_paper(tmp_path):
    Image = pytest.importorskip('PIL.Image')
    r = cfd.read_results(recorded('solids-ended-early', tmp_path))
    out = simviz.convergence_chart(r, tmp_path / 'convergence.png', title='Chip on a plate: convergence')
    im = Image.open(out).convert('RGB')
    assert im.width == 12 * 120
    assert im.getpixel((3, 3)) == tuple(int(simviz.PAPER[i:i + 2], 16) for i in (1, 3, 5))
