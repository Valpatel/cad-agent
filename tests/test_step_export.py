"""Reproducible STEP export: ``cadagent.geometry.export_step`` and ``step_timestamp`` (#91).

The time-stamp tests need no CAD kernel, so they run in the core CI job; the export tests need CadQuery (OCP) and
skip without it. Shapes are kept tiny.
"""

from __future__ import annotations

import re
import time

import pytest

from cadagent import geometry


# ----------------------------------------------------------------------------------- the header time stamp

def test_the_time_stamp_is_a_fixed_date_without_source_date_epoch(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert geometry.step_timestamp() == geometry.STEP_DATE == "2000-01-01T00:00:00"
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "")                    # set but empty counts as unset
    assert geometry.step_timestamp() == geometry.STEP_DATE


def test_the_time_stamp_follows_source_date_epoch_in_utc(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")                # the local zone must not matter
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
        assert geometry.step_timestamp() == "2023-11-14T22:13:20"
        monkeypatch.setenv("SOURCE_DATE_EPOCH", "0")
        assert geometry.step_timestamp() == "1970-01-01T00:00:00"
    finally:
        monkeypatch.undo()
        if hasattr(time, "tzset"):
            time.tzset()


@pytest.mark.parametrize("bad", ["-1", "1.5", "1e9", "soon", "１２", "99999999999999999999"])
def test_a_malformed_source_date_epoch_is_an_error_not_ignored(monkeypatch, bad):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", bad)
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        geometry.step_timestamp()


# ----------------------------------------------------------------------------------- export_step (CadQuery)

@pytest.fixture
def cq(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    return pytest.importorskip("cadquery")


def _two_boxes(cq):
    return cq.Compound.makeCompound([cq.Solid.makeBox(1, 1, 1),
                                     cq.Solid.makeBox(1, 1, 1).translate(cq.Vector(3, 0, 0))])


def _file_name(path):
    """The FILE_NAME record of the header, with OCCT's line wrapping removed."""
    head = path.read_text().split("ENDSEC;")[0]
    return re.sub(r"\n\s*", "", re.search(r"FILE_NAME\(.*?\);", head, re.S).group(0))


def _records(path):
    """The DATA section as one string per record, line wrapping removed."""
    data = path.read_text().split("DATA;", 1)[1].split("ENDSEC;", 1)[0]
    return [r for r in re.sub(r"\r?\n\s*", "", data).split(";") if r]


def _read_back(path):
    """(product names, assembly-link ids) as OCCT's reader reads the file."""
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.STEPControl import STEPControl_Reader
    from OCP.StepBasic import StepBasic_Product
    from OCP.StepRepr import StepRepr_NextAssemblyUsageOccurrence

    reader = STEPControl_Reader()
    assert reader.ReadFile(str(path)) == IFSelect_ReturnStatus.IFSelect_RetDone
    model = reader.StepModel()

    def strings(kind, field):
        out, it = [], model.Entities()
        it.SelectType(kind.get_type_descriptor_s(), True)
        it.Start()
        while it.More():
            out.append(getattr(it.Value(), field)().ToCString())
            it.Next()
        return out

    return strings(StepBasic_Product, "Name"), strings(StepRepr_NextAssemblyUsageOccurrence, "Id")


def test_the_same_shape_exported_seconds_apart_is_the_same_bytes(tmp_path, cq):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    box = cq.Workplane().box(2, 3, 4)
    for folder in ("a", "b"):
        geometry.export_step(box, tmp_path / folder / "box.step")
        geometry.export_step(_two_boxes(cq), tmp_path / folder / "two.step")
        # Other exports in between move OCCT's per-process product and assembly-link counters on.
        cq.exporters.export(cq.Workplane().box(1, 1, 1), str(tmp_path / folder / "other.step"))
        geometry.export_step(cq.Workplane().sphere(1), tmp_path / folder / "ball.step")
        if folder == "a":
            time.sleep(1.1)                          # the header's time stamp has one-second resolution
    for name in ("box.step", "two.step"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name
    assert "Open CASCADE STEP translator" not in (tmp_path / "a" / "box.step").read_text()
    assert not list(tmp_path.glob("*/.*.part"))      # no temporary file left behind


def test_the_header_names_the_file_and_its_date_follows_source_date_epoch(tmp_path, cq, monkeypatch):
    out = geometry.export_step(cq.Workplane().box(1, 2, 3), tmp_path / "part.step")
    assert out == tmp_path / "part.step"
    assert _file_name(out).startswith("FILE_NAME('part.step','2000-01-01T00:00:00',")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    geometry.export_step(cq.Workplane().box(1, 2, 3), out)
    assert _file_name(out).startswith("FILE_NAME('part.step','2023-11-14T22:13:20',")


def test_the_product_is_named_after_the_file_or_the_name_given(tmp_path, cq):
    plain = geometry.export_step(cq.Workplane().box(1, 2, 3), tmp_path / "bracket.step")
    assert _read_back(plain) == (["bracket"], [])
    named = geometry.export_step(cq.Workplane().box(1, 2, 3), tmp_path / "b2.step", name="it's a \\ part")
    product = next(r for r in _records(named) if "= PRODUCT(" in r)
    assert "PRODUCT('it''s a \\\\ part','it''s a \\\\ part'," in product   # quote and backslash doubled in the file
    assert _read_back(named) == (["it's a \\ part"], [])                 # and read back as given


def test_a_multi_solid_shape_numbers_its_products_and_links_within_the_file(tmp_path, cq):
    for i in range(2):                                    # earlier multi-solid exports in this process
        cq.exporters.export(_two_boxes(cq), str(tmp_path / f"warm{i}.step"))
    out = geometry.export_step(_two_boxes(cq), tmp_path / "pair.step")
    assert _read_back(out) == (["pair", "pair.1", "pair.2"], ["1", "2"])


def test_the_geometry_is_what_cadquery_writes(tmp_path, cq):
    """Only the header, the product names and the assembly-link ids differ from cadquery.exporters.export."""
    def normalised(path):
        rows = []
        for r in _records(path):
            r = re.sub(r"= PRODUCT\('[^']*','[^']*',", "= PRODUCT(N,N,", r)
            rows.append(re.sub(r"= NEXT_ASSEMBLY_USAGE_OCCURRENCE\('\d+',", "= NEXT_ASSEMBLY_USAGE_OCCURRENCE(I,", r))
        return rows

    for label, shape in (("box", cq.Workplane().box(2, 3, 4)),
                         ("pair", cq.Workplane().add([cq.Solid.makeBox(1, 1, 1),
                                                      cq.Solid.makeBox(1, 1, 1).translate(cq.Vector(3, 0, 0))]))):
        ours = geometry.export_step(shape, tmp_path / f"{label}.step")
        theirs = tmp_path / f"{label}.cq.step"
        cq.exporters.export(shape, str(theirs))
        assert normalised(ours) == normalised(theirs), label
        back = cq.importers.importStep(str(ours)).val()
        assert back.Volume() == pytest.approx(cq.Compound.makeCompound(shape.vals()).Volume(), rel=1e-9)


def test_an_assembly_or_a_name_that_is_not_ascii_is_refused(tmp_path, cq):
    with pytest.raises(TypeError, match="Assembly"):
        geometry.export_step(cq.Assembly(cq.Workplane().box(1, 1, 1), name="asm"), tmp_path / "asm.step")
    with pytest.raises(ValueError, match="printable ASCII"):
        geometry.export_step(cq.Workplane().box(1, 1, 1), tmp_path / "part.step", name="Gehäuse")
    with pytest.raises(ValueError, match="printable ASCII"):
        geometry.export_step(cq.Workplane().box(1, 1, 1), tmp_path / "Gehäuse.step")
    with pytest.raises(ValueError, match="no shapes"):
        geometry.export_step(cq.Workplane(), tmp_path / "empty.step")
    assert not list(tmp_path.iterdir())
