# Third-party software

The release downloads bundle the following software. Each keeps its own licence.

| Component | Used for | Licence |
|---|---|---|
| [Python](https://www.python.org/) | runs the app (inside the Windows `.exe` and Linux binary) | Python Software Foundation License |
| [Tcl/Tk](https://www.tcl-lang.org/) and Tkinter | the window and drawing | Tcl/Tk licence (BSD-style) |
| [tkinterdnd2](https://github.com/Eliav2/tkinterdnd2) 0.4.2 | drag and drop | MIT |
| [tkdnd](https://github.com/petasis/tkdnd) (included in tkinterdnd2) | drag and drop | BSD-style |
| [PyInstaller](https://pyinstaller.org/) bootloader | starts the one-file `.exe` and Linux binary | GPL 2.0 with an exception that allows distributing built programs under any licence |

The `.deb` package uses the Python and Tk that Ubuntu installs, and bundles only tkinterdnd2.
