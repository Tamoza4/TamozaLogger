#!/usr/bin/env bash
# ==============================================================================
# TamozaLogger — Systemd Service Manager (English Only)
# ==============================================================================

SERVICE_NAME="tamozalogger.service"
SERVICE_FILE="/etc/systemd/system/tamozalogger.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Check sudo / root
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo -e "${RED}[ERROR] This script requires sudo or root privileges.${NC}"
        exit 1
    fi
fi

# Ensure service file exists and is configured properly for boot
ensure_service_installed() {
    CURRENT_USER="$(id -un)"
    $SUDO bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=TamozaLogger Discord Bot
Wants=network-online.target postgresql.service
After=network-online.target postgresql.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF"
    $SUDO systemctl daemon-reload >/dev/null 2>&1 || true
}

start_service() {
    ensure_service_installed
    echo -e "${CYAN}[*] Starting TamozaLogger service...${NC}"
    $SUDO systemctl start "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}[OK] TamozaLogger service is now RUNNING.${NC}"
    else
        echo -e "${RED}[ERROR] Failed to start TamozaLogger. Recent logs:${NC}"
        $SUDO journalctl -u "$SERVICE_NAME" -n 25 --no-pager
    fi
}

stop_service() {
    echo -e "${YELLOW}[*] Stopping TamozaLogger service...${NC}"
    $SUDO systemctl stop "$SERVICE_NAME"
    sleep 1
    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}[OK] TamozaLogger service has been STOPPED.${NC}"
    else
        echo -e "${RED}[ERROR] Service is still active.${NC}"
    fi
}

restart_service() {
    ensure_service_installed
    echo -e "${CYAN}[*] Restarting TamozaLogger service...${NC}"
    $SUDO systemctl restart "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}[OK] TamozaLogger service RESTARTED successfully.${NC}"
    else
        echo -e "${RED}[ERROR] Restart failed. Recent logs:${NC}"
        $SUDO journalctl -u "$SERVICE_NAME" -n 25 --no-pager
    fi
}

status_service() {
    echo -e "${BOLD}==================== TAMOZA LOGGER STATUS ====================${NC}"
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        echo -e "Status: ${GREEN}${BOLD}● RUNNING (Active)${NC}"
    else
        echo -e "Status: ${RED}${BOLD}○ STOPPED (Inactive)${NC}"
    fi

    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        echo -e "Auto-start on Boot: ${GREEN}Enabled${NC}"
    else
        echo -e "Auto-start on Boot: ${YELLOW}Disabled${NC}"
    fi
    echo -e "=============================================================="
    $SUDO systemctl status "$SERVICE_NAME" --no-pager
}

logs_service() {
    echo -e "${CYAN}[*] Streaming live logs (Press Ctrl+C to exit)...${NC}\n"
    $SUDO journalctl -u "$SERVICE_NAME" -f -n 50
}

enable_service() {
    ensure_service_installed
    echo -e "${CYAN}[*] Enabling auto-start on boot...${NC}"
    $SUDO systemctl enable "$SERVICE_NAME"
    echo -e "${GREEN}[OK] Service enabled to start automatically on system boot.${NC}"
}

disable_service() {
    echo -e "${YELLOW}[*] Disabling auto-start on boot...${NC}"
    $SUDO systemctl disable "$SERVICE_NAME"
    echo -e "${GREEN}[OK] Service disabled from starting on system boot.${NC}"
}

show_menu() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "=============================================================="
    echo "            TAMOZA LOGGER — SERVICE MANAGER                   "
    echo "=============================================================="
    echo -e "${NC}"
    
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        echo -e "  Current State: ${GREEN}${BOLD}● RUNNING${NC}"
    else
        echo -e "  Current State: ${RED}${BOLD}○ STOPPED${NC}"
    fi
    echo -e "--------------------------------------------------------------"
    echo -e "  ${BOLD}1)${NC} ${GREEN}Start Service${NC}"
    echo -e "  ${BOLD}2)${NC} ${RED}Stop Service${NC}"
    echo -e "  ${BOLD}3)${NC} ${YELLOW}Restart Service${NC}"
    echo -e "  ${BOLD}4)${NC} ${BLUE}Check Status${NC}"
    echo -e "  ${BOLD}5)${NC} ${CYAN}Live Logs${NC}"
    echo -e "  ${BOLD}6)${NC} Enable Auto-start on Boot"
    echo -e "  ${BOLD}7)${NC} Disable Auto-start on Boot"
    echo -e "  ${BOLD}0)${NC} Exit"
    echo -e "=============================================================="
    echo -n "Choose an option [0-7]: "
    read -r choice
    echo ""

    case "$choice" in
        1) start_service ;;
        2) stop_service ;;
        3) restart_service ;;
        4) status_service ;;
        5) logs_service ;;
        6) enable_service ;;
        7) disable_service ;;
        0) exit 0 ;;
        *) echo -e "${RED}Invalid choice!${NC}" ;;
    esac
}

case "$1" in
    start)   start_service ;;
    stop)    stop_service ;;
    restart) restart_service ;;
    status)  status_service ;;
    logs)    logs_service ;;
    enable)  enable_service ;;
    disable) disable_service ;;
    *)       show_menu ;;
esac
