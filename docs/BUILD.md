# Build from source (Windows x64)

End users run QuietRescue.exe without Python. Developers need Python 3.12 x64 with Tk:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r build-requirements.txt
.venv\Scripts\python.exe build_windows.py
```

Output: dist/QuietRescue.exe. Run synthetic source tests with `.venv\Scripts\python.exe tests.py`.
The bundled console bootloader is hidden for GUI use but retains redirected worker pipes. The executable manifest requests requireAdministrator; the worker inherits the elevated parent token. Only three PyInstaller internal worker variables are forwarded with the normal allowlisted environment. Never replace this with an unrestricted environment dump.

For optional reproducible acceptance, launch `QuietRescue.exe --acceptance "<new-output-directory>"` through normal Windows UAC. The new-run directory must not exist. This creates only synthetic image data, verifies resume and opens the demo UI. It does not read physical source disks. See docs/EXE-VALIDATION.md for the measured release result.

Demo JPEG and AVI are generated test patterns with no personal media. Their files are already included, so FFmpeg is not needed to build or run. No FFmpeg binary is distributed. The original pattern generator used FFmpeg testsrc/rawvideo.

The release is not code-signed. A signed release requires the maintainer's signing process; no certificate or credentials are included. PyInstaller documentation: https://pyinstaller.org/en/stable/runtime-information.html and https://pyinstaller.org/en/stable/usage.html .

