"""Bounded, in-memory package validation before the native STEP parser runs."""

import io
import json
import re
import stat
import zipfile
from dataclasses import dataclass

from .contracts import EngineError, POLICY


@dataclass(frozen=True)
class Package:
    step: bytes
    manifest: dict
    attribution: str | None = None


def check_step(data: bytes):
    if len(data) > POLICY.max_expanded_bytes:
        raise EngineError("LIMIT_EXCEEDED", "expanded STEP size exceeded")
    text = data.decode("ascii", errors="replace")
    if not text.lstrip().startswith("ISO-10303-21;") or "END-ISO-10303-21;" not in text:
        raise EngineError("INVALID_PACKAGE", "not a complete STEP physical file")
    if not re.search(
        r"FILE_SCHEMA\s*\(\s*\(\s*'(AUTOMOTIVE_DESIGN|AP242_MANAGED_MODEL_BASED_3D_ENGINEERING)",
        text,
        re.I,
    ):
        raise EngineError("INVALID_PACKAGE", "only AP214/AP242 schema supported")
    # Conservative preflight: reject external-document/reference mechanisms,
    # including Part 21 edition 3 reference/anchor sections, before OCCT.
    code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    if re.search(
        r"\b(EXTERNAL_SOURCE|EXTERNALLY_DEFINED|DOCUMENT_FILE|DOCUMENT_REPRESENTATION_TYPE|APPLIED_EXTERNAL_IDENTIFICATION_ASSIGNMENT|REFERENCE\s*;|ANCHOR\s*;)",
        code,
        re.I,
    ):
        raise EngineError("INVALID_PACKAGE", "external STEP references are unsupported")


def load_files(
    files: dict[str, bytes], *, compressed_size: int | None = None
) -> Package:
    names = {"assembly.step", "assembly.stp", "manifest.json", "attribution.txt"}
    if not set(files) <= names:
        raise EngineError(
            "INVALID_PACKAGE",
            "allowed flat filenames: assembly.step (or .stp), manifest.json, attribution.txt",
        )
    steps = set(files) & {"assembly.step", "assembly.stp"}
    if len(steps) != 1 or "manifest.json" not in files:
        raise EngineError(
            "INVALID_PACKAGE", "exactly one STEP and manifest.json required"
        )
    size = sum(map(len, files.values()))
    if (
        size > POLICY.max_expanded_bytes
        or (compressed_size if compressed_size is not None else size)
        > POLICY.max_compressed_bytes
    ):
        raise EngineError("LIMIT_EXCEEDED", "package byte budget exceeded")
    step = files[next(iter(steps))]
    check_step(step)

    def pairs(items):
        d = {}
        for k, v in items:
            if k in d:
                raise ValueError(f"duplicate JSON key {k}")
            d[k] = v
        return d

    try:
        manifest = json.loads(
            files["manifest.json"],
            object_pairs_hook=pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(
                ValueError(f"nonfinite {x}")
            ),
        )
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        attribution = (
            files["attribution.txt"].decode("utf8")
            if "attribution.txt" in files
            else None
        )
    except (ValueError, UnicodeError) as exc:
        raise EngineError("INVALID_MANIFEST", str(exc)) from exc
    return Package(step, manifest, attribution)


def load_zip(data: bytes) -> Package:
    if len(data) > POLICY.max_compressed_bytes:
        raise EngineError("LIMIT_EXCEEDED", "compressed package exceeds 25 MiB")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > 3 or len({i.filename for i in infos}) != len(infos):
                raise ValueError("duplicate or excess archive entries")
            total = 0
            files = {}
            for i in infos:
                if i.filename not in {
                    "assembly.step",
                    "assembly.stp",
                    "manifest.json",
                    "attribution.txt",
                }:
                    raise ValueError("unsafe or unsupported ZIP path")
                if i.flag_bits & 1:
                    raise ValueError("encrypted ZIP")
                mode = i.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)):
                    raise ValueError("nonregular ZIP member")
                if i.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ValueError("unsupported ZIP compression")
                total += i.file_size
                if total > POLICY.max_expanded_bytes:
                    raise EngineError(
                        "LIMIT_EXCEEDED", "expanded package exceeds 100 MiB"
                    )
                with z.open(i) as f:
                    content = f.read(min(i.file_size, POLICY.max_expanded_bytes) + 1)
                if len(content) != i.file_size:
                    raise ValueError("invalid expanded ZIP size")
                files[i.filename] = content
            return load_files(files, compressed_size=len(data))
    except EngineError:
        raise
    except (
        ValueError,
        OSError,
        zipfile.BadZipFile,
        RuntimeError,
        NotImplementedError,
    ) as exc:
        raise EngineError("INVALID_PACKAGE", str(exc)) from exc
