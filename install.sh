#!/usr/bin/env bash
# ==============================================================================
# TamozaLogger — Interactive Automated Linux Installer (Zero Hardcoding)
# Supported OS: Ubuntu, Debian, CentOS, RHEL, Fedora, Arch Linux, Alpine
# ==============================================================================

set -e

# ANSI Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${CYAN}${BOLD}"
echo "==============================================================================="
echo "               TAMOZA LOGGER — AUTOMATED LINUX INSTALLER                       "
echo "==============================================================================="
echo -e "${NC}"

# ------------------------------------------------------------------------------
# Step 1: Detect User & Root Privileges
# ------------------------------------------------------------------------------
echo -e "${BLUE}[1/6] Checking user permissions...${NC}"
SUDO_CMD=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO_CMD="sudo"
        echo -e "${GREEN}[OK] Running as non-root user with sudo access.${NC}"
    else
        echo -e "${RED}[ERROR] This installer requires root or sudo privileges.${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}[OK] Running with root permissions.${NC}"
fi

# Detect working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# PostgreSQL command helper (Works for both root and sudo)
run_pg_sql() {
    local query="$1"
    if [ "$EUID" -eq 0 ]; then
        su - postgres -c "psql -c \"$query\"" >/dev/null 2>&1 || true
    else
        sudo -u postgres psql -c "$query" >/dev/null 2>&1 || true
    fi
}

# ------------------------------------------------------------------------------
# Step 2: Detect Linux Distribution & Install System Packages
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[2/6] Detecting Linux distribution and installing system packages...${NC}"

if command -v apt-get >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Debian / Ubuntu based system detected.${NC}"
    $SUDO_CMD apt-get update -y
    $SUDO_CMD apt-get install -y python3 python3-pip python3-venv python3-dev \
        postgresql postgresql-contrib libpq-dev git curl build-essential
elif command -v dnf >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Fedora / RHEL / Rocky Linux detected.${NC}"
    $SUDO_CMD dnf install -y python3 python3-pip python3-devel \
        postgresql-server postgresql-contrib libpq-devel git curl gcc
    if [ ! -d "/var/lib/pgsql/data" ] || [ -z "$(ls -A /var/lib/pgsql/data 2>/dev/null)" ]; then
        $SUDO_CMD postgresql-setup --initdb || true
    fi
elif command -v yum >/dev/null 2>&1; then
    echo -e "${CYAN}[*] CentOS / Amazon Linux detected.${NC}"
    $SUDO_CMD yum install -y python3 python3-pip python3-devel \
        postgresql-server postgresql-contrib git curl gcc
    if [ ! -d "/var/lib/pgsql/data" ] || [ -z "$(ls -A /var/lib/pgsql/data 2>/dev/null)" ]; then
        $SUDO_CMD postgresql-setup initdb || true
    fi
elif command -v pacman >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Arch Linux detected.${NC}"
    $SUDO_CMD pacman -Sy --noconfirm python python-pip postgresql git curl base-devel
    if [ ! -d "/var/lib/postgres/data" ] || [ -z "$(ls -A /var/lib/postgres/data 2>/dev/null)" ]; then
        $SUDO_CMD -u postgres initdb -D /var/lib/postgres/data || true
    fi
elif command -v apk >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Alpine Linux detected.${NC}"
    $SUDO_CMD apk add --no-cache python3 py3-pip py3-virtualenv python3-dev \
        postgresql postgresql-contrib git curl build-base
fi

# ------------------------------------------------------------------------------
# Step 3: Start and Enable PostgreSQL Service
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[3/6] Starting PostgreSQL service...${NC}"

if command -v systemctl >/dev/null 2>&1; then
    $SUDO_CMD systemctl enable postgresql || true
    $SUDO_CMD systemctl start postgresql || true
    echo -e "${GREEN}[OK] PostgreSQL service started.${NC}"
elif command -v service >/dev/null 2>&1; then
    $SUDO_CMD service postgresql start || true
    echo -e "${GREEN}[OK] PostgreSQL service started.${NC}"
elif command -v rc-service >/dev/null 2>&1; then
    $SUDO_CMD rc-service postgresql start || true
    echo -e "${GREEN}[OK] PostgreSQL service started with OpenRC.${NC}"
fi

# ------------------------------------------------------------------------------
# Step 4: Interactive Configuration Wizard
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}${BOLD}==============================================================================="
echo "                INTERACTIVE CONFIGURATION WIZARD                               "
echo "===============================================================================${NC}"
echo -e "Please enter your custom credentials below:\n"

# 1. Discord Bot Token
BOT_TOKEN=""
while [ -z "$BOT_TOKEN" ]; do
    echo -e "${CYAN}1. Discord Bot Token:${NC}"
    read -rp "   Enter your Discord Bot Token: " BOT_TOKEN
    if [ -z "$BOT_TOKEN" ]; then
        echo -e "${RED}   [!] Bot token cannot be empty.${NC}"
    fi
done

echo ""
echo -e "${CYAN}2. PostgreSQL Database Settings (Press ENTER for defaults):${NC}"

# 2. Database Host
read -rp "   Database Host [default: localhost]: " DB_HOST
DB_HOST=${DB_HOST:-localhost}

# 3. Database Port
read -rp "   Database Port [default: 5432]: " DB_PORT
DB_PORT=${DB_PORT:-5432}

# 4. Database Name
read -rp "   Database Name [default: tamoza_logger]: " DB_NAME
DB_NAME=${DB_NAME:-tamoza_logger}

# 5. Database Username
read -rp "   Database Username [default: tamoza]: " DB_USER
DB_USER=${DB_USER:-tamoza}

# 6. Database Password
DB_PASS=""
while [ -z "$DB_PASS" ]; do
    read -rsp "   Database Password for '$DB_USER': " DB_PASS
    echo ""
    if [ -z "$DB_PASS" ]; then
        echo -e "${RED}   [!] Password cannot be empty.${NC}"
    fi
done

# ------------------------------------------------------------------------------
# Step 5: Setup PostgreSQL Database User and Privileges
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[4/6] Creating database user and database in PostgreSQL...${NC}"

# If host is localhost / 127.0.0.1, auto-create via local postgres service
if [ "$DB_HOST" = "localhost" ] || [ "$DB_HOST" = "127.0.0.1" ]; then
    run_pg_sql "DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN
        CREATE ROLE \"$DB_USER\" WITH LOGIN PASSWORD '$DB_PASS' CREATEDB;
    ELSE
        ALTER ROLE \"$DB_USER\" WITH PASSWORD '$DB_PASS';
    END IF;
END
\$\$;"

    # Create Database if not exists
    if [ "$EUID" -eq 0 ]; then
        su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'\" | grep -q 1 || psql -c \"CREATE DATABASE \\\"$DB_NAME\\\" OWNER \\\"$DB_USER\\\";\"" >/dev/null 2>&1 || true
    else
        sudo -u postgres bash -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'\" | grep -q 1 || psql -c \"CREATE DATABASE \\\"$DB_NAME\\\" OWNER \\\"$DB_USER\\\";\"" >/dev/null 2>&1 || true
    fi

    run_pg_sql "GRANT ALL PRIVILEGES ON DATABASE \"$DB_NAME\" TO \"$DB_USER\";"
    echo -e "${GREEN}[OK] Database user '$DB_USER' and database '$DB_NAME' configured.${NC}"
fi

# Write .env file
echo -e "\n${BLUE}[5/6] Writing configuration to .env...${NC}"
cat <<EOF > .env
# TamozaLogger — Environment Variables
BOT_TOKEN=$BOT_TOKEN
DB_DSN=postgresql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME
DEFAULT_PREFIX=!
APPLICATION_ID=0
EOF
echo -e "${GREEN}[OK] .env file written successfully.${NC}"

# ------------------------------------------------------------------------------
# Step 6: Virtual Environment & Database Schema Setup
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[6/6] Setting up Python virtual environment and database schema...${NC}"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

./venv/bin/python3 -m pip install --upgrade pip --quiet
./venv/bin/python3 -m pip install -r requirements.txt --quiet
echo -e "${GREEN}[OK] Python virtual environment ready.${NC}"

# Apply database schema
./venv/bin/python3 database/setup_db.py

# ------------------------------------------------------------------------------
# Create start.sh & systemd service
# ------------------------------------------------------------------------------
cat <<'EOF' > start.sh
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "venv/bin/python3" ]; then
    echo "[ERROR] Virtual environment not found. Please run ./install.sh first."
    exit 1
fi

echo "==============================================================================="
echo "                          STARTING TAMOZA LOGGER                               "
echo "==============================================================================="
exec ./venv/bin/python3 bot.py
EOF

chmod +x start.sh
chmod +x install.sh
chmod +x service.sh 2>/dev/null || true

# Register systemd service
SERVICE_FILE="/etc/systemd/system/tamozalogger.service"
if command -v systemctl >/dev/null 2>&1; then
    CURRENT_USER="$(id -un)"
    $SUDO_CMD bash -c "cat <<EOF > $SERVICE_FILE
[Unit]
Description=TamozaLogger Discord Bot
After=network.target postgresql.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF"
    $SUDO_CMD systemctl daemon-reload || true
fi

echo -e "\n${GREEN}${BOLD}==============================================================================="
echo "                          INSTALLATION COMPLETED!                              "
echo "===============================================================================${NC}"
echo -e "\n${BOLD}How to manage the bot:${NC}"
echo -e "  • ${CYAN}./service.sh${NC}          (Interactive service manager: start, stop, logs, status)"
echo -e "  • ${CYAN}./start.sh${NC}            (Start manually in foreground)"
echo -e "  • ${CYAN}sudo systemctl start tamozalogger${NC} (Start 24/7 background service)"
echo -e "\n${CYAN}===============================================================================${NC}\n"
