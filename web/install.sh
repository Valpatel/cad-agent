#!/bin/sh
# cad-agent installer for macOS, Linux and WSL: https://github.com/Valpatel/cad-agent (MIT)
#
#   curl -fsSL https://cad-agent.valpatel.com/install.sh | sh
#   curl -fsSL https://cad-agent.valpatel.com/install.sh | sh -s -- --extras fea,sim --ref v0.14.0
#
# Read it first if you like:
#   curl -fsSLO https://cad-agent.valpatel.com/install.sh && less install.sh && sh install.sh
#
# What it does, and nothing else:
#   1. needs git; installs uv (astral.sh, the version pinned below) into ~/.local/bin if it is missing, without
#      editing your shell profile;
#   2. clones cad-agent into ~/cad-agent (main, the released channel), or updates it if it is already there;
#   3. `uv tool install --editable` of that checkout: the `cad-agent` command lands in ~/.local/bin, with its own
#      Python 3.12 that uv manages;
#   4. links the agent skills into ~/.claude/skills and ~/.agents/skills (`cad-agent agents install`) and says
#      which ones this computer can't use yet.
# Running it again updates, with `cad-agent update`, which does the same steps. No sudo. cad-agent collects no
# telemetry, and this script turns usage reporting off for what it starts. Nothing is written outside ~/cad-agent,
# uv's own folders (~/.local/bin, ~/.local/share/uv, ~/.cache/uv) and the agents' skill folders.
#
# Everything is inside main(), called on the last line, so a download cut short runs nothing.

set -eu

UV_VERSION="0.13.5"

say() { printf 'cad-agent: %s\n' "$*"; }
die() { printf 'cad-agent: %s\n' "$*" >&2; exit 1; }

usage() {
    say "install or update cad-agent: clone ~/cad-agent, install the command with uv, link the agent skills"
    say "  sh install.sh [--ref <tag or branch>] [--extras <a,b>] [--dir <path>] [--uninstall]"
    say "  --extras: fea (strength), sim (airflow, topology, renders), robot (URDF, MuJoCo), explore (search),"
    say "            site; cad is always included. The same as CAD_AGENT_REF, CAD_AGENT_EXTRAS, CAD_AGENT_DIR."
    say "  Run it again to update: the same steps as \`cad-agent update\`."
}

main() {
    repo="${CAD_AGENT_REPO:-https://github.com/Valpatel/cad-agent}"
    dir="${CAD_AGENT_DIR:-$HOME/cad-agent}"
    ref="${CAD_AGENT_REF:-}"
    extras="${CAD_AGENT_EXTRAS:-}"
    uninstall=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --ref) [ $# -ge 2 ] || die "--ref needs a tag or branch"; ref="$2"; shift 2 ;;
            --ref=*) ref="${1#--ref=}"; shift ;;
            --extras) [ $# -ge 2 ] || die "--extras needs a list, e.g. fea,sim"; extras="$2"; shift 2 ;;
            --extras=*) extras="${1#--extras=}"; shift ;;
            --dir) [ $# -ge 2 ] || die "--dir needs a path"; dir="$2"; shift 2 ;;
            --dir=*) dir="${1#--dir=}"; shift ;;
            --uninstall) uninstall=1; shift ;;
            -h|--help) usage; return 0 ;;
            *) die "unknown option $1 (see --help)" ;;
        esac
    done
    case "$extras" in *[!a-z0-9,-]*) die "--extras is a comma-separated list of names, e.g. fea,sim" ;; esac
    case "$ref" in -*|*[!A-Za-z0-9._/-]*) die "--ref is a tag or branch name, e.g. v0.14.0" ;; esac

    # Usage reporting off for everything this script and cad-agent start, unless you set it yourself (cad-agent itself
    # sends nothing; the list is cadagent.cli.OPT_OUTS).
    DO_NOT_TRACK="${DO_NOT_TRACK:-1}" CADGEN_TELEMETRY="${CADGEN_TELEMETRY:-0}"
    CADGEN_UPDATE_CHECK="${CADGEN_UPDATE_CHECK:-0}" KICAD_MCP_TELEMETRY_ENABLED="${KICAD_MCP_TELEMETRY_ENABLED:-false}"
    export DO_NOT_TRACK CADGEN_TELEMETRY CADGEN_UPDATE_CHECK KICAD_MCP_TELEMETRY_ENABLED

    bin="${XDG_BIN_HOME:-$HOME/.local/bin}"
    case ":$PATH:" in *":$bin:"*) on_path=1 ;; *) on_path="" ;; esac
    PATH="$bin:$PATH"
    export PATH

    if [ -n "$uninstall" ]; then
        if command -v cad-agent >/dev/null 2>&1; then cad-agent agents uninstall || true; fi
        if command -v uv >/dev/null 2>&1; then uv tool uninstall cad-agent || true; fi
        say "removed the cad-agent command and its skill links; the checkout stays in $dir (delete it if you want)"
        return 0
    fi

    command -v git >/dev/null 2>&1 ||
        die "git is needed: install it (macOS: xcode-select --install; Debian or Ubuntu: sudo apt install git), then run this again"

    if ! command -v uv >/dev/null 2>&1; then
        command -v curl >/dev/null 2>&1 || die "curl is needed to install uv"
        say "installing uv $UV_VERSION (astral.sh) into $bin"
        curl -fsSL "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR="$bin" sh
        command -v uv >/dev/null 2>&1 || die "uv did not install: see https://docs.astral.sh/uv/getting-started/installation/"
    fi

    if [ -d "$dir/.git" ] && command -v cad-agent >/dev/null 2>&1 && cad-agent update --help >/dev/null 2>&1; then
        say "updating $dir"
        set -- update
        [ -n "$ref" ] && set -- "$@" --ref "$ref"
        [ -n "$extras" ] && set -- "$@" --extras "$extras"
        cad-agent "$@"
    else
        if [ -d "$dir/.git" ]; then
            say "found $dir: bringing it up to date and installing the cad-agent command from it"
            if [ -n "$ref" ]; then
                git -C "$dir" fetch --quiet --depth 1 origin "$ref" || die "could not fetch $ref into $dir"
                git -C "$dir" checkout --quiet --detach FETCH_HEAD || die "could not move $dir to $ref"
            elif [ "$(git -C "$dir" symbolic-ref -q --short HEAD || true)" = main ]; then
                git -C "$dir" pull --quiet --ff-only origin main ||
                    die "$dir has its own changes on main: fork cad-agent to change it, or move $dir away and run this again"
            fi
        elif [ -e "$dir" ]; then
            die "$dir exists and is not a git checkout: move it away, or choose another folder with --dir"
        else
            say "cloning $repo into $dir"
            git clone --quiet --depth 1 --branch "${ref:-main}" "$repo" "$dir"
        fi
        say "installing the cad-agent command (uv tool install --editable, Python 3.12)"
        uv tool install --quiet --force --editable --python 3.12 "${dir}[cad${extras:+,$extras}]"
        cad-agent agents install || say "some skills were left alone (see above); the rest are installed"
    fi

    say "done: cad-agent $(git -C "$dir" describe --tags --always 2>/dev/null || true) in $dir"
    [ -n "$on_path" ] ||
        say "$bin is not on your PATH yet: run \`uv tool update-shell\` and open a new terminal (or call $bin/cad-agent)"
    say "next: paste this into your AI agent, followed by what you want made:"
    printf '\n  Install cad-agent from https://cad-agent.valpatel.com/llms.txt, then use it for:\n\n'
}

main "$@"
