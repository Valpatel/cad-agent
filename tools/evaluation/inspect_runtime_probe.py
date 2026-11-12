#!/usr/bin/env python3
"""Reviewed phase-1 metadata probe: no installs, resolution, images or models.

Download a hash-bound uv binary and three pinned source files into a fresh
private directory; execute only version/help and offline frozen exports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
from urllib.request import HTTPSHandler, ProxyHandler, build_opener

INSPECT_REVISION = 'ff0acb3de3cb2fec0b1b35d0f46d40e234289dc8'
HELPER_HASHES = {
    'runner.py': 'c20a2799749e3bb56951fb31555c0f29f3052b12b6cbbfc9ac769389669af5bc',
    'standard_eval.py': '289dc3b4dd30ed403432ae84f0be01da91ea7713f361a04fb5f033766a13bfa8',
}
for name, expected in HELPER_HASHES.items():
    if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != expected:
        raise ValueError('phase-1 process helper differs from reviewed bytes')
import runner

UV_VERSION = '0.13.4'
UV_URL = 'https://github.com/astral-sh/uv/releases/download/0.13.4/uv-x86_64-unknown-linux-gnu.tar.gz'
UV_HASH = '2b428396f12572d4429cf210ca234dd599a33b3af0958a4d5ed569d63e3f344f'
CHECKSUM_HASH = '4504013b0a07f04078a3423e741b904206c2b4ea04bffaf3cba1b2334a007c93'
SOURCE = 'https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/' + INSPECT_REVISION + '/'
SOURCE_HASHES = {
    'pyproject.toml': 'c05c87727d3908ed9c56ead746012af41440f99435ebac98cad105f566f433ac',
    'uv.lock': '51e5c7e02907eddb299da012cc1a141ef9054f544300a19ee1f862d169da497c',
    'CONTRIBUTING.md': '772f6f756d7dfad60a54355987ebdb229709feb4700503a98983098beb130b9f',
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def download(url, path, expected, limit):
    # Public immutable artifacts only. Ignore ambient proxy/credential helpers.
    opener = build_opener(ProxyHandler({}), HTTPSHandler())
    size = 0
    with opener.open(url, timeout=20) as response, Path(path).open('xb') as out:
        os.chmod(path, 0o600)
        while True:
            data = response.read(min(65536, limit-size+1))
            if not data:
                break
            size += len(data)
            if size > limit:
                raise ValueError('download exceeds its artifact bound')
            out.write(data)
    if digest(path) != expected:
        raise ValueError('download hash differs from reviewed artifact')


def extract_uv(archive, destination):
    prefix = 'uv-x86_64-unknown-linux-gnu'
    found, total = {}, 0
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            if member.isdir() and member.name.rstrip('/') == prefix:
                continue
            if member.name not in (prefix + '/uv', prefix + '/uvx') or not member.isfile():
                raise ValueError('unexpected uv archive member/type')
            name = Path(member.name).name
            if name in found or not 0 < member.size <= 80_000_000:
                raise ValueError('duplicate or oversized uv archive member')
            total += member.size
            if total > 128_000_000:
                raise ValueError('uv extraction exceeds byte bound')
            data = tar.extractfile(member).read(member.size + 1)
            if len(data) != member.size:
                raise ValueError('truncated uv archive member')
            found[name] = data
    if set(found) != {'uv', 'uvx'}:
        raise ValueError('expected exactly uv and uvx binaries')
    destination.mkdir(mode=0o700)
    for name, data in found.items():
        with (destination / name).open('xb') as out:
            out.write(data)
        (destination / name).chmod(0o500)


def probe(work):
    work = Path(work).absolute()
    if '..' in work.parts or any(p.is_symlink() for p in (work, *work.parents)):
        raise ValueError('work path must not contain symlinks/traversal')
    work.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(work.iterdir()):
        raise ValueError('work must be fresh and empty')
    work.chmod(0o700)
    source = work / 'source'
    source.mkdir(mode=0o700)
    checksum = work / 'uv.sha256'
    download(UV_URL + '.sha256', checksum, CHECKSUM_HASH, 1024)
    if checksum.read_text() != UV_HASH + '  uv-x86_64-unknown-linux-gnu.tar.gz\n':
        raise ValueError('official release checksum content differs')
    archive = work / 'uv.tar.gz'
    download(UV_URL, archive, UV_HASH, 20_000_000)
    extract_uv(archive, work / 'tool')
    for name, expected in SOURCE_HASHES.items():
        download(SOURCE + name, source / name, expected, 2_000_000)
        (source / name).chmod(0o400)
    uv = str(work / 'tool/uv')
    commands = [
        [uv, '--version'],
        [uv, 'export', '--help'],
        [uv, 'tree', '--help'],
        [uv, '--no-config', 'export', '--offline', '--frozen', '--no-default-groups',
         '--no-emit-project', '--no-header', '--no-annotate', '--python', '/usr/bin/python3.12',
         '--output-file', str(work / 'base.requirements.txt')],
        [uv, '--no-config', 'export', '--offline', '--frozen', '--no-default-groups', '--extra', 'dev',
         '--no-emit-project', '--no-header', '--no-annotate', '--python', '/usr/bin/python3.12',
         '--output-file', str(work / 'dev-extra.requirements.txt')],
    ]
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'UV_OFFLINE': '1',
           'UV_PYTHON_DOWNLOADS': 'never', 'UV_CACHE_DIR': str(work / 'cache'),
           'PYTHONDONTWRITEBYTECODE': '1'}
    receipts = []
    for index, argv in enumerate(commands):
        stdout, stderr = work / f'{index}.stdout', work / f'{index}.stderr'
        # Metadata-only commands cannot invoke dependency builds: no project
        # source was fetched, no sync/install command or model is available.
        with stdout.open('xb') as out, stderr.open('xb') as err:
            os.chmod(stdout, 0o600)
            os.chmod(stderr, 0o600)
            with subprocess.Popen(argv, env=env, cwd=source, stdout=out, stderr=err,
                                  start_new_session=True) as child:
                try:
                    code = child.wait(timeout=15)
                finally:
                    runner.settle_group(child)
                    child.wait(timeout=5)
        receipts.append(dict(argv=argv, exit_code=code, stdout_sha256=digest(stdout), stderr_sha256=digest(stderr)))
        runner.write_json(work / f'{index}.receipt.json', receipts[-1])
        if code != 0:
            raise ValueError(f'metadata command {index} failed; retain its receipt, do not retry setup')
        if index == 0 and not stdout.read_text().startswith('uv 0.13.4 '):
            raise ValueError('verified artifact reports an unexpected version')
        if any(digest(source / name) != expected for name, expected in SOURCE_HASHES.items()):
            raise ValueError('pinned source/lock changed during metadata export')
    artifacts = {name: dict(sha256=digest(work / name), bytes=(work / name).stat().st_size)
                 for name in ('base.requirements.txt', 'dev-extra.requirements.txt')}
    result = dict(phase=1, upstream_revision=INSPECT_REVISION, uv_sha256=UV_HASH, exports=artifacts,
                  environment_installed=False, image_operations=False, dependency_resolution=False,
                  note='Exports retain upstream markers/hashes; no minimal environment has been selected or qualified.')
    runner.write_json(work / 'probe.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(probe(args.work)))
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(json.dumps(dict(phase=1, passed=False, error=str(exc))))
        raise SystemExit(1)
