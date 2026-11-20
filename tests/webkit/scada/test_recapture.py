"""The SCADA recapture step's file list, ownership and manifest logic, without a browser."""
import importlib.util
import json
import re
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
                     f'{SIM}img/thumbnails/../../src/index.mjs', f'/{SIM}img/thumbnails/x.jpg',
                     f'{SIM}img/thumbnails/a\\..\\b.jpg'):
            self.assertEqual(recapture.unowned([path], [g for _, g, _ in recapture.PAIRS]), [path], path)
        docs = ['docs:scenarios']
        self.assertEqual(recapture.unowned([f'{SIM}scenarios/README.md', f'{SIM}scenarios/water-plant/README.md'], docs), [])
        self.assertEqual(recapture.unowned([f'{SIM}scenarios/water-plant/system.json'], docs), [f'{SIM}scenarios/water-plant/system.json'])
        self.assertEqual(recapture.unowned([f'{SIM}scenarios/a/b/README.md'], docs), [f'{SIM}scenarios/a/b/README.md'])

    def test_frozen_path_stays_excluded_even_if_a_generator_claims_it(self):
        baseline = 'tests/fixtures/scada/default-baseline.json'
        pairs = [('check', 'generate', [re.escape(baseline)])]
        with mock.patch.object(recapture, 'PAIRS', pairs):
            self.assertEqual(recapture.unowned([baseline], ['generate']), [baseline])

    def test_no_owned_output_is_git_ignored(self):
        # --no-index checks the ignore rules even for paths already tracked by git.
        tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z', '--', UI, SIM],
                                          text=True).split('\0')
        samples = set()
        for _, _, patterns in recapture.PAIRS:
            for pattern in patterns:
                matches = [path for path in tracked if re.fullmatch(pattern, path)]
                self.assertTrue(matches, f'No tracked output matches {pattern}')
                samples.update(matches)
        ignored = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '--no-index', '-z', '--stdin'],
                                 input='\0'.join(sorted(samples)) + '\0', capture_output=True, text=True)
        self.assertEqual(ignored.returncode, 1, ignored.stdout or ignored.stderr)
        self.assertEqual(subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '--no-index', '-q', recapture.MANIFEST]).returncode, 0)

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

    def fake_run(self, writes, deletes=(), generator_exit=0, stays_stale=False):
        def run(script, commands):
            if script == 'thumbnails:scenarios':
                for relative, data in writes.items():
                    path = self.repo / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(data)
                for relative in deletes:
                    (self.repo / relative).unlink()
                self.state['fresh'] = not stays_stale
                code = generator_exit
            else:
                code = 1 if script == 'thumbnails:scenarios:check' and not self.state['fresh'] else 0
            commands.append({'command': recapture.npm(script), 'exit': code})
            return code
        return run

    def main(self, writes, **behaviour):
        with mock.patch.object(recapture, 'run', self.fake_run(writes, **behaviour)), \
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

    def test_refuses_a_failing_generator_and_checks_that_stay_stale(self):
        writes = {f'{SIM}metadata/thumbnails.json': '{}\n'}
        with self.assertRaisesRegex(SystemExit, 'thumbnails:scenarios failed'):
            self.main(writes, generator_exit=1)
        self.assertFalse(self.out.exists())
        subprocess.run(['git', '-C', str(self.repo), 'checkout', '-q', '--', '.'], check=True)
        self.state['fresh'] = False
        with self.assertRaisesRegex(SystemExit, 'still fail.*thumbnails:scenarios:check'):
            self.main(writes, stays_stale=True)
        self.assertFalse(self.out.exists())

    def test_refuses_a_non_empty_out(self):
        self.out.mkdir()
        (self.out / 'old.txt').write_text('x')
        with self.assertRaisesRegex(SystemExit, 'not empty'):
            self.main({})
        self.assertEqual([p.name for p in self.out.iterdir()], ['old.txt'])

    def test_deleted_owned_output_is_listed_and_deleted_baseline_refused(self):
        image = f'{SIM}img/thumbnails/energy/old/preview.jpg'
        (self.repo / image).parent.mkdir(parents=True)
        (self.repo / image).write_text('jpeg')
        subprocess.run(['git', '-C', str(self.repo), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=t', '-c', 'user.email=t@example.invalid',
                        'commit', '-qm', 'image'], check=True)
        self.out.mkdir()                                   # an empty --out is accepted and replaced
        self.assertEqual(self.main({f'{SIM}metadata/thumbnails.json': '{}\n'}, deletes=[image]), 0)
        manifest = json.loads((self.out / recapture.MANIFEST).read_text())
        self.assertEqual(manifest['deleted'], [image])
        self.assertFalse((self.out / image).exists())
        subprocess.run(['git', '-C', str(self.repo), 'checkout', '-q', '--', '.'], check=True)
        self.state['fresh'] = False
        other = Path(self.directory.name) / 'out2'
        with mock.patch.object(recapture, 'run', self.fake_run({f'{SIM}metadata/thumbnails.json': '{}\n'},
                                                               deletes=['tests/fixtures/scada/default-baseline.json'])):
            with self.assertRaisesRegex(SystemExit, 'outside its generators.*default-baseline'):
                recapture.main(['--out', str(other)])
        self.assertFalse(other.exists())

    def test_a_staging_failure_leaves_out_untouched(self):
        first = f'{SIM}img/thumbnails/a/preview.jpg'
        second = f'{SIM}img/thumbnails/b/preview.jpg'
        generate = self.fake_run({first: 'first image'})

        def run(script, commands):
            result = generate(script, commands)
            if script == 'thumbnails:scenarios':
                link = self.repo / second
                link.parent.mkdir(parents=True)
                link.symlink_to(self.repo / first)
            return result

        with mock.patch.object(recapture, 'run', run), \
                mock.patch.object(recapture.shutil, 'copyfile', wraps=recapture.shutil.copyfile) as copy:
            with self.assertRaisesRegex(ValueError, re.escape(f'Not a regular file: {second}')):
                recapture.main(['--out', str(self.out)])
        self.assertEqual([call.args[0] for call in copy.call_args_list], [self.repo / first])
        self.assertFalse(self.out.exists())
        self.assertEqual(list(self.out.parent.glob('.recapture-*')), [])

    def test_a_failed_rename_preserves_the_existing_empty_output_directory(self):
        self.out.mkdir()
        original = self.out.stat()
        with mock.patch.object(Path, 'rename', side_effect=OSError('rename failed')):
            with self.assertRaisesRegex(OSError, 'rename failed'):
                self.main({f'{SIM}metadata/thumbnails.json': '{}\n'})
        self.assertTrue(self.out.is_dir())
        self.assertEqual(self.out.stat().st_ino, original.st_ino)
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertEqual(list(self.out.parent.glob('.recapture-*')), [])

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
