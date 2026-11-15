"""The SCADA recapture step's file list, ownership and manifest logic, without a browser."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("scada_recapture", ROOT / "tools/webkit/scada/recapture.py")
recapture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recapture)
UI, SIM = recapture.UI, recapture.SIM
CHECKS = [check for check, _, _ in recapture.PAIRS]


class PureLogicTests(unittest.TestCase):
    def test_porcelain_parsing_and_split(self):
        data = (f' M {SIM}metadata/thumbnails.json\0?? {SIM}img/thumbnails/a/new/preview.jpg\0'
                f' D {SIM}img/thumbnails/a/old/preview.jpg\0').encode()
        entries = recapture.parse_porcelain(data)
        self.assertEqual([code for code, _ in entries], [' M', '??', ' D'])
        written, deleted = recapture.split_changes(entries)
        self.assertEqual(written, [f'{SIM}img/thumbnails/a/new/preview.jpg', f'{SIM}metadata/thumbnails.json'])
        self.assertEqual(deleted, [f'{SIM}img/thumbnails/a/old/preview.jpg'])
        self.assertEqual(recapture.parse_porcelain(b''), [])
        with self.assertRaises(ValueError):
            recapture.parse_porcelain(b'garbage\0')

    def test_only_failed_checks_regenerate_in_order(self):
        results = dict.fromkeys(CHECKS, 0)
        self.assertEqual(recapture.generators_for(results), [])
        results.update({'thumbnails:scenarios:check': 1, 'gallery:check': 1})
        self.assertEqual(recapture.generators_for(results), ['gallery:generate', 'thumbnails:scenarios'])

    def test_ownership_is_per_generator_and_frozen_baseline_always_refused(self):
        scenario = ['thumbnails:scenarios']
        owned = [f'{SIM}metadata/thumbnails.json', f'{SIM}img/thumbnails/energy/grid/preview.jpg',
                 f'{SIM}img/README.md', f'{SIM}docs/scenario-gallery.md']
        self.assertEqual(recapture.unowned(owned, scenario), [])
        # Another generator's outputs are not this run's to offer.
        self.assertEqual(recapture.unowned([f'{UI}metadata/thumbnails.json'], scenario), [f'{UI}metadata/thumbnails.json'])
        self.assertEqual(recapture.unowned([f'{UI}metadata/thumbnails.json'], ['thumbnails']), [])
        for path in ('tests/fixtures/scada/default-baseline.json', f'{SIM}src/index.mjs',
                     f'{SIM}img/thumbnails/../../src/index.mjs', f'/{SIM}img/thumbnails/x.jpg'):
            self.assertEqual(recapture.unowned([path], [g for _, g, _ in recapture.PAIRS]), [path], path)
        docs = ['docs:scenarios']
        self.assertEqual(recapture.unowned([f'{SIM}scenarios/README.md', f'{SIM}scenarios/water-plant/README.md'], docs), [])
        self.assertEqual(recapture.unowned([f'{SIM}scenarios/water-plant/system.json'], docs), [f'{SIM}scenarios/water-plant/system.json'])
        self.assertEqual(recapture.unowned([f'{SIM}scenarios/a/b/README.md'], docs), [f'{SIM}scenarios/a/b/README.md'])

    def test_pinned_playwright_matches_the_requirements_file(self):
        self.assertRegex(recapture.pinned_playwright(ROOT / recapture.REQUIREMENTS), r'^\d+\.\d+\.\d+$')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'requirements.txt'
            path.write_text('Pillow==1.0\n')
            with self.assertRaises(ValueError):
                recapture.pinned_playwright(path)

    def test_stage_copies_regular_files_with_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, out = Path(directory) / 'repo', Path(directory) / 'out'
            (repo / 'a/b').mkdir(parents=True)
            (repo / 'a/b/c.txt').write_bytes(b'hello')
            records = recapture.stage(repo, ['a/b/c.txt'], out)
            self.assertEqual((out / 'a/b/c.txt').read_bytes(), b'hello')
            self.assertEqual(records, [{'path': 'a/b/c.txt', 'bytes': 5,
                                        'sha256': '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'}])
            (repo / 'link').symlink_to(repo / 'a/b/c.txt')
            with self.assertRaises(ValueError):
                recapture.stage(repo, ['link'], out)


class MainTests(unittest.TestCase):
    """Drive main() against a scratch git repository with fake npm scripts."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name) / 'repo'
        self.out = Path(self.directory.name) / 'out'
        manifest = self.repo / SIM / 'metadata/thumbnails.json'
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"stale": true}\n')
        (self.repo / 'tests/fixtures/scada').mkdir(parents=True)
        (self.repo / 'tests/fixtures/scada/default-baseline.json').write_text('{}\n')
        for command in (['init', '-q'], ['add', '-A'],
                        ['-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'base']):
            subprocess.run(['git', '-C', str(self.repo), *command], check=True)
        self.state = {'fresh': False}
        for name, value in (('REPO', self.repo), ('shell_record', lambda: {'python_playwright': 'x'})):
            patcher = mock.patch.object(recapture, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fake_run(self, writes):
        def run(script, commands):
            if script == 'thumbnails:scenarios':
                for relative, data in writes.items():
                    path = self.repo / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(data)
                self.state['fresh'] = True
                code = 0
            else:
                code = 1 if script == 'thumbnails:scenarios:check' and not self.state['fresh'] else 0
            commands.append({'command': recapture.npm(script), 'exit': code})
            return code
        return run

    def main(self, writes):
        with mock.patch.object(recapture, 'run', self.fake_run(writes)), \
                mock.patch.dict('os.environ', {'PR_HEAD_SHA': 'abc123'}):
            return recapture.main(['--out', str(self.out)])

    def test_stages_exactly_the_changed_outputs_with_a_manifest(self):
        image = f'{SIM}img/thumbnails/energy/grid/preview.jpg'
        self.assertEqual(self.main({f'{SIM}metadata/thumbnails.json': '{"fresh": true}\n', image: 'jpeg'}), 0)
        staged = sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob('*') if p.is_file())
        self.assertEqual(staged, sorted([recapture.MANIFEST, image, f'{SIM}metadata/thumbnails.json']))
        manifest = json.loads((self.out / recapture.MANIFEST).read_text())
        head = subprocess.run(['git', '-C', str(self.repo), 'rev-parse', 'HEAD'], check=True,
                              capture_output=True, text=True).stdout.strip()
        self.assertEqual((manifest['source_commit'], manifest['pull_request_head']), (head, 'abc123'))
        self.assertEqual([f['path'] for f in manifest['files']], sorted([image, f'{SIM}metadata/thumbnails.json']))
        self.assertEqual(manifest['deleted'], [])
        commands = [c['command'].rsplit(' ', 1)[1] for c in manifest['commands']]
        self.assertEqual(commands, CHECKS + ['thumbnails:scenarios'] + CHECKS)

    def test_refuses_to_stage_a_frozen_baseline_change(self):
        writes = {f'{SIM}metadata/thumbnails.json': '{}\n', 'tests/fixtures/scada/default-baseline.json': '{"x": 1}\n'}
        with self.assertRaisesRegex(SystemExit, 'outside its generators'):
            self.main(writes)
        self.assertFalse(self.out.exists())

    def test_refuses_a_dirty_tree_and_a_failure_that_is_not_stale_provenance(self):
        (self.repo / 'stray.txt').write_text('x')
        with self.assertRaisesRegex(SystemExit, 'not clean'):
            self.main({})
        (self.repo / 'stray.txt').unlink()
        self.state['fresh'] = True
        with self.assertRaisesRegex(SystemExit, 'Nothing to recapture'):
            self.main({})


if __name__ == '__main__':
    unittest.main()
