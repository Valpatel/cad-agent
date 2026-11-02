# cad-agent installer for Windows (PowerShell 5.1 or 7): https://github.com/Valpatel/cad-agent (MIT)
#
#   irm https://cad-agent.valpatel.com/install.ps1 | iex
#
# Options as variables, set first: $env:CAD_AGENT_EXTRAS = "fea,sim"; $env:CAD_AGENT_REF = "v0.14.0";
# $env:CAD_AGENT_DIR (default ~\cad-agent); $env:CAD_AGENT_UNINSTALL = "1" removes the command and the skill links.
#
# Read it first if you like:
#   irm https://cad-agent.valpatel.com/install.ps1 -OutFile install.ps1; notepad install.ps1; .\install.ps1
#
# The same steps as install.sh:
#   1. needs git; installs uv (astral.sh, the version pinned below) into ~\.local\bin if it is missing, without
#      editing your PATH settings;
#   2. clones cad-agent into ~\cad-agent (main, the released channel), or updates it if it is already there;
#   3. `uv tool install --editable` of that checkout: the cad-agent command lands in ~\.local\bin, with its own
#      Python 3.12 that uv manages;
#   4. puts the agent skills into ~\.claude\skills and ~\.agents\skills (`cad-agent agents install`; copies where
#      Windows does not allow links) and says which ones this computer can't use yet.
# Running it again updates, with `cad-agent update`, which does the same steps. No administrator rights. cad-agent
# collects no telemetry, and this script turns usage reporting off for what it starts.
#
# Everything is inside Install-CadAgent, called on the last line, so a download cut short runs nothing.

function Install-CadAgent {
    $ErrorActionPreference = 'Stop'
    $UvVersion = '0.13.5'
    function Say([string]$Text) { Write-Host "cad-agent: $Text" }
    function Invoke-Native {
        $exe, $rest = $args
        & $exe @rest
        if ($LASTEXITCODE -ne 0) { throw "cad-agent: $exe $($rest -join ' ') failed (exit $LASTEXITCODE)" }
    }
    # A native command whose failure is an answer, not an error: its output is dropped. PowerShell 5.1 turns redirected
    # stderr into error records, which 'Stop' would throw, so it runs with 'Continue'.
    function Test-Native {
        $ErrorActionPreference = 'Continue'
        $exe, $rest = $args
        & $exe @rest *> $null
        return ($LASTEXITCODE -eq 0)
    }

    $repo = if ($env:CAD_AGENT_REPO) { $env:CAD_AGENT_REPO } else { 'https://github.com/Valpatel/cad-agent' }
    $dir = if ($env:CAD_AGENT_DIR) { $env:CAD_AGENT_DIR } else { Join-Path $HOME 'cad-agent' }
    $ref = "$env:CAD_AGENT_REF"
    $extras = "$env:CAD_AGENT_EXTRAS"
    if ($extras -notmatch '^[a-z0-9,-]*$') { throw 'cad-agent: CAD_AGENT_EXTRAS is a comma-separated list of names, e.g. fea,sim' }
    if ($ref -match '^-' -or $ref -notmatch '^[A-Za-z0-9._/-]*$') { throw 'cad-agent: CAD_AGENT_REF is a tag or branch name, e.g. v0.14.0' }

    # Usage reporting off for everything this script and cad-agent start, unless you set it yourself (cad-agent itself
    # sends nothing; the list is cadagent.cli.OPT_OUTS).
    $optOuts = @{ DO_NOT_TRACK = '1'; CADGEN_TELEMETRY = '0'; CADGEN_UPDATE_CHECK = '0'; KICAD_MCP_TELEMETRY_ENABLED = 'false' }
    foreach ($k in $optOuts.Keys) { if (-not [Environment]::GetEnvironmentVariable($k)) { Set-Item "env:$k" $optOuts[$k] } }

    $bin = Join-Path $HOME '.local\bin'
    $onPath = ($env:Path -split ';') -contains $bin
    $env:Path = "$bin;$env:Path"

    if ($env:CAD_AGENT_UNINSTALL) {
        if (Get-Command cad-agent -ErrorAction SilentlyContinue) { & cad-agent agents uninstall }
        if (Get-Command uv -ErrorAction SilentlyContinue) { & uv tool uninstall cad-agent }
        Say "removed the cad-agent command and its skills; the checkout stays in $dir (delete it if you want)"
        return
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        throw 'cad-agent: git is needed: install it (winget install --id Git.Git -e), open a new PowerShell, then run this again'
    }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Say "installing uv $UvVersion (astral.sh) into $bin"
        $env:UV_NO_MODIFY_PATH = '1'; $env:UV_INSTALL_DIR = $bin
        # uv's own installer, in a child PowerShell so nothing it does can end this one.
        $ps = (Get-Process -Id $PID).Path
        Invoke-Native $ps -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/$UvVersion/install.ps1 | iex"
        if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
            throw 'cad-agent: uv did not install: see https://docs.astral.sh/uv/getting-started/installation/'
        }
    }

    $spec = if ($extras) { "${dir}[cad,$extras]" } else { "${dir}[cad]" }
    $extraArgs = @(); if ($extras) { $extraArgs = @('--extras', $extras) }
    $refArgs = @(); if ($ref) { $refArgs = @('--ref', $ref) }
    $canUpdate = $false
    if ((Test-Path (Join-Path $dir '.git')) -and (Get-Command cad-agent -ErrorAction SilentlyContinue)) {
        $help = & { $ErrorActionPreference = 'Continue'; & cad-agent update --help 2>$null }
        $canUpdate = ($LASTEXITCODE -eq 0) -and [bool]($help -match '--dir')
    }
    if ($canUpdate) {
        Say "updating $dir"
        & cad-agent update --dir $dir @refArgs @extraArgs
        if ($LASTEXITCODE -eq 3) {
            # The reinstall is due, and cad-agent.exe cannot replace itself while it runs: finish here.
            $json = (& cad-agent update --dir $dir --reinstall-command @extraArgs) -join ''
            $cmd = @(ConvertFrom-Json $json | ForEach-Object { $_ })    # PowerShell 5.1 returns the array as one item
            Invoke-Native @cmd
            Invoke-Native cad-agent update --dir $dir --reinstalled
            & cad-agent agents install --source $dir
            if ($LASTEXITCODE -gt 1) { throw "cad-agent: cad-agent agents install failed (exit $LASTEXITCODE)" }
        } elseif ($LASTEXITCODE -ne 0) {
            throw "cad-agent: cad-agent update failed (exit $LASTEXITCODE)"
        }
    } else {
        if (Test-Path (Join-Path $dir '.git')) {
            Say "found ${dir}: bringing it up to date and installing the cad-agent command from it"
            if (& git -C $dir status --porcelain --untracked-files=no) {
                throw "cad-agent: $dir has changes to tracked files: commit or stash them; to change cad-agent itself, fork it"
            }
            if ($ref) {
                # A release tag is checked out detached (pinned); a branch is followed as a local branch (as update --ref).
                if (Test-Native git -C $dir fetch --quiet origin "+refs/tags/${ref}:refs/tags/${ref}") {
                    Invoke-Native git -C $dir checkout --quiet --detach "refs/tags/$ref"
                } else {
                    Invoke-Native git -C $dir fetch --quiet origin "+refs/heads/${ref}:refs/remotes/origin/${ref}"
                    if (Test-Native git -C $dir rev-parse --verify -q "refs/heads/$ref") {
                        Invoke-Native git -C $dir switch --quiet $ref
                        Invoke-Native git -C $dir merge --quiet --ff-only "origin/$ref"
                    } else {
                        Invoke-Native git -C $dir switch --quiet -c $ref "origin/$ref"
                    }
                }
            } elseif ((& git -C $dir symbolic-ref -q --short HEAD) -eq 'main') {
                Invoke-Native git -C $dir pull --quiet --ff-only origin main
            }
        } elseif (Test-Path $dir) {
            throw "cad-agent: $dir exists and is not a git checkout: move it away, or set CAD_AGENT_DIR"
        } else {
            Say "cloning $repo into $dir"
            $branch = if ($ref) { $ref } else { 'main' }
            Invoke-Native git clone --quiet --depth 1 --branch $branch $repo $dir
        }
        Say 'installing the cad-agent command (uv tool install --editable, Python 3.12)'
        Invoke-Native uv tool install --quiet --force --editable --python 3.12 $spec
        & cad-agent agents install
        if ($LASTEXITCODE -gt 1) { throw "cad-agent: cad-agent agents install failed (exit $LASTEXITCODE)" }
    }

    Say "done: cad-agent $(& git -C $dir describe --tags --always) in $dir"
    if (-not $onPath) { Say "$bin is not on your PATH yet: run ``uv tool update-shell`` and open a new terminal (or call $bin\cad-agent.exe)" }
    Say 'next: paste this into your AI agent, followed by what you want made:'
    Write-Host ''
    Write-Host '  Install cad-agent from https://cad-agent.valpatel.com/llms.txt, then use it for:'
    Write-Host ''
}

Install-CadAgent
