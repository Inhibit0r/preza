#!/bin/zsh
# Рендер PPTX → PDF → PNG через Microsoft PowerPoint (песочница Office: файл копируется в её контейнер).
# Запуск: render_pptx.sh <deck.pptx> <out_dir>   → out_dir/deck.pdf, out_dir/slide-NN.png
set -euo pipefail
src=${1:A}; out=${2:A}
box=~/Library/Containers/com.microsoft.Powerpoint/Data/render_tmp
mkdir -p "$box" "$out"
cp "$src" "$box/deck.pptx"
rm -f "$box/deck.pdf"
osascript <<EOF
tell application "Microsoft PowerPoint"
  open POSIX file "$box/deck.pptx"
  set p to active presentation
  save p in POSIX file "$box/deck.pdf" as save as PDF
  close p saving no
end tell
EOF
cp "$box/deck.pdf" "$out/deck.pdf"
pdftoppm -png -r 96 "$out/deck.pdf" "$out/slide"  # 13,333 in × 96 dpi = 1280 px
pdffonts "$out/deck.pdf" | awk 'NR>2 {sub(/^[A-Z]+\+/, "", $1); print $1}' | sort -u
