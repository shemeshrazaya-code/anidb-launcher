"""Build a standalone desktop app with PyInstaller.

Run from the project root:
    python -m pip install -r requirements.txt
    python -m pip install pyinstaller
    python build.py

Outputs by platform:
- Windows: dist/anidb-launcher.exe
- macOS:   dist/anidb-launcher.app
- Linux:   dist/anidb-launcher
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ENTRY = PROJECT_ROOT / "anidb_launcher_entry.py"
APP_NAME = "anidb-launcher"
DEFAULT_SOURCES = PROJECT_ROOT / "anidb_launcher" / "default_sources.json"


def _find_upx_dir() -> str | None:
    if sys.platform != "win32":
        return None
    upx_on_path = shutil.which("upx")
    if upx_on_path:
        return str(Path(upx_on_path).parent)

    winget_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_root.is_dir():
        for match in winget_root.glob("UPX.UPX_*/upx-*-win64/upx.exe"):
            return str(match.parent)
    return None


def _bundle_args() -> list[str]:
    if sys.platform == "darwin":
        # macOS .app bundle. Keep onedir to avoid onefile extraction lag.
        return ["--onedir", "--windowed", "--argv-emulation"]
    # Windows/Linux: single-file GUI binary.
    return ["--onefile", "--windowed"]


def _expected_artifact_path() -> Path:
    dist = PROJECT_ROOT / "dist"
    if sys.platform == "win32":
        return dist / f"{APP_NAME}.exe"
    if sys.platform == "darwin":
        return dist / f"{APP_NAME}.app"
    return dist / APP_NAME


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("error: PyInstaller is not installed.", file=sys.stderr)
        print("       Run: python -m pip install pyinstaller", file=sys.stderr)
        return 1

    if not DEFAULT_SOURCES.exists():
        print(f"warn: {DEFAULT_SOURCES} missing; bundled defaults will be unavailable.", file=sys.stderr)

    for d in ("build", "dist"):
        target = PROJECT_ROOT / d
        if target.is_dir():
            shutil.rmtree(target)
        elif target.is_file():
            target.unlink()

    # PyInstaller's --add-data uses ';' on Windows, ':' elsewhere.
    sep = ";" if sys.platform == "win32" else ":"
    add_data = f"{DEFAULT_SOURCES}{sep}anidb_launcher"

    upx_args: list[str] = ["--noupx"]
    if sys.platform == "win32":
        upx_dir = _find_upx_dir()
        if upx_dir:
            upx_args = [f"--upx-dir={upx_dir}"]
        else:
            print(
                "warn: UPX not found; Windows build will be larger. "
                "Install with: winget install UPX.UPX",
                file=sys.stderr,
            )

    pil_hidden_imports = [
        "PIL.JpegImagePlugin",
        "PIL.PngImagePlugin",
        "PIL.WebPImagePlugin",
        "PIL.GifImagePlugin",
    ]
    pil_excludes = [
        "PIL.AvifImagePlugin",
        "PIL.BlpImagePlugin", "PIL.BmpImagePlugin", "PIL.BufrStubImagePlugin",
        "PIL.CurImagePlugin", "PIL.DcxImagePlugin", "PIL.DdsImagePlugin",
        "PIL.EpsImagePlugin", "PIL.FitsImagePlugin", "PIL.FliImagePlugin",
        "PIL.FpxImagePlugin", "PIL.FtexImagePlugin", "PIL.GbrImagePlugin",
        "PIL.GribStubImagePlugin", "PIL.Hdf5StubImagePlugin",
        "PIL.IcnsImagePlugin", "PIL.IcoImagePlugin", "PIL.ImImagePlugin",
        "PIL.ImtImagePlugin", "PIL.IptcImagePlugin", "PIL.Jpeg2KImagePlugin",
        "PIL.McIdasImagePlugin", "PIL.MicImagePlugin", "PIL.MpegImagePlugin",
        "PIL.MpoImagePlugin", "PIL.MspImagePlugin", "PIL.PalmImagePlugin",
        "PIL.PcdImagePlugin", "PIL.PcxImagePlugin", "PIL.PixarImagePlugin",
        "PIL.PpmImagePlugin", "PIL.PsdImagePlugin", "PIL.QoiImagePlugin",
        "PIL.SgiImagePlugin", "PIL.SpiderImagePlugin", "PIL.SunImagePlugin",
        "PIL.TgaImagePlugin", "PIL.TiffImagePlugin", "PIL.WmfImagePlugin",
        "PIL.XbmImagePlugin", "PIL.XpmImagePlugin", "PIL.XVThumbImagePlugin",
        "PIL.ImageCms", "PIL.ImageDraw", "PIL.ImageEnhance", "PIL.ImageGrab",
        "PIL.ImageMorph", "PIL.ImageTransform", "PIL.PSDraw",
        "PIL.BdfFontFile", "PIL.PcfFontFile", "PIL.WalImageFile",
        "PIL.ContainerIO", "PIL.TarIO",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        *_bundle_args(),
        f"--name={APP_NAME}",
        f"--add-data={add_data}",
        *[f"--hidden-import={m}" for m in pil_hidden_imports],
        *[f"--exclude-module={m}" for m in pil_excludes],
        "--exclude-module=tkinter.test",
        "--exclude-module=test",
        "--exclude-module=unittest.test",
        *upx_args,
        "--noconfirm",
        str(ENTRY),
    ]

    print("running:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=str(PROJECT_ROOT))
    if rc != 0:
        return rc

    artifact = _expected_artifact_path()
    if artifact.is_file():
        size_mb = artifact.stat().st_size / 1_048_576
        print(f"build: {artifact}  {size_mb:.2f} MB")
    elif artifact.is_dir():
        print(f"build: {artifact}")
    else:
        print(f"build complete; check {PROJECT_ROOT / 'dist'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
