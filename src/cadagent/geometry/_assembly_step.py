"""``export_step`` for a cadquery ``Assembly``: the same STEP bytes every time the same assembly is exported (#150).

``Assembly.save`` (``cadquery.occ_impl.exporters.assembly.exportAssembly``) writes four things that change with no
model change:

* the write time in the header's ``FILE_NAME``;
* assembly-link (``NEXT_ASSEMBLY_USAGE_OCCURRENCE``) ids, counted across the process;
* the name of every node added without one: cadquery names it with a random uuid (``uuid.uuid1``);
* the order of the colour records. OCCT's XCAF writer (``STEPCAFControl_Writer``) adds one presentation graph per
  coloured product (a ``MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION`` and its styles) by walking a map
  hashed on shape addresses, so with two or more coloured products their records come in heap order, which changes
  from process to process.

This writes the same document (``cadquery.occ_impl.assembly.toCAF``, colours on) with the same writer and settings
as ``exportAssembly`` in its default mode, and fixes those four in OCCT's document and model before the file is
written: the header as for parts; the link ids 1, 2, ... in file order; each unnamed node named ``<parent>.<k>``
(its place among its parent's children); and the colour records put in one order that depends only on the model:
the presentation graphs sorted by the geometry they style, each laid out depth-first in field order, which is how
OCCT lays out one graph. Adapted, with credit: the canonical style order, its list of style record types and their
field-order references come from text-to-cad's cadgen ``step_export`` (https://github.com/earthtojake/text-to-cad,
packages/cadgen/src/cadgen/step_export.py, MIT, Copyright (c) 2026 Thompson Labs LLC; vendored, with its licence, under
``vendor/text-to-cad``). Here the order is applied to OCCT's model before the write (``ChangeOrder``), not to the
written text, and an order this cannot settle is an error rather than a file left as OCCT wrote it.

Limits: a style record type this does not know (OCCT changed its writer), or a tail the graphs do not cover, stops
the export with ``GeometryError`` instead of writing a file that is not reproducible. Sub-shape names, colours and
layers (``Assembly.addSubshape``) are refused: cadquery adds them in the order of a set of shapes hashed on their
addresses. So are written names that cadquery's reader (``Assembly.importStep``) would refuse or misread: a child
with its parent's name or a sibling's (an unnamed root is written with the file's name). Another OCCT or cadquery
version can write different bytes for the same assembly.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# cadquery's name for a node added without one: str(uuid.uuid1()).
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# The writer settings exportAssembly sets on top of those of a part (cadagent.geometry.STEP_SETTINGS).
ASSEMBLY_SETTINGS = (("write.stepcaf.subshapes.name", 1),)

_MDGPR = "StepVisual_MechanicalDesignGeometricPresentationRepresentation"
_STYLED = ("StepVisual_StyledItem", "StepVisual_OverRidingStyledItem")
# Every record type OCCT's colour writer adds for a styled product (STEPCAFControl_Writer, MakeSTEPStyles), as
# text-to-cad lists them. The colour tail of the model must be made of these only.
_STYLE_FAMILY = frozenset({
    _MDGPR, *_STYLED,
    "StepVisual_PresentationStyleAssignment", "StepVisual_PresentationStyleByContext",
    "StepVisual_SurfaceStyleUsage", "StepVisual_SurfaceSideStyle", "StepVisual_SurfaceStyleFillArea",
    "StepVisual_SurfaceStyleRendering", "StepVisual_SurfaceStyleRenderingWithProperties",
    "StepVisual_SurfaceStyleTransparent", "StepVisual_FillAreaStyle", "StepVisual_FillAreaStyleColour",
    "StepVisual_ColourRgb", "StepVisual_Colour", "StepVisual_PreDefinedColour",
    "StepVisual_DraughtingPreDefinedColour", "StepVisual_CurveStyle", "StepVisual_DraughtingPreDefinedCurveFont",
})


def node_names(assy: Any, root: str) -> Dict[int, Tuple[str, str]]:
    """``{id(node): (cadquery's name, the name written)}`` for every node of ``assy``: the root is ``root``, an
    unnamed node (a uuid) ``<its parent's written name>.<k>`` with ``k`` its place among the parent's children
    (from 1), and any other node keeps its own name."""
    out: Dict[int, Tuple[str, str]] = {id(assy): (assy.name, root)}

    def walk(node: Any, written: str) -> None:
        for k, child in enumerate(node.children, 1):
            mine = f"{written}.{k}" if _UUID.match(child.name) else child.name
            out[id(child)] = (child.name, mine)
            walk(child, mine)

    walk(assy, root)
    return out


def _check(assy: Any, names: Dict[int, Tuple[str, str]], step_string: Any) -> None:
    """Refuse what the file could not carry the same way every time, or what cadquery's reader would misread:
    sub-shape styling, a name OCCT's reader would misread, and written names that clash."""
    def nodes(node: Any):
        yield node
        for child in node.children:
            yield from nodes(child)

    for node in nodes(assy):
        if any(getattr(node, f"_subshape_{kind}", None) for kind in ("colors", "names", "layers")):
            raise ValueError(f"assembly node {node.name!r} has sub-shape names, colours or layers "
                             "(Assembly.addSubshape); cadquery writes those in an order that changes from run to run, "
                             "so export_step does not take them yet (#150)")
    for _old, new in names.values():
        step_string(new, "STEP product name", "name the assembly node (or pass export_step another name=)")
    _check_clashes(assy, names)


def _check_clashes(assy: Any, names: Dict[int, Tuple[str, str]]) -> None:
    """Refuse written names that cadquery's reader (``Assembly.importStep``) would refuse or misread. It rebuilds the
    tree with ``Assembly.add``, which wants each child's name new to its parent: not the parent's own name (nor its
    ``<name>_part``, the label of a node that holds a shape and children) and not a sibling's. Deeper nodes are keyed
    by path (``leg0/bolt``), so a name may come back at another level. A child with the root's name would also make
    the reader take that child for the top of the tree."""
    def told(node: Any) -> str:
        old, new = names[id(node)]
        return f"{new!r}" if old == new else f"{new!r} (a node added without a name)"

    def walk(node: Any) -> None:
        mine = names[id(node)][1]
        taken = {mine: "its parent's name"}
        if node.obj is not None and node.children:
            taken[f"{mine}_part"] = "the label of its parent's own shape"
        for child in node.children:
            theirs = names[id(child)][1]
            if theirs in taken:
                if node is assy and theirs == mine:
                    raise ValueError(f"the assembly would be written as {mine!r}, the name of one of its children; "
                                     "cadquery's reader would read the file as that child alone. Pass export_step "
                                     "another name= (or rename the child)")
                raise ValueError(f"a child of the assembly node {mine!r} would be written as {told(child)}, "
                                 f"{taken[theirs]}; cadquery's reader would refuse or lose it. Name the node, or "
                                 "rename the one it clashes with (an unnamed node is written as <parent>.<k>)")
            taken[theirs] = "a sibling's name"
            walk(child)

    walk(assy)


def _renamed(assy: Any, names: Dict[int, Tuple[str, str]]) -> Any:
    """A copy of ``assy`` whose nodes carry the written names. toCAF names each node's labels from the node itself, so
    each copy of a sub-assembly added twice gets the names of its own place."""
    def copy(node: Any) -> Any:
        out = node.__class__(node.obj, node.loc, names[id(node)][1], node.color, node.material, node.metadata)
        for child in node.children:          # as Assembly._copy does, without Assembly.add's copy of each subtree
            mine = copy(child)
            mine.parent = out
            out.children.append(mine)
            out.objects[mine.name] = mine
            out.objects.update(mine.objects)
        return out

    return copy(assy)


def _entities(model: Any, kind: Any) -> List[Any]:
    found, it = [], model.Entities()
    it.SelectType(kind.get_type_descriptor_s(), True)
    it.Start()
    while it.More():
        found.append(it.Value())
        it.Next()
    return found


def _style_children(ent: Any) -> List[Any]:
    """The entities a colour record refers to, in field order: the order OCCT adds them to the model in."""
    kind = ent.DynamicType().Name()
    out: List[Any] = []

    def add(value: Any) -> None:
        if value is not None:
            out.append(value)

    def add_array(array: Any) -> None:
        if array is None:
            return
        for i in range(1, array.Length() + 1):
            value = array.Value(i)
            add(value.Value() if callable(getattr(value, "Value", None)) else value)   # a SELECT holds its entity

    if kind == _MDGPR:
        add_array(ent.Items())
    elif kind in _STYLED:
        add(ent.Item())
        add_array(ent.Styles())
        if kind == "StepVisual_OverRidingStyledItem":
            add(ent.OverRiddenStyle())
    elif kind in ("StepVisual_PresentationStyleAssignment", "StepVisual_PresentationStyleByContext"):
        add_array(ent.Styles())
        if kind == "StepVisual_PresentationStyleByContext":
            context = ent.StyleContext()
            add(context.Value() if callable(getattr(context, "Value", None)) else context)
    elif kind == "StepVisual_SurfaceStyleUsage":
        add(ent.Style())
    elif kind == "StepVisual_SurfaceSideStyle":
        add_array(ent.Styles())
    elif kind == "StepVisual_SurfaceStyleFillArea":
        add(ent.FillArea())
    elif kind == "StepVisual_FillAreaStyle":
        add_array(ent.FillStyles())
    elif kind == "StepVisual_FillAreaStyleColour":
        add(ent.FillColour())
    elif kind in ("StepVisual_SurfaceStyleRendering", "StepVisual_SurfaceStyleRenderingWithProperties"):
        add(ent.SurfaceColour())
        if kind == "StepVisual_SurfaceStyleRenderingWithProperties":
            add_array(ent.Properties())
    return out                                    # colours, transparency and curve fonts refer to nothing


def order_style_tail(model: Any, where: str) -> bool:
    """Put the colour records at the end of ``model`` in their canonical order (see the module notes); True when
    there was more than one presentation graph to order. Raises ``GeometryError`` when the tail is not what OCCT's
    colour writer makes."""
    from cadagent.geometry import GeometryError

    from OCP.StepVisual import StepVisual_MechanicalDesignGeometricPresentationRepresentation as Graph

    if len(_entities(model, Graph)) < 2:                 # one graph or none: nothing to order, skip the scan
        return False
    total = model.NbEntities()
    entities = [None] + [model.Entity(i) for i in range(1, total + 1)]
    graphs = [i for i in range(1, total + 1) if entities[i].DynamicType().Name() == _MDGPR]
    start = graphs[0]
    strangers = sorted({entities[i].DynamicType().Name() for i in range(start, total + 1)} - _STYLE_FAMILY)
    if strangers:
        raise GeometryError(f"{where}: the colour records end in records export_step does not know how to order "
                            f"({', '.join(strangers)}); the file would not be reproducible")
    # Entity(i) gives the same Python object for the same entity while `entities` holds it, so id() numbers them.
    number = {id(e): i for i, e in enumerate(entities) if e is not None}
    children = {i: [number.get(id(c)) for c in _style_children(entities[i])] for i in range(start, total + 1)}
    if any(n is None for refs in children.values() for n in refs):
        raise GeometryError(f"{where}: a colour record refers to an entity outside the model")

    def key(graph: int) -> Tuple[List[int], int]:
        """What a graph styles (geometry before the tail, numbered in transfer order) and its context."""
        styled = sorted(children[i][0] for i in children[graph] if entities[i].DynamicType().Name() in _STYLED)
        return styled, number[id(entities[graph].ContextOfItems())]

    order: List[int] = []
    seen = set()

    def visit(i: int) -> None:
        if i < start or i in seen:
            return
        seen.add(i)
        order.append(i)
        for child in children[i]:
            visit(child)

    keys = {graph: key(graph) for graph in graphs}
    if len(set(map(repr, keys.values()))) != len(graphs):
        raise GeometryError(f"{where}: two presentation graphs style the same geometry in the same context; their "
                            "order would not be reproducible")
    for graph in sorted(graphs, key=keys.__getitem__):
        visit(graph)
    if len(order) != total - start + 1:
        raise GeometryError(f"{where}: {total - start + 1 - len(order)} colour record(s) belong to no presentation "
                            "graph; the file would not be reproducible")
    # Move the records into that order: each out-of-place run of records that stay together (a whole graph, as a
    # rule) moves back to where it belongs in one ChangeOrder, which renumbers the model in C++. Entities before
    # the tail keep their numbers.
    current = list(range(start, total + 1))            # the old number of the record at each tail position
    for k, want in enumerate(order):
        if current[k] == want:
            continue
        j = current.index(want, k)
        run = 1
        # OCCT refuses a move whose source and target overlap (run > j - k); a shorter one leaves the rest for later.
        while run < j - k and k + run < len(order) and j + run < len(current) and current[j + run] == order[k + run]:
            run += 1
        model.ChangeOrder(start + j, start + k, run)   # moves records j..j+run-1 back to k, shifting the rest on
        current = current[:k] + current[j:j + run] + current[k:j] + current[j + run:]
    if model.NbEntities() != total or any(model.Entity(start + k) is not entities[old] for k, old in enumerate(order)):
        raise GeometryError(f"{where}: reordering the colour records did not give the order planned")
    return True


def write_assembly(assy: Any, path: Path, name: Optional[str], step_string: Any, swap_settings: Any,
                   part_settings: Any) -> None:
    """``export_step``'s work for an Assembly (see the module notes). ``step_string``, ``swap_settings`` and
    ``part_settings`` are ``cadagent.geometry``'s, passed in to keep one copy of each."""
    from cadquery.occ_impl.assembly import toCAF
    from OCP.APIHeaderSection import APIHeaderSection_MakeHeader
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_StepModelType
    from OCP.StepBasic import StepBasic_Product
    from OCP.StepRepr import StepRepr_NextAssemblyUsageOccurrence
    from OCP.TCollection import TCollection_HAsciiString
    from OCP.XSControl import XSControl_WorkSession

    from cadagent.geometry import GeometryError, step_timestamp

    if not assy.children and assy.obj is None:
        raise ValueError(f"{path.name}: the assembly is empty")
    root = name if name is not None else (path.stem if _UUID.match(assy.name) else assy.name)
    names = node_names(assy, root)
    _check(assy, names, step_string)
    _top, doc = toCAF(_renamed(assy, names), True)      # colours as STEP styles, as exportAssembly does

    writer = STEPCAFControl_Writer(XSControl_WorkSession(), False)    # registers the settings swapped in below
    writer.SetColorMode(True)
    writer.SetLayerMode(True)
    writer.SetNameMode(True)
    previous = swap_settings(tuple(part_settings) + ASSEMBLY_SETTINGS)
    try:
        if not writer.Transfer(doc, STEPControl_StepModelType.STEPControl_AsIs):
            raise GeometryError(f"{path.name}: OCCT could not transfer the assembly to STEP")
        model = writer.Writer().Model()
        header = APIHeaderSection_MakeHeader(model)
        if not header.IsDone():
            raise GeometryError(f"{path.name}: OCCT made no STEP header")
        header.SetName(TCollection_HAsciiString(path.name))
        header.SetTimeStamp(TCollection_HAsciiString(step_timestamp()))
        unnamed = [p.Name().ToCString() for p in _entities(model, StepBasic_Product)
                   if p.Name().ToCString().startswith("Open CASCADE STEP translator")]
        if unnamed:                                     # OCCT numbers those per process
            raise GeometryError(f"{path.name}: {len(unnamed)} product(s) have no name ({unnamed[0]!r})")
        for number, link in enumerate(_entities(model, StepRepr_NextAssemblyUsageOccurrence), 1):
            link.SetId(TCollection_HAsciiString(str(number)))
        order_style_tail(model, path.name)

        part = path.with_name(f".{path.name}.{os.getpid()}.part")
        try:
            if writer.Write(str(part)) != IFSelect_ReturnStatus.IFSelect_RetDone or not part.is_file():
                raise GeometryError(f"OCCT could not write {path}")
            os.replace(part, path)
        finally:
            part.unlink(missing_ok=True)
    finally:
        swap_settings(previous)                         # the process keeps the project's own settings
