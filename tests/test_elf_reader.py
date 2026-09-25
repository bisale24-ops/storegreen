# SPDX-License-Identifier: MIT
"""
tests/test_elf_reader.py — unit tests for bundle/elf_reader.py

Covers:
- 64-bit LE aligned (all PT_LOAD ≥ 0x4000)         → passes
- 64-bit LE misaligned (p_align 0x1000)             → fails
- Truncated file (< 64 bytes)                       → readable=False
- Wrong magic                                       → readable=False
- 32-bit ELF (not in scope but must not crash)      → readable=True, bits=32
- Program-header table runs past EOF               → readable=False
- No PT_LOAD segments                              → readable=True, empty alignments, NOT aligned
- Empty bytes                                      → readable=False
"""

import struct
import pytest

from storegreen.bundle.elf_reader import read_alignments, ElfResult, PT_LOAD


# ---------------------------------------------------------------------------
# ELF builder helpers
# ---------------------------------------------------------------------------

def _elf64_header(
    e_phoff: int,
    e_phentsize: int,
    e_phnum: int,
    ei_data: int = 1,   # 1=LE
) -> bytes:
    """Build a minimal 64-bit ELF header (64 bytes)."""
    header = bytearray(64)
    # EI_MAG0-3
    header[0:4] = b"\x7fELF"
    # EI_CLASS = 2 (64-bit)
    header[4] = 2
    # EI_DATA
    header[5] = ei_data
    # EI_VERSION = 1
    header[6] = 1
    # e_type = ET_DYN (3) @ 0x10
    struct.pack_into("<H", header, 0x10, 3)
    # e_machine = AArch64 (0xB7) @ 0x12
    struct.pack_into("<H", header, 0x12, 0xB7)
    # e_phoff @ 0x20 (uint64)
    struct.pack_into("<Q", header, 0x20, e_phoff)
    # e_phentsize @ 0x36 (uint16)
    struct.pack_into("<H", header, 0x36, e_phentsize)
    # e_phnum @ 0x38 (uint16)
    struct.pack_into("<H", header, 0x38, e_phnum)
    return bytes(header)


def _elf32_header(e_phoff: int, e_phentsize: int, e_phnum: int) -> bytes:
    """Build a minimal 32-bit ELF header (52 bytes, padded to 64)."""
    header = bytearray(64)
    header[0:4] = b"\x7fELF"
    header[4] = 1   # 32-bit
    header[5] = 1   # LE
    header[6] = 1
    struct.pack_into("<H", header, 0x10, 3)
    # e_phoff @ 0x1c (uint32)
    struct.pack_into("<I", header, 0x1c, e_phoff)
    # e_phentsize @ 0x2a (uint16)
    struct.pack_into("<H", header, 0x2a, e_phentsize)
    # e_phnum @ 0x2c (uint16)
    struct.pack_into("<H", header, 0x2c, e_phnum)
    return bytes(header)


def _phdr64(p_type: int, p_align: int) -> bytes:
    """Build a 64-bit program header entry (56 bytes)."""
    phdr = bytearray(56)
    struct.pack_into("<I", phdr, 0x00, p_type)   # p_type
    struct.pack_into("<Q", phdr, 0x30, p_align)  # p_align @ 0x30
    return bytes(phdr)


def _phdr32(p_type: int, p_align: int) -> bytes:
    """Build a 32-bit program header entry (32 bytes)."""
    phdr = bytearray(32)
    struct.pack_into("<I", phdr, 0x00, p_type)   # p_type
    struct.pack_into("<I", phdr, 0x1c, p_align)  # p_align @ 0x1c
    return bytes(phdr)


def _make_elf64(*alignments: int) -> bytes:
    """Build a complete 64-bit ELF with PT_LOAD entries having the given alignments."""
    phentsize = 56
    phnum = len(alignments)
    e_phoff = 64  # immediately after header
    header = _elf64_header(e_phoff, phentsize, phnum)
    phdrs = b"".join(_phdr64(PT_LOAD, a) for a in alignments)
    return header + phdrs


def _make_elf64_no_ptload() -> bytes:
    """Build a 64-bit ELF with a program header that is NOT PT_LOAD."""
    phentsize = 56
    phnum = 1
    e_phoff = 64
    header = _elf64_header(e_phoff, phentsize, phnum)
    phdr = _phdr64(2, 0x1000)  # p_type=PT_DYNAMIC (2), not PT_LOAD
    return header + phdr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestElfReader:

    # ---- Valid 64-bit files ----

    def test_aligned_16kb(self):
        data = _make_elf64(0x4000, 0x4000)
        result = read_alignments(data, "base/lib/arm64-v8a/libfoo.so")
        assert result.readable is True
        assert result.bits == 64
        assert result.alignments == [0x4000, 0x4000]
        assert result.is_aligned_16kb is True

    def test_misaligned_like_libsqlcipher(self):
        """Replicates the Numsly p_align=0x1000 finding from the spec."""
        data = _make_elf64(0x1000, 0x1000, 0x1000)
        result = read_alignments(data, "base/lib/arm64-v8a/libsqlcipher.so")
        assert result.readable is True
        assert result.is_aligned_16kb is False
        assert result.min_alignment == 0x1000
        assert result.alignments == [0x1000, 0x1000, 0x1000]

    def test_mixed_alignment_fails(self):
        data = _make_elf64(0x4000, 0x1000)
        result = read_alignments(data, "base/lib/arm64-v8a/libmixed.so")
        assert result.is_aligned_16kb is False

    def test_no_pt_load_not_aligned(self):
        """Empty alignments must NOT be read as aligned (spec requirement)."""
        data = _make_elf64_no_ptload()
        result = read_alignments(data, "base/lib/arm64-v8a/libnoptload.so")
        assert result.readable is True
        assert result.alignments == []
        assert result.is_aligned_16kb is False  # empty is NOT aligned

    def test_no_program_headers_at_all(self):
        """phnum=0 means no headers to walk."""
        header = _elf64_header(e_phoff=64, e_phentsize=56, e_phnum=0)
        result = read_alignments(header, "base/lib/arm64-v8a/libempty.so")
        assert result.readable is True
        assert result.alignments == []
        assert result.is_aligned_16kb is False  # no PT_LOAD is NOT aligned

    # ---- Error cases ----

    def test_truncated_file(self):
        result = read_alignments(b"\x7fELF\x02\x01\x01", "libtrunc.so")
        assert result.readable is False
        assert "unreadable ELF" in result.reason
        assert result.alignments == []

    def test_empty_bytes(self):
        result = read_alignments(b"", "libempty.so")
        assert result.readable is False
        assert "unreadable ELF" in result.reason

    def test_wrong_magic(self):
        data = bytearray(64)
        data[0:4] = b"CAFE"
        result = read_alignments(bytes(data), "notanelf.so")
        assert result.readable is False
        assert "magic" in result.reason.lower() or "unreadable ELF" in result.reason

    def test_bad_ei_class(self):
        data = bytearray(64)
        data[0:4] = b"\x7fELF"
        data[4] = 0x99  # neither 1 nor 2
        data[5] = 1
        result = read_alignments(bytes(data), "libbadclass.so")
        assert result.readable is False
        assert "unreadable ELF" in result.reason

    def test_bad_ei_data(self):
        data = bytearray(64)
        data[0:4] = b"\x7fELF"
        data[4] = 2      # 64-bit
        data[5] = 0x99   # neither 1 (LE) nor 2 (BE)
        result = read_alignments(bytes(data), "libbadendian.so")
        assert result.readable is False
        assert "unreadable ELF" in result.reason

    def test_phdr_table_past_eof(self):
        """Program-header table runs past end of file → readable=False."""
        # phoff=64, phentsize=56, phnum=10 → needs 64+560=624 bytes, but only 128
        header = _elf64_header(e_phoff=64, e_phentsize=56, e_phnum=10)
        short_data = header  # only 64 bytes, table would need 624
        result = read_alignments(short_data, "libshort.so")
        assert result.readable is False
        assert "unreadable ELF" in result.reason

    # ---- 32-bit ----

    def test_32bit_readable(self):
        """32-bit ELF should be readable (bits=32) even though not in scope for rule."""
        phentsize = 32
        phnum = 1
        e_phoff = 64
        header = _elf32_header(e_phoff, phentsize, phnum)
        phdr = _phdr32(PT_LOAD, 0x1000)
        data = header + phdr
        result = read_alignments(data, "base/lib/armeabi-v7a/libfoo.so")
        assert result.readable is True
        assert result.bits == 32
        assert result.alignments == [0x1000]
        # Not 16KB aligned, but readable
        assert result.is_aligned_16kb is False

    # ---- Big-endian ----

    def test_big_endian_elf(self):
        """Big-endian ELF header should be parsed without crashing."""
        header = bytearray(64)
        header[0:4] = b"\x7fELF"
        header[4] = 2   # 64-bit
        header[5] = 2   # big-endian
        header[6] = 1
        # e_phnum @ 0x38 (big-endian)
        struct.pack_into(">H", header, 0x38, 0)  # phnum=0 → safe
        struct.pack_into(">H", header, 0x36, 56) # phentsize
        struct.pack_into(">Q", header, 0x20, 64) # phoff
        result = read_alignments(bytes(header), "libbe.so")
        # Should be readable (phnum=0 means no headers to walk)
        assert result.readable is True
        assert result.alignments == []

    # ---- min_alignment property ----

    def test_min_alignment_none_when_empty(self):
        result = read_alignments(b"", "libempty.so")
        assert result.min_alignment is None

    def test_min_alignment_correct(self):
        data = _make_elf64(0x4000, 0x1000, 0x8000)
        result = read_alignments(data, "libfoo.so")
        assert result.min_alignment == 0x1000
