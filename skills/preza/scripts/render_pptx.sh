#!/bin/zsh
# Рендер PPTX → PDF → PNG через Microsoft PowerPoint (песочница Office: файл копируется в её контейнер).
# Запуск: render_pptx.sh <deck.pptx> <out_dir>   → out_dir/deck.pdf, out_dir/slide-NN.png
# Копия получает уникальное имя, и закрывается только она: открытые презентации пользователя остаются как есть.
set -euo pipefail
src=${1:A}; out=${2:A}
name="preza-render-$$-$RANDOM"
box=~/Library/Containers/com.microsoft.Powerpoint/Data/render_tmp/$name
mkdir -p "$box" "$out"
trap 'rm -f "$box/$name.pptx" "$box/deck.pdf"; rmdir "$box" 2>/dev/null || true' EXIT  # и при ошибке
cp "$src" "$box/$name.pptx"
osascript <<EOF
tell application "Microsoft PowerPoint"
  try
    with timeout of 150 seconds
      open POSIX file "$box/$name.pptx"
      set p to presentation "$name.pptx"
      if full name of p is not "$box/$name.pptx" then error "открыта не та копия: " & (full name of p)
      save p in POSIX file "$box/deck.pdf" as save as PDF
      close p saving no
    end timeout
  on error msg number n
    try
      with timeout of 10 seconds
        set q to presentation "$name.pptx"
        if full name of q is "$box/$name.pptx" then close q saving no
      end timeout
    end try
    if n is -1712 then set msg to "PowerPoint не ответил за 150 с: закройте его модальное окно (восстановление, экспорт) и повторите рендер"
    error msg number n
  end try
end tell
EOF
cp "$box/deck.pdf" "$out/deck.pdf"
pdftoppm -png -r 96 "$out/deck.pdf" "$out/slide"  # 13,333 in × 96 dpi = 1280 px
pdffonts "$out/deck.pdf" | awk 'NR>2 {sub(/^[A-Z]+\+/, "", $1); print $1}' | sort -u
