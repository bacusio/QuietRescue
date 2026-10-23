# Third-party components in the executable

QuietRescue source and documentation: MIT (LICENSE). No DiskGenius code or binaries are included.

Python 3.12, Tcl/Tk and Pillow 12.3.0 are embedded in the Windows EXE. Their retained license notices are in licenses/. Pillow's notice also covers its bundled image libraries. Windows system libraries and codecs are supplied by Windows, not redistributed here.

The Python runtime also includes OpenSSL 3.5.8; its Apache 2.0 license is retained in licenses/OpenSSL-LICENSE.txt. Tcl 8.6.12's upstream notice is in licenses/Tcl-license.terms. Upstream source notices: https://github.com/openssl/openssl/tree/openssl-3.5.8 and https://github.com/tcltk/tcl/tree/core-8-6-12 .

PyInstaller 6.22.3 supplies the bootloader under GPL with a distribution exception; its notice is retained. The exception permits distributing the application under its own license. See https://pyinstaller.org/en/stable/license.html .

Public packages do not redistribute PhotoRec/TestDisk or their dependent DLLs. Install-OfficialTools.ps1 downloads the pinned official 7.2 archive directly from CGSecurity and preserves its notices. These external tools have their own licenses and are not relicensed under QuietRescue MIT. Official distribution and source: https://www.cgsecurity.org/wiki/TestDisk_Download .

The synthetic JPEG and AVI are project-generated demo media. FFmpeg was used only to produce the synthetic AVI and is not distributed or needed at runtime.
