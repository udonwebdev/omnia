"""
tests/test_forensics_e2e_module49.py
End-to-end 10-step defensive analysis pipeline verification for OMNIA Module 49:
Autonomous Malware Analysis, Reverse Engineering & Behavioral Classification Intelligence.
Tests complete lifecycle on synthetic harmless fixtures.
"""

import os
import sys
import shutil
import tempfile
import struct
import unittest
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from malware import (
    malware_service,
    SampleVerdict,
    QuarantineStatus,
    FileType,
    BehaviorCategory
)
import sqlite3
from persistence.migrations import MIGRATION_V34


class TestMalwareE2EModule49(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "omnia_e2e.db")
        self.vault_dir = os.path.join(self.test_dir, "vault")
        os.makedirs(self.vault_dir, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(MIGRATION_V34)
        # Point service to test fixtures
        malware_service.repo.db_path = self.db_path
        malware_service.quarantine_manager.vault_dir = self.vault_dir

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_synthetic_trojan_fixture(self) -> bytes:
        """Creates a synthetic harmless PE binary with embedded static IOCs and API imports."""
        dos = bytearray(64)
        dos[0:2] = b"MZ"
        dos[0x3C:0x40] = struct.pack("<I", 0x40)

        pe_sig = b"PE\x00\x00"
        file_hdr = struct.pack("<HHIIIHH", 0x014C, 2, 0, 0, 0, 224, 0x0102)

        opt_hdr_std = struct.pack(
            "<HBBIIIIII",
            0x10B, 14, 0, 0x200, 0x200, 0, 0x1000, 0x1000, 0x2000
        )
        opt_hdr_win = struct.pack(
            "<IIIHHHHHHIIIIHHIIIIII",
            0x400000, 0x1000, 0x200, 6, 0, 0, 0, 6, 0, 0, 0x3000, 0x200, 0, 3, 0x8160,
            0x100000, 0x1000, 0x100000, 0x1000, 0, 16
        )
        data_dirs = bytearray(16 * 8)
        data_dirs[8:16] = struct.pack("<II", 0x2000, 40)

        opt_hdr = opt_hdr_std + opt_hdr_win + data_dirs

        sec1 = struct.pack("<8sIIIIIIHHI", b".text\x00\x00\x00", 0x200, 0x1000, 0x200, 0x400, 0, 0, 0, 0, 0x60000020)
        sec2 = struct.pack("<8sIIIIIIHHI", b".rdata\x00\x00", 0x200, 0x2000, 0x200, 0x600, 0, 0, 0, 0, 0x40000040)

        headers = dos + pe_sig + file_hdr + opt_hdr + sec1 + sec2
        headers += b"\x00" * (0x400 - len(headers))

        text_data = bytearray(0x200)
        text_data[0:4] = b"\x90\x90\x90\xc3"

        rdata = bytearray(0x200)
        rdata[0:20] = struct.pack("<IIIII", 0, 0, 0, 0x2030, 0x2040)
        rdata[0x30:0x3D] = b"KERNEL32.DLL\x00"
        rdata[0x40:0x44] = struct.pack("<I", 0x2060)
        rdata[0x60:0x70] = b"\x00\x00VirtualAlloc\x00"

        # Embed suspicious IOC strings
        iocs = (
            b"http://c2-botnet.defense-test.internal/beacon\x00"
            b"198.51.100.88\x00"
            b"HKLM\\Software\\Microsoft\\Windows\\CurrentVersion\\Run\x00"
            b"GetAsyncKeyState\x00"
            b"mimikatz\x00"
        )
        rdata[0x80:0x80 + len(iocs)] = iocs

        return bytes(headers + text_data + rdata)

    def test_full_10_step_defensive_pipeline(self):
        """
        Executes and validates the 10-step defensive analysis pipeline:
        Step 1: Sample Submission & Ingestion
        Step 2: Quarantine & Secure Vault Isolation (Fail-safe, no-exec)
        Step 3: Magic Bytes & Extension Spoofing Identification
        Step 4: Pure-Python PE Structural & Section Parsing
        Step 5: String Extraction & High-Entropy Shannon Calculation
        Step 6: Indicator of Compromise (IOC) Harvesting (IP, URL, Registry, API)
        Step 7: Behavioral ATT&CK Classification (Credential Access, Evasion)
        Step 8: Defensive YARA & Sigma Rule Generation with Syntax Validation
        Step 9: Epistemic Malware Intelligence Reporting with Verdict & Cryptographic Seal
        Step 10: Safe Sandbox Boundary Query (Zero Host Execution Guarantee)
        """
        # Step 1 & 2: Quarantine Ingestion
        payload = self._create_synthetic_trojan_fixture()
        file_path = os.path.join(self.test_dir, "disguised_invoice.pdf.exe")
        with open(file_path, "wb") as f:
            f.write(payload)

        sample, q_rec = malware_service.quarantine_sample(
            file_path=file_path,
            reason="Heuristic trigger from perimeter gateway",
            isolated_by="forensic_drill_agent",
            is_legal_hold=True
        )
        self.assertIsNotNone(sample.sample_id)
        self.assertTrue(sample.is_quarantined)
        self.assertTrue(q_rec.is_legal_hold)
        self.assertEqual(q_rec.status, QuarantineStatus.QUARANTINED)

        # Step 3: Magic Bytes & Extension Mismatch
        ident = malware_service.identify_file(payload, file_name="disguised_invoice.pdf")
        self.assertEqual(ident["file_type"], FileType.PE_EXE)
        self.assertTrue(ident["extension_mismatch"])

        # Step 4, 5, 6, 7: Static Analysis, Strings, IOCs & ATT&CK Behavior
        static_res, indicators, behaviors = malware_service.analyze_sample(sample.sample_id)
        self.assertIn("PE", static_res.format_detected)
        self.assertGreater(static_res.entropy, 0.0)
        self.assertIn("KERNEL32.DLL", static_res.imports)

        # Verify extracted IOCs
        ioc_types = {i.indicator_type for i in indicators}
        self.assertIn("URL", ioc_types)
        self.assertIn("IP", ioc_types)
        self.assertIn("REGISTRY", ioc_types)

        # Verify behavioral classification
        beh_categories = {b.category for b in behaviors}
        self.assertIn(BehaviorCategory.CREDENTIAL_ACCESS, beh_categories)

        # Step 8: Rule Generation (YARA + Sigma)
        yara_rule, sigma_rule = malware_service.generate_rules(sample.sample_id, "Trojan_TestFixture")
        self.assertEqual(yara_rule.validation_status, "VALIDATED")
        self.assertEqual(sigma_rule.validation_status, "VALIDATED")
        self.assertIn("uint16(0) == 0x5A4D", yara_rule.rule_content)
        self.assertIn("CommandLine|contains:", sigma_rule.rule_content)

        # Step 9: Epistemic Malware Intelligence Report
        report = malware_service.generate_intelligence_report(sample.sample_id, investigator="LeadSecOpsAnalyst")
        self.assertIn(report.verdict, (SampleVerdict.CONFIRMED_MALICIOUS, SampleVerdict.LIKELY_MALICIOUS))
        self.assertGreater(report.risk_score, 50.0)
        self.assertEqual(len(report.cryptographic_seal), 64)
        self.assertGreater(len(report.recommendations), 0)

        # Step 10: Safe Sandbox Boundary
        sandbox_res = malware_service.sandbox_adapter.query_dynamic_execution(sample.sample_id)
        self.assertEqual(sandbox_res["status"], "UNAVAILABLE")
        self.assertIn("Host execution strictly prevented for safety", sandbox_res["message"])


if __name__ == "__main__":
    unittest.main()
