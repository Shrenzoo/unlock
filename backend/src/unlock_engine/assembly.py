"""XDE occurrence traversal and hierarchy-preserving STEP assembly export."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import cadquery as cq
from OCP.BRep import BRep_Builder
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TColStd import TColStd_SequenceOfAsciiString
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from .contracts import EngineError, POLICY, Transform, digest
from .geometry import bounds, fingerprint, inverse, matrix, transform, validate_solid
from .package import check_step


@dataclass(frozen=True)
class Occurrence:
    id: str
    source_occurrence_path: str
    definition_id: str
    display_name: str
    placement: Transform
    local_shape: cq.Shape
    shape: cq.Shape
    geometry_hash: str

    def inventory(self):
        return dict(
            id=self.id,
            source_occurrence_path=self.source_occurrence_path,
            definition_id=self.definition_id,
            display_name=self.display_name,
            placement=self.placement.matrix,
            geometry_hash=self.geometry_hash,
            **validate_solid(self.shape),
        )


@dataclass(frozen=True)
class AssemblyNode:
    path: str
    name: str
    placement: Transform


@dataclass(frozen=True)
class Assembly:
    source_hash: str
    source_step: bytes
    occurrences: tuple[Occurrence, ...]
    nodes: tuple[AssemblyNode, ...]

    @property
    def geometry_hash(self):
        return digest(
            [
                (o.source_occurrence_path, o.geometry_hash, o.placement.matrix)
                for o in self.occurrences
            ]
        )


def entry(label):
    s = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, s)
    return s.ToCString()


def name(label):
    attr = TDataStd_Name()
    return (
        attr.Get().ToExtString()
        if label.FindAttribute(TDataStd_Name.GetID_s(), attr)
        else entry(label)
    )


def import_step(path: str | Path, *, enforce_limits=True) -> Assembly:
    path = Path(path)
    if path.stat().st_size > POLICY.max_expanded_bytes:
        raise EngineError("LIMIT_EXCEEDED", "STEP exceeds expanded byte budget")
    data = path.read_bytes()
    check_step(data)
    source = hashlib.sha256(data).hexdigest()
    try:
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        if reader.ReadFile(str(path)) != IFSelect_RetDone:
            raise ValueError("STEP parser rejected file")
        # ExternFiles() returns an unregistered map type in OCP 7.8.1.1.
        # Package preflight rejects reference-bearing entities before native parsing.
        units = TColStd_SequenceOfAsciiString()
        angles = TColStd_SequenceOfAsciiString()
        solid = TColStd_SequenceOfAsciiString()
        reader.Reader().FileUnits(units, angles, solid)
        unit_names = [
            units.Value(i).ToCString().lower() for i in range(1, units.Length() + 1)
        ]
        if not unit_names or any(
            u not in ("millimetre", "millimeter", "mm") for u in unit_names
        ):
            raise ValueError(
                f"v1 requires explicit uniform millimetre STEP units, got {unit_names}"
            )
        reader.ChangeReader().SetSystemLengthUnit(1.0)
        doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
        if not reader.Transfer(doc):
            raise ValueError("XDE transfer failed")
        st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        roots = TDF_LabelSequence()
        st.GetFreeShapes(roots)
        leaves = []
        nodes = []

        def walk(label, parent, path, active, depth=0):
            if depth > 32:
                raise ValueError("XDE hierarchy depth limit exceeded")
            definition = TDF_Label()
            if st.IsReference_s(label):
                if not st.GetReferredShape_s(label, definition):
                    raise ValueError("unresolved XDE reference")
                placement = parent.Multiplied(st.GetLocation_s(label))
            else:
                definition = label
                placement = parent
            key = entry(definition)
            if key in active:
                raise ValueError("cyclic XDE assembly")
            if st.IsAssembly_s(definition):
                placement = placement.Multiplied(st.GetLocation_s(definition))
                nodes.append(AssemblyNode(path, name(label), matrix(placement)))
                children = TDF_LabelSequence()
                st.GetComponents_s(definition, children, False)
                for i in range(1, children.Length() + 1):
                    walk(
                        children.Value(i),
                        placement,
                        f"{path}/{i - 1}",
                        active | {key},
                        depth + 1,
                    )
            else:
                raw = st.GetShape_s(definition)
                if raw.IsNull():
                    raise ValueError(f"null leaf {path}")
                placement = placement.Multiplied(raw.Location())
                local = cq.Shape.cast(raw.Located(TopLoc_Location()))
                world = cq.Shape.cast(local.wrapped.Moved(placement))
                validate_solid(world)
                leaves.append(
                    Occurrence(
                        "occ_" + digest([source, path])[:20],
                        path,
                        "def_" + digest([source, key])[:20],
                        name(label),
                        matrix(placement),
                        local,
                        world,
                        fingerprint(world),
                    )
                )
                if len(leaves) > 12 and enforce_limits:
                    raise ValueError("more than 12 leaf occurrences")

        for i in range(1, roots.Length() + 1):
            walk(roots.Value(i), TopLoc_Location(), f"/{i - 1}", set())
        if enforce_limits and not 5 <= len(leaves) <= 12:
            raise ValueError(
                "supported assembly requires 5–12 separate rigid leaf occurrences"
            )
        if not leaves:
            raise ValueError("empty assembly")
        if sum(len(o.shape.Faces()) for o in leaves) > POLICY.max_faces:
            raise ValueError("assembly face limit exceeded")
        mins = [min(bounds(o.shape).min[k] for o in leaves) for k in range(3)]
        maxs = [max(bounds(o.shape).max[k] for o in leaves) for k in range(3)]
        if any(b - a > POLICY.max_envelope_mm for a, b in zip(mins, maxs)):
            raise ValueError("assembly exceeds 500 mm envelope")
        return Assembly(source, data, tuple(leaves), tuple(nodes))
    except EngineError:
        raise
    except Exception as exc:
        raise EngineError("INVALID_PACKAGE", f"STEP/XDE: {exc}") from exc


def export_assembly(
    assembly: Assembly,
    path: str | Path,
    replacements: dict[str, cq.Shape] | None = None,
):
    """Rebuild the occurrence tree. Replacement keys are source paths; shapes are world BReps."""
    replacements = replacements or {}
    known = {o.source_occurrence_path for o in assembly.occurrences}
    if not replacements.keys() <= known:
        raise EngineError("NOT_FOUND", "unknown replacement occurrence")
    doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    st.SetAutoNaming_s(False)
    definitions = {}

    def location(t):
        from OCP.gp import gp_Trsf

        tr = gp_Trsf()
        tr.SetValues(*t.matrix[:12])
        return TopLoc_Location(tr)

    def relative(parent, world):
        return location(parent).Inverted().Multiplied(location(world))

    nodes = {n.path: n for n in assembly.nodes}
    leaves = {o.source_occurrence_path: o for o in assembly.occurrences}

    def build(path):
        if path in nodes:
            node = nodes[path]
            raw = TopoDS_Compound()
            BRep_Builder().MakeCompound(raw)
            label = st.AddShape(raw, False)
            TDataStd_Name.Set_s(label, TCollection_ExtendedString(node.name))
            children = sorted(
                [p for p in (*nodes, *leaves) if p.rsplit("/", 1)[0] == path],
                key=lambda p: int(p.rsplit("/", 1)[1]),
            )
            for child in children:
                definition, placement, display = build(child)
                inst = st.AddComponent(
                    label, definition, relative(node.placement, placement)
                )
                TDataStd_Name.Set_s(inst, TCollection_ExtendedString(display))
            return label, node.placement, node.name
        o = leaves[path]
        shape = replacements.get(path, o.shape)
        validate_solid(shape)
        local = transform(shape.copy(), inverse(o.placement))
        h = fingerprint(local)
        if h not in definitions:
            definitions[h] = st.AddShape(local.wrapped, False)
            TDataStd_Name.Set_s(
                definitions[h], TCollection_ExtendedString(o.display_name)
            )
        return definitions[h], o.placement, o.display_name

    roots = sorted(
        [p for p in nodes if not p.rsplit("/", 1)[0]], key=lambda p: int(p[1:])
    )
    if any(not p.rsplit("/", 1)[0] for p in leaves):
        raise EngineError(
            "UNSUPPORTED_SEMANTICS",
            "free leaf roots export unsupported; require assembly roots",
        )
    for root in roots:
        if nodes[root].placement != Transform():
            raise EngineError(
                "UNSUPPORTED_SEMANTICS",
                "nonidentity root assembly placement export unsupported",
            )
        build(root)
    st.UpdateAssemblies()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True)
    if not writer.Transfer(doc, STEPControl_AsIs):
        raise EngineError("GEOMETRY_FAILED", "XDE STEP export transfer failed")
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise EngineError("GEOMETRY_FAILED", "XDE STEP write failed")
