#!/usr/bin/env bash
# ==============================================================================
# TamozaLogger — One-Click Automated Linux Installer
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
echo "                TAMOZA LOGGER — AUTOMATED LINUX INSTALLER                      "
echo "==============================================================================="
echo -e "${NC}"

# ------------------------------------------------------------------------------
# Step 1: Detect User & Root Privileges
# ------------------------------------------------------------------------------
echo -e "${BLUE}[1/7] Checking user permissions...${NC}"
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
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

# ------------------------------------------------------------------------------
# Step 2: Detect Linux Distribution & Install System Packages
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[2/7] Detecting Linux distribution and installing system packages...${NC}"

if command -v apt-get >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Debian / Ubuntu based system detected.${NC}"
    $SUDO apt-get update -y
    $SUDO apt-get install -y python3 python3-pip python3-venv python3-dev \
        postgresql postgresql-contrib libpq-dev git curl build-essential
elif command -v dnf >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Fedora / RHEL / Rocky Linux detected.${NC}"
    $SUDO dnf install -y python3 python3-pip python3-devel \
        postgresql-server postgresql-contrib libpq-devel git curl gcc
    # Initialize DB on RHEL if needed
    if [ ! -d "/var/lib/pgsql/data" ] || [ -z "$(ls -A /var/lib/pgsql/data 2>/dev/null)" ]; then
        $SUDO postgresql-setup --initdb || true
    fi
elif command -v yum >/dev/null 2>&1; then
    echo -e "${CYAN}[*] CentOS / Amazon Linux detected.${NC}"
    $SUDO yum install -y python3 python3-pip python3-devel \
        postgresql-server postgresql-contrib git curl gcc
    if [ ! -d "/var/lib/pgsql/data" ] || [ -z "$(ls -A /var/lib/pgsql/data 2>/dev/null)" ]; then
        $SUDO postgresql-setup initdb || true
    fi
elif command -v pacman >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Arch Linux detected.${NC}"
    $SUDO pacman -Sy --noconfirm python python-pip postgresql git curl base-devel
    if [ ! -d "/var/lib/postgres/data" ] || [ -z "$(ls -A /var/lib/postgres/data 2>/dev/null)" ]; then
        $SUDO -u postgres initdb -D /var/lib/postgres/data || true
    fi
elif command -v apk >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Alpine Linux detected.${NC}"
    $SUDO apk add --no-cache python3 py3-pip py3-virtualenv python3-dev \
        postgresql postgresql-contrib git curl build-base
else
    echo -e "${YELLOW}[!] Warning: Unknown package manager. Please ensure Python 3, pip, venv, and PostgreSQL are installed.${NC}"
fi

# ------------------------------------------------------------------------------
# Step 3: Start and Enable PostgreSQL Service
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[3/7] Configuring PostgreSQL service...${NC}"

if command -v systemctl >/dev/null 2>&1; then
    $SUDO systemctl enable postgresql || true
    $SUDO systemctl start postgresql || true
    echo -e "${GREEN}[OK] PostgreSQL service started and enabled with systemd.${NC}"
elif command -v service >/dev/null 2>&1; then
    $SUDO service postgresql start || true
    echo -e "${GREEN}[OK] PostgreSQL service started.${NC}"
elif command -v rc-service >/dev/null 2>&1; then
    $SUDO rc-service postgresql start || true
    echo -e "${GREEN}[OK] PostgreSQL service started with OpenRC.${NC}"
fi

# ------------------------------------------------------------------------------
# Step 4: Configure PostgreSQL User & Database
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[4/7] Setting up PostgreSQL database user and permissions...${NC}"

DB_USER="tamoza"
DB_PASS="tamoza_password_2026"
DB_NAME="tamoza_logger"

# Create user and database via postgres superuser
$SUDO -u postgres psql -c "DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN
        CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASS' CREATEDB;
    ELSE
        ALTER ROLE $DB_USER WITH PASSWORD '$DB_PASS';
    END IF;
END
\$\$;" >/dev/null 2>&1 || true

$SUDO -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
    $SUDO -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" >/dev/null 2>&1 || true

$SUDO -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" >/dev/null 2>&1 || true
echo -e "${GREEN}[OK] Database '$DB_NAME' and user '$DB_USER' configured.${NC}"

# ------------------------------------------------------------------------------
# Step 5: Python Virtual Environment & Dependencies
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[5/7] Setting up Python virtual environment (venv)...${NC}"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}[OK] Created virtual environment in ./venv${NC}"
fi

# Activate and install packages
./venv/bin/python3 -m pip install --upgrade pip --quiet
./venv/bin/python3 -m pip install -r requirements.txt --quiet
echo -e "${GREEN}[OK] All Python dependencies installed successfully.${NC}"

# ------------------------------------------------------------------------------
# Step 6: Environment File (.env) Configuration
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[6/7] Configuring environment file (.env)...${NC}"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        sed -i "s|DB_DSN=.*|DB_DSN=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME|g" .env
        echo -e "${GREEN}[OK] Created .env from .env.example with pre-configured DB_DSN.${NC}"
    else
        cat <<EOF > .env
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
DB_DSN=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
DEFAULT_PREFIX=!
APPLICATION_ID=0
EOF
        echo -e "${GREEN}[OK] Created fresh .env file.${NC}"
    fi
    echo -e "${YELLOW}[!] IMPORTANT: Open .env and insert your Discord BOT_TOKEN.${NC}"
else
    echo -e "${GREEN}[OK] .env already exists.${NC}"
fi

# ------------------------------------------------------------------------------
# Step 7: Apply Database Schema
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[7/7] Initializing database schema...${NC}"
./venv/bin/python3 database/setup_db.py || true

# ------------------------------------------------------------------------------
# Create start.sh & optional systemd service
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

# Optional systemd service generator
SERVICE_FILE="/etc/systemd/system/tamozalogger.service"
if command -v systemctl >/dev/null 2>&1; then
    CURRENT_USER="$(id -un)"
    $SUDO bash -c "cat <<EOF > $SERVICE_FILE
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
    $SUDO systemctl daemon-reload || true
    echo -e "\n${CYAN}[*] Registered systemd service: tamozalogger.service${NC}"
fi

echo -e "\n${GREEN}${BOLD}==============================================================================="
echo "                          INSTALLATION COMPLETE!                               "
echo "===============================================================================${NC}"
echo -e "\n${BOLD}Next steps:${NC}"
echo -e "  1. Edit ${CYAN}.env${NC} and set your ${BOLD}BOT_TOKEN${NC}:"
echo -e "     ${YELLOW}nano .env${NC}"
echo -e "  2. Start the bot manually:"
echo -e "     ${CYAN}./start.sh${NC}"
if [ -f "$SERVICE_FILE" ]; then
    echo -e "  3. Or run it 24/7 in the background with systemd:"
    echo -e "     ${CYAN}sudo systemctl start tamozalogger${NC}"
    echo -e "     ${CYAN}sudo systemctl enable tamozalogger${NC}"
    echo -e "     ${CYAN}sudo systemctl status tamozalogger${NC}"
fi
echo -e "\n${CYAN}===============================================================================${NC}\n"
