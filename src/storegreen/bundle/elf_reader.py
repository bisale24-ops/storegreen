# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Aleksandr Khrukalo
"""
bundle/elf_reader.py — reads ELF PT_LOAD segment alignments.

Pure Python, no NDK, no readelf.  Standard library only.  Python 3.9 compat.

Spec requirements (§2 of rules-catalog.md):
- For each base/lib/<abi>/*.so: confirm \\x7fELF magic; read e_phoff /
  e_phentsize / e_phnum; walk PT_LOAD headers; report p_align for each.
- Only 64-bit ABIs (arm64-v8a, x86_64) are in scope for the 16 KB rule.
- A library passes when EVERY PT_LOAD alignment is ≥ 0x4000.
- An EMPTY result (no PT_LOAD segments found) MUST NOT be read as aligned —
  it is the undecidable case.
- The reader must NEVER raise on:
    - a file shorter than 64 bytes
    - wrong magic (not \\x7fELF)
    - an EI_CLASS byte that is neither 1 (32-bit) nor 2 (64-bit)
    - an EI_DATA byte that is neither 1 (LE) nor 2 (BE)
    - a program-header table that runs past the end of the file
  All of those return an ElfResult with readable=False and a reason string.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ELF_MAGIC = b"\x7fELF"
PT_LOAD = 1

# ELF header byte offsets (same for 32 and 64 bit)
EI_CLASS   = 4   # 1=32-bit, 2=64-bit
EI_DATA    = 5   # 1=LE, 2=BE

# 64-bit ELF header layout (LE)
#   e_phoff     @ 0x20, uint64, 8 bytes
#   e_phentsize @ 0x36, uint16, 2 bytes
#   e_phnum     @ 0x38, uint16, 2 bytes
_HDR64_PHOFF      = (0x20, "<Q")   # e_phoff
_HDR64_PHENTSIZE  = (0x36, "<H")   # e_phentsize
_HDR64_PHNUM      = (0x38, "<H")   # e_phnum

# 32-bit ELF header layout (LE)
#   e_phoff     @ 0x1c, uint32
#   e_phentsize @ 0x2a, uint16
#   e_phnum     @ 0x2c, uint16
_HDR32_PHOFF      = (0x1c, "<I")
_HDR32_PHENTSIZE  = (0x2a, "<H")
_HDR32_PHNUM      = (0x2c, "<H")

# PT_LOAD p_type location within a program header
# 64-bit: p_type @ 0x00 (uint32), p_align @ 0x30 (uint64)
# 32-bit: p_type @ 0x00 (uint32), p_align @ 0x1c (uint32)
_PHDR64_PTYPE  = (0x00, "<I")
_PHDR64_PALIGN = (0x30, "<Q")
_PHDR32_PTYPE  = (0x00, "<I")
_PHDR32_PALIGN = (0x1c, "<I")

_MIN_ELF_SIZE = 64


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class ElfResult:
    """Result of reading ELF PT_LOAD alignments from one .so entry."""
    entry_path: str         # AAB-entry path, e.g. base/lib/arm64-v8a/libfoo.so
    readable: bool          # False if the file could not be parsed at all
    reason: Optional[str]   # set when readable=False; "cannot be determined — …"
    bits: Optional[int]     # 32 or 64
    alignments: List[int] = field(default_factory=list)  # p_align for each PT_LOAD

    @property
    def is_aligned_16kb(self) -> bool:
        """True iff every PT_LOAD is ≥ 16 KB aligned AND at least one exists.

        An empty alignments list is NOT aligned (spec: empty result must never
        be read as aligned).
        """
        return bool(self.alignments) and all(a >= 0x4000 for a in self.alignments)

    @property
    def min_alignment(self) -> Optional[int]:
        return min(self.alignments) if self.alignments else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _unpack_at(data: bytes, offset: int, fmt: str) -> Optional[int]:
    """Unpack a single integer from *data* at *offset* using *fmt*.

    Returns None (never raises) if there are not enough bytes.
    """
    size = struct.calcsize(fmt)
    if offset + size > len(data):
        return None
    try:
        (value,) = struct.unpack_from(fmt, data, offset)
        return value
    except struct.error:
        return None


def _endian_prefix(ei_data: int) -> Optional[str]:
    if ei_data == 1:
        return "<"   # little-endian
    if ei_data == 2:
        return ">"   # big-endian
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_alignments(data: bytes, entry_path: str) -> ElfResult:
    """Parse *data* as an ELF file and return PT_LOAD alignments.

    Never raises.  On any parse error, returns an ElfResult with
    readable=False and a descriptive reason string.
    """

    def bad(reason: str) -> ElfResult:
        return ElfResult(entry_path=entry_path, readable=False, reason=reason, bits=None)

    # Guard 1: minimum size
    if len(data) < _MIN_ELF_SIZE:
        return bad(
            f"cannot be determined — unreadable ELF: file too short "
            f"({len(data)} bytes, need ≥ {_MIN_ELF_SIZE})"
        )

    # Guard 2: magic
    if data[:4] != ELF_MAGIC:
        return bad(
            f"cannot be determined — unreadable ELF: wrong magic "
            f"({data[:4]!r}, expected {ELF_MAGIC!r})"
        )

    ei_class = data[EI_CLASS]
    ei_data  = data[EI_DATA]

    # Guard 3: class
    if ei_class not in (1, 2):
        return bad(
            f"cannot be determined — unreadable ELF: unknown EI_CLASS={ei_class:#x}"
        )

    # Guard 4: endianness
    pfx = _endian_prefix(ei_data)
    if pfx is None:
        return bad(
            f"cannot be determined — unreadable ELF: unknown EI_DATA={ei_data:#x}"
        )

    bits = 64 if ei_class == 2 else 32

    # Select layout
    if bits == 64:
        phoff_spec     = (0x20, pfx + "Q")
        phentsize_spec = (0x36, pfx + "H")
        phnum_spec     = (0x38, pfx + "H")
        ptype_off      = 0x00
        palign_off     = 0x30
        ptype_fmt      = pfx + "I"
        palign_fmt     = pfx + "Q"
    else:
        phoff_spec     = (0x1c, pfx + "I")
        phentsize_spec = (0x2a, pfx + "H")
        phnum_spec     = (0x2c, pfx + "H")
        ptype_off      = 0x00
        palign_off     = 0x1c
        ptype_fmt      = pfx + "I"
        palign_fmt     = pfx + "I"

    phoff     = _unpack_at(data, phoff_spec[0], phoff_spec[1])
    phentsize = _unpack_at(data, phentsize_spec[0], phentsize_spec[1])
    phnum     = _unpack_at(data, phnum_spec[0], phnum_spec[1])

    if phoff is None or phentsize is None or phnum is None:
        return bad("cannot be determined — unreadable ELF: ELF header truncated")

    if phentsize == 0 or phnum == 0:
        # No program headers — not an error, just nothing to check
        return ElfResult(entry_path=entry_path, readable=True, reason=None, bits=bits, alignments=[])

    # Guard 5: program-header table runs past end of file
    table_end = phoff + phentsize * phnum
    if table_end > len(data):
        return bad(
            f"cannot be determined — unreadable ELF: program-header table "
            f"[{phoff:#x}..{table_end:#x}) extends past file end ({len(data):#x})"
        )

    alignments: List[int] = []
    for i in range(phnum):
        hdr_start = phoff + i * phentsize
        p_type = _unpack_at(data, hdr_start + ptype_off, ptype_fmt)
        if p_type is None:
            return bad(
                f"cannot be determined — unreadable ELF: program header {i} truncated"
            )
        if p_type != PT_LOAD:
            continue
        p_align = _unpack_at(data, hdr_start + palign_off, palign_fmt)
        if p_align is None:
            return bad(
                f"cannot be determined — unreadable ELF: p_align of PT_LOAD[{i}] truncated"
            )
        alignments.append(p_align)

    return ElfResult(
        entry_path=entry_path,
        readable=True,
        reason=None,
        bits=bits,
        alignments=alignments,
    )
