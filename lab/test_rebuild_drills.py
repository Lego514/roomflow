"""Rebuild stored measurements without invoking network or namespace operations."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rebuild_drill_dashboards', ROOT / 'scripts/rebuild-drill-dashboards.py')
rebuild_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rebuild_module)


class SavedDrillRebuild(unittest.TestCase):
    def test_rebuild_uses_saved_packets_preserves_raw_bytes_and_transition_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for scenario in ('delay', 'loss', 'dns'):
                source = ROOT / f'results/incident-drills/{scenario}-evidence.json'
                destination = output / source.name
                shutil.copyfile(source, destination)
                before = destination.read_bytes()
                old = json.loads((ROOT / f'results/incident-drills/{scenario}.json').read_text(encoding='utf-8'))
                with patch('subprocess.run', side_effect=AssertionError('must not run commands')):
                    result = rebuild_module.rebuild(output, scenario)
                payload = json.loads((output / f'{scenario}.json').read_text(encoding='utf-8'))
                self.assertEqual(before, destination.read_bytes())
                self.assertTrue(result['rawEvidenceUnchanged'])
                self.assertEqual(payload['notifications'], old['notifications'])
                self.assertEqual(payload['incidents'][0]['id'], old['incidents'][0]['id'])
                self.assertEqual(len(payload['timeline']), 7)
                self.assertEqual(len(payload.get('replay', {}).get('frames', [])), 7)

    def test_failed_saved_evidence_cannot_replace_successful_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            evidence = json.loads((ROOT / 'results/incident-drills/dns-evidence.json').read_text(encoding='utf-8'))
            evidence['error'] = 'Interrupted during collection'
            (output / 'dns-evidence.json').write_text(json.dumps(evidence), encoding='utf-8')
            with self.assertRaises(ValueError):
                rebuild_module.rebuild(output, 'dns')
            self.assertFalse((output / 'dns.json').exists())


if __name__ == '__main__':
    unittest.main()
