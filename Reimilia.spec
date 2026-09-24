# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— 产出单文件可执行程序 ``dist/reimilia``。

推荐用 ``./build.sh``（会自动建 venv 并装好 PyInstaller）：

    ./build.sh

也可以手动执行：

    python3 -m pip install pyinstaller
    pyinstaller --clean --noconfirm Reimilia.spec

要求 PyInstaller >= 6.0（本文件用的是 6.x 的 spec 写法：
``PYZ(a.pure)`` 与单文件 ``EXE(pyz, a.scripts, a.binaries, a.datas, ...)``）。

注意：``static/`` 与 ``repo/`` 会被打进包里，运行时由
``reimilia/paths.py`` 的 ``resource_dir()`` 从 ``sys._MEIPASS`` 读取，
因此单文件也能正常提供 WebUI 页面与内置项目列表。
"""

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("static", "static"),
        ("repo", "repo"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 这些标准库模块用不到，剔掉能明显减小体积
    excludes=[
        "tkinter",
        "unittest",
        "pydoc_data",
        "lib2to3",
        "distutils",
        "setuptools",
        "pip",
    ],
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
    name="reimilia",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
)
