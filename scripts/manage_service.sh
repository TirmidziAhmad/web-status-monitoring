#!/usr/bin/env bash

# Management script for cPanel Monitor systemd user service
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ACTION="${1:-status}"
SERVICE_NAME="cpanel-monitor"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

mkdir -p "$SYSTEMD_USER_DIR"

case "$ACTION" in
    install)
        echo "========================================================="
        echo "  Memasang Background Service ($SERVICE_NAME)"
        echo "========================================================="
        if [ ! -d "$PROJECT_ROOT/venv" ]; then
            echo "[!] Menyiapkan virtual environment terlebih dahulu..."
            bash "$PROJECT_ROOT/scripts/setup.sh"
        fi

        cp "$PROJECT_ROOT/service/${SERVICE_NAME}.service" "$SYSTEMD_USER_DIR/"
        systemctl --user daemon-reload
        systemctl --user enable --now "${SERVICE_NAME}.service"

        echo ""
        echo "[SUKSES] Service ${SERVICE_NAME} berhasil dipasang dan diaktifkan!"
        echo "Bot sekarang berjalan 24/7 di latar belakang."
        echo ""
        systemctl --user status "${SERVICE_NAME}.service" --no-pager || true
        ;;

    start)
        systemctl --user start "${SERVICE_NAME}.service"
        echo "Service ${SERVICE_NAME} dinyalakan."
        ;;

    stop)
        systemctl --user stop "${SERVICE_NAME}.service"
        echo "Service ${SERVICE_NAME} dimatikan."
        ;;

    restart)
        systemctl --user restart "${SERVICE_NAME}.service"
        echo "Service ${SERVICE_NAME} dimulai ulang."
        ;;

    status)
        echo "Status Service ${SERVICE_NAME}:"
        echo "---------------------------------------------------------"
        systemctl --user status "${SERVICE_NAME}.service" --no-pager || true
        ;;

    logs)
        echo "Menampilkan 50 log terakhir (Tekan Ctrl+C untuk keluar):"
        journalctl --user -u "${SERVICE_NAME}.service" -n 50 -f
        ;;

    uninstall)
        echo "Menonaktifkan dan menghapus service ${SERVICE_NAME}..."
        systemctl --user stop "${SERVICE_NAME}.service" 2>/dev/null || true
        systemctl --user disable "${SERVICE_NAME}.service" 2>/dev/null || true
        rm -f "${SYSTEMD_USER_DIR}/${SERVICE_NAME}.service"
        systemctl --user daemon-reload
        echo "Service ${SERVICE_NAME} berhasil dihapus dari sistem."
        ;;

    *)
        echo "Penggunaan: $0 {install|start|stop|restart|status|logs|uninstall}"
        exit 1
        ;;
esac
