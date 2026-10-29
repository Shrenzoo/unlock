"""Real AP214 -> XDE -> AP242 round-trip smoke on a generated fixture."""

import hashlib
import json
from pathlib import Path
import tempfile

from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document

from unlock_engine.assembly import import_step
from unlock_engine.contracts import POLICY
from unlock_engine.geometry import difference_volume

root = Path(__file__).resolve().parents[1]
source = root / "evidence/fixtures/B01/assembly.step"
original = import_step(source)
reader = STEPCAFControl_Reader()
assert reader.ReadFile(str(source)) == IFSelect_RetDone
doc = TDocStd_Document(TCollection_ExtendedString("BinXCAF"))
assert reader.Transfer(doc)
Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
Interface_Static.SetCVal_s("write.step.unit", "MM")
writer = STEPCAFControl_Writer()
assert writer.Transfer(doc, STEPControl_AsIs)
with tempfile.TemporaryDirectory(prefix="unlock-ap242-") as tmp:
    path = Path(tmp) / "assembly.step"
    assert writer.Write(str(path)) == IFSelect_RetDone
    data = path.read_bytes()
    assert b"AP242_MANAGED_MODEL_BASED_3D_ENGINEERING" in data
    (root / "evidence/ap242_assembly.step").write_bytes(data)
    imported = import_step(path)
    assert len(original.occurrences) == len(imported.occurrences) == 5
    differences = []
    for old, new in zip(original.occurrences, imported.occurrences):
        assert old.source_occurrence_path == new.source_occurrence_path
        assert (
            max(abs(a - b) for a, b in zip(old.placement.matrix, new.placement.matrix))
            <= POLICY.algebraic_tolerance
        )
        difference = difference_volume(old.shape, new.shape)
        assert difference <= POLICY.volume_noise_mm3
        differences.append(difference)
    report = dict(
        status="passed",
        format="AP242",
        occurrences=5,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        exported_sha256=hashlib.sha256(data).hexdigest(),
        symmetric_differences_mm3=differences,
    )
    (root / "evidence/ap242_smoke.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
