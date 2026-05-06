# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\BC\\anidb-launcher\\anidb_launcher_entry.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\BC\\anidb-launcher\\anidb_launcher\\default_sources.json', 'anidb_launcher')],
    hiddenimports=['PIL.JpegImagePlugin', 'PIL.PngImagePlugin', 'PIL.WebPImagePlugin', 'PIL.GifImagePlugin'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PIL.AvifImagePlugin', 'PIL.BlpImagePlugin', 'PIL.BmpImagePlugin', 'PIL.BufrStubImagePlugin', 'PIL.CurImagePlugin', 'PIL.DcxImagePlugin', 'PIL.DdsImagePlugin', 'PIL.EpsImagePlugin', 'PIL.FitsImagePlugin', 'PIL.FliImagePlugin', 'PIL.FpxImagePlugin', 'PIL.FtexImagePlugin', 'PIL.GbrImagePlugin', 'PIL.GribStubImagePlugin', 'PIL.Hdf5StubImagePlugin', 'PIL.IcnsImagePlugin', 'PIL.IcoImagePlugin', 'PIL.ImImagePlugin', 'PIL.ImtImagePlugin', 'PIL.IptcImagePlugin', 'PIL.Jpeg2KImagePlugin', 'PIL.McIdasImagePlugin', 'PIL.MicImagePlugin', 'PIL.MpegImagePlugin', 'PIL.MpoImagePlugin', 'PIL.MspImagePlugin', 'PIL.PalmImagePlugin', 'PIL.PcdImagePlugin', 'PIL.PcxImagePlugin', 'PIL.PixarImagePlugin', 'PIL.PpmImagePlugin', 'PIL.PsdImagePlugin', 'PIL.QoiImagePlugin', 'PIL.SgiImagePlugin', 'PIL.SpiderImagePlugin', 'PIL.SunImagePlugin', 'PIL.TgaImagePlugin', 'PIL.TiffImagePlugin', 'PIL.WmfImagePlugin', 'PIL.XbmImagePlugin', 'PIL.XpmImagePlugin', 'PIL.XVThumbImagePlugin', 'PIL.ImageCms', 'PIL.ImageDraw', 'PIL.ImageEnhance', 'PIL.ImageGrab', 'PIL.ImageMorph', 'PIL.ImageTransform', 'PIL.PSDraw', 'PIL.BdfFontFile', 'PIL.PcfFontFile', 'PIL.WalImageFile', 'PIL.ContainerIO', 'PIL.TarIO', 'tkinter.test', 'test', 'unittest.test'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='anidb-launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
