#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
#  FF GUEST ID CLEANER — Termux edition
#  ------------------------------------------------------------
#  How to use:
#    1. Termux:  pkg update && pkg install root-repo tsu
#    2. Enable ROOT in emulator settings
#       (LDPlayer: Settings -> Other -> Root, then RESTART)
#    3.  bash clear_guest.sh
#
#  What it does (option 1):
#    - force-stops Free Fire / Garena MSDK
#    - deletes shared_prefs / databases / no_backup / app_webview /
#      cache / code_cache for every FF package (incl. /data/user_de/0)
#    - sweeps remaining files for guest/msdk/token credentials
#    - ROTATES the Android device ID (android_id) — this is what
#      makes Garena hand out a NEW guest account
#    - verifies nothing credential-like is left
# ============================================================
export PATH="$PATH:/system/bin:/system/xbin:/vendor/bin"

C="\033[1;33m"; R="\033[1;31m"; G="\033[1;32m"; B="\033[1;36m"; N="\033[0m"

KNOWN_PKGS=(com.dts.freefireind com.dts.freefireth com.dts.freefireid com.dts.freefirebd com.dts.freefirebr com.dts.freefiremx com.dts.freefiremax com.garena.msdk)

run_root() {
    local out=""
    if command -v tsu >/dev/null 2>&1; then
        out=$(timeout 25 tsu -c "$1" 2>/dev/null)
    elif command -v su >/dev/null 2>&1; then
        out=$(timeout 25 su -c "$1" 2>/dev/null)
    else
        echo "__NO_SU__"
        return
    fi
    echo "$out"
}

check_root() {
    local who
    who=$(run_root "id -u")
    if [ "$who" = "__NO_SU__" ]; then
        echo -e "${R}[X] No su/tsu found.${N}"
        echo -e "    Run:  pkg install root-repo tsu"
        echo -e "    And enable root: LDPlayer Settings -> Other -> Root"
        exit 1
    elif [ "$who" != "0" ]; then
        echo -e "${R}[X] Root rejected (id -u = $who).${N}"
        echo -e "    Enable root in emulator settings and RESTART the emulator."
        exit 1
    fi
    echo -e "${G}[OK] Root works.${N}"
}

discover_pkgs() {
    local found
    found=$(run_root "ls /data/data 2>/dev/null | grep -iE 'freefire|dts|garena'")
    if [ -n "$found" ]; then
        echo "$found"
    else
        echo "${KNOWN_PKGS[@]}"
    fi
}

build_tool_script() {
    cat > "$HOME/.ff_tool.sh" <<'TOOL'
#!/system/bin/sh
MODE="$1"; shift
PKGS="$*"
case "$MODE" in
    wipe)
        for pkg in $PKGS; do
            base="/data/data/$pkg"
            userde="/data/user_de/0/$pkg"
            am force-stop "$pkg" 2>/dev/null
            echo "=== $pkg ==="
            for d in shared_prefs databases no_backup app_webview cache code_cache; do
                [ -d "$base/$d" ] && { rm -rf "$base/$d"; echo "removed $base/$d"; }
                [ -d "$userde/$d" ] && { rm -rf "$userde/$d"; echo "removed $userde/$d"; }
            done
            [ -d "$base/files" ] && { rm -rf "$base/files"; echo "removed $base/files"; }
            [ -d "$userde/files" ] && { rm -rf "$userde/files"; echo "removed $userde/files"; }
            [ -d "/storage/emulated/0/Android/data/$pkg" ] && { rm -rf "/storage/emulated/0/Android/data/$pkg"; echo "removed external /Android/data/$pkg"; }
            [ -d "/sdcard/Android/data/$pkg" ] && { rm -rf "/sdcard/Android/data/$pkg"; echo "removed /sdcard/Android/data/$pkg"; }
            am force-stop "$pkg" 2>/dev/null
        done
        echo "== WIPE DONE =="
        ;;
    reset)
        for pkg in $PKGS; do
            am force-stop "$pkg" 2>/dev/null
            echo -n "$pkg: "
            pm clear "$pkg" 2>/dev/null | tail -1
        done
        echo "== RESET DONE =="
        ;;
    verify)
        total=0
        for pkg in $PKGS; do
            [ -d "/data/data/$pkg" ] || continue
            n=$(find "/data/data/$pkg" "/data/user_de/0/$pkg" -maxdepth 6 -type f -size -20M 2>/dev/null | while read -r f; do
                grep -aqiE 'guest[._]?(uid|password|pwd|token)|msdk[._]?(uid|token)|access_token' "$f" 2>/dev/null && echo x
            done | wc -l)
            if [ "$n" != "0" ]; then
                echo "$pkg: $n credential file(s) STILL PRESENT"
            else
                echo "$pkg: clean (0)"
            fi
            total=$((total + n))
        done
        echo "== TOTAL CREDENTIAL FILES LEFT: $total =="
        ;;
esac
TOOL
}

verify_report() {
    echo -e "${B}--- VERIFY ---${N}"
    run_root "sh $HOME/.ff_tool.sh verify $1" | grep -v '^$'
}

while true; do
    echo
    echo -e "${C}==============================${N}"
    echo -e "${C}  FF GUEST ID CLEANER (Termux)${N}"
    echo -e "${C}==============================${N}"
    check_root
    PKGS=$(discover_pkgs)
    echo -e "${G}[i] Found packages:${N} $PKGS"
    echo
    echo -e "${C}[1]${N} WIPE storage + ROTATE device ID  (recommended, no re-download)"
    echo -e "${C}[2]${N} WIPE storage ONLY (keep device ID)"
    echo -e "${C}[3]${N} FULL RESET (pm clear) — guaranteed new guest, game re-downloads"
    echo -e "${C}[4]${N} Verify only (check leftover credential files)"
    echo -e "${C}[q]${N} Quit"
    echo -n "> "
    read -r choice
    case "$choice" in
        1|2)
            build_tool_script
            echo -e "${B}--- WIPING ---${N}"
            run_root "sh $HOME/.ff_tool.sh wipe $PKGS" | grep -v '^$' | grep -vE '^removed' || true
            echo -e "${G}[i] Removed items hidden above; run [4] Verify to see leftovers.${N}"
            if [ "$choice" = "1" ]; then
                old_id=$(run_root "settings get secure android_id")
                new_id=$(echo "$RANDOM$RANDOM$RANDOM$RANDOM$RANDOM" | md5sum | cut -c1-16)
                new_id=$(run_root "settings put secure android_id $new_id && settings get secure android_id")
                echo -e "${B}--- DEVICE ID ---${N}"
                echo -e "old: ${R}${old_id:-null}${N}"
                echo -e "new: ${G}${new_id:-FAILED}${N}"
                if [ -z "$new_id" ] || [ "$new_id" = "$old_id" ]; then
                    echo -e "${R}[!] android_id rotation FAILED — try option 3 (pm clear)${N}"
                fi
            fi
            verify_report "$PKGS"
            echo
            echo -e "${G}Now OPEN Free Fire -> Guest login. If it still shows the OLD account,"
            echo -e "run option 3 (FULL RESET).${N}"
            ;;
        3)
            echo -e "${R}Full reset clears ALL game data (fresh install state).${N}"
            echo -n "Type YES to continue: "
            read -r ans
            if [ "$ans" = "YES" ]; then
                build_tool_script
                echo -e "${B}--- PM CLEAR ---${N}"
                run_root "sh $HOME/.ff_tool.sh reset $PKGS" | grep -v '^$'
                echo
                echo -e "${G}Open Free Fire -> Guest login -> brand new account guaranteed.${N}"
            else
                echo "Cancelled."
            fi
            ;;
        4)
            verify_report "$PKGS"
            ;;
        q|Q)
            exit 0
            ;;
        *)
            echo -e "${R}Invalid choice${N}"
            ;;
    esac
done