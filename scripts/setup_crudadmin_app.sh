#!/bin/bash
#
# CRUDAdmin Application Setup Script
# Creates a new FastAPI application with CRUDAdmin pre-configured
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  CRUDAdmin Application Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Get app name
read -p "Enter your application name (e.g., myapp): " APP_NAME

if [ -z "$APP_NAME" ]; then
    echo -e "${RED}Error: Application name is required${NC}"
    exit 1
fi

# Sanitize app name (lowercase, replace spaces with underscores)
APP_NAME=$(echo "$APP_NAME" | tr '[:upper:]' '[:lower:]' | tr ' ' '_' | tr '-' '_')
APP_DIR="${APP_NAME}"

echo -e "${GREEN}Creating application: ${APP_NAME}${NC}"

# Check if directory exists
if [ -d "$APP_DIR" ]; then
    echo -e "${RED}Error: Directory '$APP_DIR' already exists${NC}"
    exit 1
fi

# Detect OS
detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    elif [ -f /etc/debian_version ]; then
        OS="debian"
    elif [ -f /etc/redhat-release ]; then
        OS="rhel"
    else
        OS=$(uname -s | tr '[:upper:]' '[:lower:]')
    fi
    echo $OS
}

OS=$(detect_os)
echo -e "${YELLOW}Detected OS: ${OS}${NC}"

# Check Python version
check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
        PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

        if [ "$PYTHON_MAJOR" -ge 3 ] && [ "$PYTHON_MINOR" -ge 10 ]; then
            echo -e "${GREEN}Python $PYTHON_VERSION found${NC}"
            return 0
        else
            echo -e "${RED}Python 3.10+ required, found $PYTHON_VERSION${NC}"
            return 1
        fi
    else
        echo -e "${RED}Python3 not found${NC}"
        return 1
    fi
}

# Install Python if needed
install_python() {
    echo -e "${YELLOW}Installing Python...${NC}"
    case $OS in
        ubuntu|debian)
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip
            ;;
        fedora)
            sudo dnf install -y python3 python3-pip
            ;;
        rhel|centos|rocky|almalinux)
            sudo yum install -y python3 python3-pip
            ;;
        arch|manjaro)
            sudo pacman -S --noconfirm python python-pip
            ;;
        *)
            echo -e "${RED}Unsupported OS for automatic Python installation${NC}"
            echo "Please install Python 3.10+ manually"
            exit 1
            ;;
    esac
}

# Check and install venv support
ensure_venv() {
    echo -e "${YELLOW}Checking venv support...${NC}"

    # Try to create a test venv
    TEST_VENV="/tmp/test_venv_$$"
    if python3 -m venv "$TEST_VENV" 2>/dev/null; then
        rm -rf "$TEST_VENV"
        echo -e "${GREEN}venv support available${NC}"
        return 0
    fi

    echo -e "${YELLOW}Installing venv support...${NC}"
    case $OS in
        ubuntu|debian)
            sudo apt-get update
            sudo apt-get install -y python3-venv python3-dev build-essential
            ;;
        fedora)
            sudo dnf install -y python3-devel gcc
            ;;
        rhel|centos|rocky|almalinux)
            sudo yum install -y python3-devel gcc
            ;;
        arch|manjaro)
            # venv is included with python on Arch
            sudo pacman -S --noconfirm base-devel
            ;;
        *)
            echo -e "${RED}Please install python3-venv manually${NC}"
            exit 1
            ;;
    esac

    # Verify venv works now
    if python3 -m venv "$TEST_VENV" 2>/dev/null; then
        rm -rf "$TEST_VENV"
        echo -e "${GREEN}venv support installed${NC}"
    else
        echo -e "${RED}Failed to install venv support${NC}"
        exit 1
    fi
}

# Check Python
if ! check_python; then
    install_python
    check_python || exit 1
fi

# Ensure venv support
ensure_venv

# Create project directory
echo -e "${YELLOW}Creating project structure...${NC}"
mkdir -p "$APP_DIR"
cd "$APP_DIR"

# Create virtual environment
echo -e "${YELLOW}Creating virtual environment...${NC}"
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
echo -e "${YELLOW}Installing dependencies...${NC}"
pip install fastapi uvicorn sqlalchemy[asyncio] aiosqlite alembic pydantic python-dotenv
pip install crudadmin

# Create project structure
mkdir -p app/models app/schemas templates static migrations

# Create .env file
cat > .env << EOF
# Application Settings
APP_NAME="${APP_NAME}"
SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
DEBUG=true

# Database
DATABASE_URL="sqlite+aiosqlite:///./${APP_NAME}.db"

# Admin credentials (change in production!)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
EOF

# Create main.py
APP_TITLE=$(echo "$APP_NAME" | sed 's/_/ /g' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) tolower(substr($i,2));}1')
cat > main.py << 'MAINPY'
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from crudadmin import CRUDAdmin

from app.models import Base
# Import your models here
# from app.models.user import User
# from app.schemas.user import UserCreate, UserUpdate

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "My App")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

# Database setup
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session():
    async with async_session() as session:
        yield session


# Create admin interface
admin = CRUDAdmin(
    session=get_session,
    SECRET_KEY=SECRET_KEY,
    initial_admin={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    secure_cookies=False,  # Set True in production with HTTPS
)

# Add your model views here
# admin.add_view(
#     model=User,
#     create_schema=UserCreate,
#     update_schema=UserUpdate,
#     allowed_actions={"view", "create", "update", "delete"}
# )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Initialize admin
    await admin.initialize()
    yield


# Create FastAPI app
app = FastAPI(
    title=APP_NAME,
    lifespan=lifespan,
)

# Mount admin interface
app.mount("/admin", admin.app)


@app.get("/")
async def root():
    return {"message": f"Welcome to {APP_NAME}", "admin": "/admin"}
MAINPY

# Update APP_NAME in main.py
sed -i "s/My App/${APP_TITLE}/g" main.py

# Create base model
cat > app/models/__init__.py << 'MODELSINIT'
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import your models here to register them with Base
# from .user import User
MODELSINIT

# Create example model
cat > app/models/example.py << 'EXAMPLEMODEL'
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.sql import func

from . import Base


class Example(Base):
    """Example model - replace with your own models"""
    __tablename__ = "examples"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
EXAMPLEMODEL

# Create example schema
cat > app/schemas/__init__.py << 'SCHEMASINIT'
# Import your schemas here
# from .user import UserCreate, UserUpdate
SCHEMASINIT

cat > app/schemas/example.py << 'EXAMPLESCHEMA'
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ExampleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_active: bool = True


class ExampleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
EXAMPLESCHEMA

# Create alembic.ini
cat > alembic.ini << 'ALEMBICINI'
[alembic]
script_location = migrations
prepend_sys_path = .
sqlalchemy.url = sqlite:///./app.db

[post_write_hooks]

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
ALEMBICINI

# Initialize alembic
alembic init migrations 2>/dev/null || true

# Update migrations/env.py for async
cat > migrations/env.py << 'ENVPY'
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
ENVPY

# Create .gitignore
cat > .gitignore << 'GITIGNORE'
# Python
__pycache__/
*.pyc
*.pyo
venv/
.venv/
env/

# Environment
.env
.env.*

# Database
*.db
*.sqlite
*.sqlite3
crudadmin_data/

# IDE
.vscode/
.idea/
*.swp

# Logs
*.log

# OS
.DS_Store
GITIGNORE

# Create requirements.txt
pip freeze > requirements.txt

echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "Your ${BLUE}${APP_NAME}${NC} application has been created."
echo
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. cd ${APP_DIR}"
echo "  2. source venv/bin/activate"
echo "  3. Edit .env to configure your settings"
echo "  4. Add your models in app/models/"
echo "  5. Add your schemas in app/schemas/"
echo "  6. Register models in main.py with admin.add_view()"
echo "  7. Run: uvicorn main:app --reload"
echo "  8. Visit: http://localhost:8000/admin"
echo
echo -e "${YELLOW}Default admin credentials:${NC}"
echo "  Username: admin"
echo "  Password: admin123"
echo
echo -e "${RED}Remember to change the admin password in production!${NC}"
