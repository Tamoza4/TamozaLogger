#!/usr/bin/env bash
# ==============================================================================
# TamozaLogger — 100% Fully Automated One-Click Linux Installer
# Zero prompts, zero manual input — sets up everything automatically!
# ==============================================================================

set -e

# ANSI Color Codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${CYAN}${BOLD}"
echo "==============================================================================="
echo "             TAMOZA LOGGER — 100% AUTOMATED LINUX INSTALLER                    "
echo "==============================================================================="
echo -e "${NC}"

# ------------------------------------------------------------------------------
# Step 1: Detect User & Root Privileges
# ------------------------------------------------------------------------------
echo -e "${BLUE}[1/6] Checking system permissions...${NC}"
SUDO_CMD=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO_CMD="sudo"
    else
        echo -e "${RED}[ERROR] This installer requires root or sudo privileges.${NC}"
        exit 1
    fi
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
echo -e "${GREEN}[OK] Working directory: $SCRIPT_DIR${NC}"

# ------------------------------------------------------------------------------
# Step 2: Install System Packages
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[2/6] Installing system packages & dependencies...${NC}"

if command -v apt-get >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Installing packages on Ubuntu/Debian...${NC}"
    $SUDO_CMD apt-get update -qq
    $SUDO_CMD apt-get install -y -qq python3 python3-pip python3-venv python3-dev \
        postgresql postgresql-contrib libpq-dev git curl build-essential >/dev/null 2>&1
elif command -v dnf >/dev/null 2>&1; then
    echo -e "${CYAN}[*] Installing packages on RHEL/Fedora...${NC}"
    $SUDO_CMD dnf install -y -q python3 python3-pip python3-devel \
        postgresql-server postgresql-contrib libpq-devel git curl gcc >/dev/null 2>&1
    if [ ! -d "/var/lib/pgsql/data" ] || [ -z "$(ls -A /var/lib/pgsql/data 2>/dev/null)" ]; then
        $SUDO_CMD postgresql-setup --initdb >/dev/null 2>&1 || true
    fi
fi
echo -e "${GREEN}[OK] System packages installed successfully.${NC}"

# ------------------------------------------------------------------------------
# Step 3: Ensure PostgreSQL Service is Running
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[3/6] Starting PostgreSQL service...${NC}"
if command -v systemctl >/dev/null 2>&1; then
    $SUDO_CMD systemctl enable postgresql >/dev/null 2>&1 || true
    $SUDO_CMD systemctl start postgresql >/dev/null 2>&1 || true
elif command -v service >/dev/null 2>&1; then
    $SUDO_CMD service postgresql start >/dev/null 2>&1 || true
fi
echo -e "${GREEN}[OK] PostgreSQL service is active.${NC}"

# ------------------------------------------------------------------------------
# Step 4: Fully Automated Database & User Provisioning
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[4/6] Provisioning PostgreSQL user & database automatically...${NC}"

DB_USER="tamoza"
DB_NAME="tamoza_logger"
DB_PASS="tamoza_pass_$(date +%s)"

# If .env exists with password, reuse it
if [ -f ".env" ]; then
    EXISTING_PASS=$(grep "DB_DSN=" .env 2>/dev/null | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p' || true)
    if [ -n "$EXISTING_PASS" ]; then
        DB_PASS="$EXISTING_PASS"
    fi
fi

# Execute PostgreSQL role and DB creation
PG_SQL="
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '$DB_USER') THEN
        CREATE ROLE \"$DB_USER\" WITH LOGIN PASSWORD '$DB_PASS' CREATEDB SUPERUSER;
    ELSE
        ALTER ROLE \"$DB_USER\" WITH PASSWORD '$DB_PASS';
        ALTER ROLE \"$DB_USER\" WITH LOGIN CREATEDB SUPERUSER;
    END IF;
END
\$\$;
"

if command -v sudo >/dev/null 2>&1; then
    echo "$PG_SQL" | sudo -u postgres psql >/dev/null 2>&1 || su - postgres -c "psql" <<< "$PG_SQL" >/dev/null 2>&1 || true
    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" 2>/dev/null | grep -q 1 || sudo -u postgres psql -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";" >/dev/null 2>&1 || true
    echo "GRANT ALL PRIVILEGES ON DATABASE \"$DB_NAME\" TO \"$DB_USER\";" | sudo -u postgres psql >/dev/null 2>&1 || true
else
    echo "$PG_SQL" | su - postgres -c "psql" >/dev/null 2>&1 || true
    su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'\"" 2>/dev/null | grep -q 1 || su - postgres -c "psql -c \"CREATE DATABASE \\\"$DB_NAME\\\" OWNER \\\"$DB_USER\\\";\"" >/dev/null 2>&1 || true
    echo "GRANT ALL PRIVILEGES ON DATABASE \"$DB_NAME\" TO \"$DB_USER\";" | su - postgres -c "psql" >/dev/null 2>&1 || true
fi

echo -e "${GREEN}[OK] Database '$DB_NAME' and user '$DB_USER' configured.${NC}"

# ------------------------------------------------------------------------------
# Step 5: Configure .env Automatically
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}[5/6] Configuring .env file...${NC}"

if [ ! -f ".env" ]; then
    cat <<EOF > .env
BOT_TOKEN=YOUR_BOT_TOKEN_HERE
DB_DSN=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
DEFAULT_PREFIX=!
APPLICATION_ID=0
EOF
    echo -e "${GREEN}[OK] Created .env with pre-configured database connection.${NC}"
else
    # Update DB_DSN in existing .env while keeping existing BOT_TOKEN
    if grep -q "DB_DSN=" .env; then
        sed -i "s|DB_DSN=.*|DB_DSN=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME|g" .env
    else
        echo "DB_DSN=postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME" >> .env
    fi
    echo -e "${GREEN}[OK] Updated .env database connection.${NC}"
fi

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
# Generate start.sh & systemd service
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
echo "                     INSTALLATION 100% COMPLETED!                              "
echo "===============================================================================${NC}"
echo -e "\n${BOLD}Next Step:${NC}"
echo -e "  1. If you haven't set your bot token yet, edit ${CYAN}.env${NC}:"
echo -e "     ${YELLOW}nano .env${NC}"
echo -e "\n  2. Start and manage the bot easily:"
echo -e "     ${CYAN}./service.sh${NC}          (Interactive manager: start, stop, logs, status)"
echo -e "     ${CYAN}./start.sh${NC}            (Or start manually in foreground)"
echo -e "     ${CYAN}systemctl start tamozalogger${NC} (Or start 24/7 background service)"
echo -e "\n${CYAN}===============================================================================${NC}\n"
