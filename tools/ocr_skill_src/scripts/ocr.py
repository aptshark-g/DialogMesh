#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local OCR tool for Codex: extract text from images before visual processing.

Uses the Windows built-in OCR engine (Windows.Media.Ocr) via PowerShell —
zero dependencies, native en-US + zh-Hans-CN support.

Usage:
    python ocr.py <image_path> [more_paths...]

Output: for each image, print detected text blocks with confidence.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile


PS_SCRIPT = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation, ContentType=WindowsRuntime]

function Await($WinRtTask, $ResultType) {
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                       $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    $netTask = $asTaskGeneric.MakeGenericMethod($ResultType).Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

function AwaitAction($WinRtTask) {
    $asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
                       $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
}

param([string]$ImagePath, [double]$MinConf)

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage(
    [Windows.Globalization.Language]::new('en-US')) }
if ($null -eq $engine) { throw "No OCR engine available" }

$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])

$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) {
    foreach ($w in $line.Words) {
        Write-Output ("{0}`t{1:F3}" -f $w.Text, $w.Confidence)
    }
    Write-Output ""
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Windows built-in OCR (en/zh)")
    parser.add_argument("images", nargs="+", help="image file path(s)")
    parser.add_argument("--min-conf", type=float, default=0.0,
                        help="drop words below this confidence (default 0.0)")
    args = parser.parse_args()

    ok = True
    for path in args.images:
        print(f"=== {path} ===")
        fd, ps1 = tempfile.mkstemp(suffix=".ps1")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("param([string]$ImagePath, [double]$MinConf)\n")
                f.write(PS_SCRIPT + "\n")
            cmd = [
                "powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
                "-File", ps1, "-ImagePath", path, "-MinConf", str(args.min_conf),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=120, encoding="utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            print(f"[ocr] ERROR {path}: {exc}", file=sys.stderr)
            ok = False
            continue
        finally:
            try:
                os.unlink(ps1)
            except OSError:
                pass
        if proc.returncode != 0:
            print(f"[ocr] ERROR {path}: {proc.stderr.strip()}", file=sys.stderr)
            ok = False
            continue
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        if not lines:
            print("(no text detected)")
            continue
        for ln in lines:
            if "\t" in ln:
                text, conf = ln.rsplit("\t", 1)
                try:
                    c = float(conf)
                except ValueError:
                    c = 0.0
                if c >= args.min_conf and text.strip():
                    print(f"[{c:.2f}] {text.strip()}")
            else:
                print(ln)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
