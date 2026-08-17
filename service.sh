#!/usr/bin/env bash
# ==============================================================================
# TamozaLogger — Service Control Manager (Systemd)
# Used to Start, Stop, Restart, Check Status, and View Live Logs.
# ==============================================================================

SERVICE_NAME="tamozalogger.service"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Check sudo
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo -e "${RED}[ERROR] This script requires sudo or root privileges.${NC}"
        exit 1
    fi
fi

# Check if service file exists
check_service_installed() {
    if ! systemctl list-unit-files "$SERVICE_NAME" >/dev/null 2>&1 && [ ! -f "/etc/systemd/system/$SERVICE_NAME" ]; then
        echo -e "${RED}[!] Error: Service '$SERVICE_NAME' is not installed.${NC}"
        echo -e "    Please run ${CYAN}./install.sh${NC} first to set up the service."
        exit 1
    fi
}

start_service() {
    check_service_installed
    echo -e "${CYAN}[*] Starting TamozaLogger service...${NC}"
    $SUDO systemctl start "$SERVICE_NAME"
    sleep 1
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}[✓] TamozaLogger is now RUNNING!${NC}"
    else
        echo -e "${RED}[✗] Failed to start TamozaLogger. Checking logs...${NC}"
        $SUDO journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    fi
}

stop_service() {
    check_service_installed
    echo -e "${YELLOW}[*] Stopping TamozaLogger service...${NC}"
    $SUDO systemctl stop "$SERVICE_NAME"
    sleep 1
    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}[✓] TamozaLogger has been STOPPED.${NC}"
    else
        echo -e "${RED}[✗] Service is still active.${NC}"
    fi
}

restart_service() {
    check_service_installed
    echo -e "${CYAN}[*] Restarting TamozaLogger service...${NC}"
    $SUDO systemctl restart "$SERVICE_NAME"
    sleep 1
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "${GREEN}[✓] TamozaLogger RESTARTED successfully!${NC}"
    else
        echo -e "${RED}[✗] Restart failed. Checking logs...${NC}"
        $SUDO journalctl -u "$SERVICE_NAME" -n 20 --no-pager
    fi
}

status_service() {
    check_service_installed
    echo -e "${BOLD}==================== TAMOZA LOGGER STATUS ====================${NC}"
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "Status: ${GREEN}${BOLD}● RUNNING (نشط ويعمل)${NC}"
    else
        echo -e "Status: ${RED}${BOLD}○ STOPPED (متوقف)${NC}"
    fi

    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        echo -e "Auto-start on boot: ${GREEN}Enabled (مفعل مع إقلاع النظام)${NC}"
    else
        echo -e "Auto-start on boot: ${YELLOW}Disabled (غير مفعل)${NC}"
    fi
    echo -e "=============================================================="
    $SUDO systemctl status "$SERVICE_NAME" --no-pager
}

logs_service() {
    check_service_installed
    echo -e "${CYAN}[*] Streaming live logs (Press Ctrl+C to exit)...${NC}\n"
    $SUDO journalctl -u "$SERVICE_NAME" -f -n 50
}

enable_service() {
    check_service_installed
    echo -e "${CYAN}[*] Enabling auto-start on boot...${NC}"
    $SUDO systemctl enable "$SERVICE_NAME"
    echo -e "${GREEN}[✓] Service enabled on boot.${NC}"
}

disable_service() {
    check_service_installed
    echo -e "${YELLOW}[*] Disabling auto-start on boot...${NC}"
    $SUDO systemctl disable "$SERVICE_NAME"
    echo -e "${GREEN}[✓] Service disabled from boot.${NC}"
}

show_menu() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "=============================================================="
    echo "            TAMOZA LOGGER — SERVICE MANAGER                   "
    echo "=============================================================="
    echo -e "${NC}"
    
    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        echo -e "  Current State: ${GREEN}${BOLD}● RUNNING (يعمل)${NC}"
    else
        echo -e "  Current State: ${RED}${BOLD}○ STOPPED (متوقف)${NC}"
    fi
    echo -e "--------------------------------------------------------------"
    echo -e "  ${BOLD}1)${NC} ${GREEN}Start Service${NC}        (تشغيل الخدمة)"
    echo -e "  ${BOLD}2)${NC} ${RED}Stop Service${NC}         (إيقاف الخدمة)"
    echo -e "  ${BOLD}3)${NC} ${YELLOW}Restart Service${NC}      (إعادة تشغيل الخدمة)"
    echo -e "  ${BOLD}4)${NC} ${BLUE}Check Status${NC}         (عرض الحالة الحالية)"
    echo -e "  ${BOLD}5)${NC} ${CYAN}Live Logs${NC}            (متابعة السجلات الحية)"
    echo -e "  ${BOLD}6)${NC} Enable on Boot       (تفعيل التشغيل التلقائي مع السيرفر)"
    echo -e "  ${BOLD}7)${NC} Disable on Boot      (إلغاء التشغيل التلقائي مع السيرفر)"
    echo -e "  ${BOLD}0)${NC} Exit                 (خروج)"
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

# CLI Argument Router
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
