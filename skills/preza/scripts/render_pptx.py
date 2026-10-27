"""PowerPoint -> PDF -> PNG on Windows and macOS; preserve the source and prior renders."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from xml.etree import ElementTree as ET


def validate_paths(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source.suffix.lower() != '.pptx' or not source.is_file():
        raise ValueError('Input must be an existing .pptx file')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError('Use a new or empty output directory; existing results are preserved')
    return source, output


def render(source, output):
    source, output = validate_paths(source, output)
    if sys.platform == 'darwin':
        return render_mac(source, output)
    if os.name != 'nt':
        raise RuntimeError('This adapter requires Windows PowerPoint')
    binaries = {name: shutil.which(name) for name in ['powershell.exe', 'pdftoppm', 'pdffonts']}
    if not all(binaries.values()):
        raise RuntimeError('PowerShell and Poppler (pdftoppm, pdffonts) must be in PATH')
    output.mkdir(parents=True, exist_ok=True)
    pdf = output / 'deck.pdf'
    # PowerPoint can reuse an already open presentation; always open our own copy.
    working = output / '_render-source.pptx'
    shutil.copyfile(source, working)
    try:
        result = subprocess.run([
            binaries['powershell.exe'], '-NoProfile', '-NonInteractive', '-File',
            str(Path(__file__).with_name('export_pdf.ps1')),
            '-InputPath', str(working), '-OutputPath', str(pdf)
        ], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    finally:
        try:
            working.unlink()
        except PermissionError:
            # An interrupted Office process may retain the copy; keep it for diagnosis.
            print(f'PowerPoint still holds the temporary copy: {working}', file=sys.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    info = json.loads(result.stdout.strip())
    if pdf.read_bytes()[:5] != b'%PDF-':
        raise RuntimeError('PowerPoint output is not a PDF')
    subprocess.run([binaries['pdftoppm'], '-png', '-scale-to-x', '1280', '-scale-to-y', '-1',
                    str(pdf), str(output / 'slide')], check=True, timeout=180)
    fonts = subprocess.run([binaries['pdffonts'], str(pdf)], check=True,
                           capture_output=True, text=True, encoding='utf-8', timeout=30).stdout
    (output / 'fonts.txt').write_text(fonts, encoding='utf-8')
    images = sorted(output.glob('slide-*.png'))
    if len(images) != info['slides']:
        raise RuntimeError(f"Rendered {len(images)} images for {info['slides']} slides")
    from PIL import Image
    sizes = []
    for image in images:
        with Image.open(image) as im:
            im.verify()
            sizes.append(list(im.size))
    info.update(pdf=str(pdf), images=[str(p) for p in images], sizes=sizes)
    (output / 'render.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    return info


def render_mac(source, output):
    # Keep the existing AppleScript path for Claude/macOS users.
    result = subprocess.run(['/bin/zsh', str(Path(__file__).with_suffix('.sh')),
                             str(source), str(output)],
                            capture_output=True, text=True, encoding='utf-8', timeout=180)
    if result.returncode:  # причина (модальное окно, не та копия) — в stderr скрипта
        raise RuntimeError((result.stderr or result.stdout).strip() or f'render_pptx.sh: код {result.returncode}')
    (output / 'fonts.txt').write_text(result.stdout, encoding='utf-8')
    with zipfile.ZipFile(source) as archive:
        presentation = ET.fromstring(archive.read('ppt/presentation.xml'))
    count = len(presentation.findall('.//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId'))
    images = sorted(output.glob('slide-*.png'))
    if len(images) != count:
        raise RuntimeError(f'Rendered {len(images)} images for {count} slides')
    info = {'slides': count, 'platform': 'darwin', 'pdf': str(output / 'deck.pdf'),
            'images': [str(p) for p in images]}
    (output / 'render.json').write_text(json.dumps(info, indent=2), encoding='utf-8')
    return info


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pptx')
    parser.add_argument('output', help='новая или пустая папка 5-проверка/round<N> (старая работа — render/round<N>)')
    args = parser.parse_args()
    try:
        print(json.dumps(render(args.pptx, args.output), ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
