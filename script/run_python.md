<%*

const { exec } = require("child_process");
const path = require("path");

const currentFile = app.workspace.getActiveFile();

const currentDir =
    path.dirname(
        app.vault.adapter.getFullPath(currentFile.path)
    );

const py =
    path.join(currentDir, "gen.py");

exec(
    `python "${py}"`,
    { cwd: currentDir },
    (err, stdout, stderr) => {

        if (err) {
            console.log(stderr);
            new Notice("Python Error");
            return;
        }

        console.log(stdout);
        new Notice("Python Done");
    }
);

%>