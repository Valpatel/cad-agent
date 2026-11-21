#!/usr/bin/env node

var childProcess = require ('child_process');
var path = require ('path');

function GetRebuildDistCommand (platform)
{
    if (platform === 'win32') {
        return {
            command : 'cmd.exe',
            args : ['/d', '/s', '/c', 'tools\\build_wasm_win_dist.bat']
        };
    }

    return {
        command : 'bash',
        args : [path.join ('tools', 'build_wasm_dist.sh')]
    };
}

function Run ()
{
    var rebuildCommand = GetRebuildDistCommand (process.platform);
    var result = childProcess.spawnSync (
        rebuildCommand.command,
        rebuildCommand.args,
        {
            cwd : path.join (__dirname, '..'),
            stdio : 'inherit'
        }
    );

    if (result.error) {
        console.error (result.error.message);
        return 1;
    }

    return result.status === null ? 1 : result.status;
}

if (require.main === module) {
    process.exit (Run ());
}

module.exports = {
    GetRebuildDistCommand : GetRebuildDistCommand
};
