#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# DialogMesh — One-click Docker Startup Script
# ═══════════════════════════════════════════════════════════════════════════════
#  Usage: ./scripts/run.sh [build|up|down|restart|logs|test|shell]
#  Defaults to "up" if no argument is provided.
# ───────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
PROJECT_NAME="dialogmesh"
COMPOSE_FILE="docker-compose.yml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ── Helpers ───────────────────────────────────────────────────────────────────
log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC}  $*"; }

# ── Docker Check ────────────────────────────────────────────────────────────
check_docker() {
    log_step "Checking Docker environment..."

    if ! command -v docker &>/dev/null; then
        log_error "Docker is not installed. Please install Docker Desktop."
        log_error "  Windows: https://docs.docker.com/desktop/install/windows/"
        log_error "  macOS  : https://docs.docker.com/desktop/install/mac/"
        log_error "  Linux  : https://docs.docker.com/engine/install/"
        exit 1
    fi

    if ! docker info &>/dev/null; then
        log_error "Docker daemon is not running. Please start Docker Desktop or the Docker service."
        exit 1
    fi

    # Detect docker compose (legacy vs modern plugin)
    if docker compose version &>/dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &>/dev/null; then
        DOCKER_COMPOSE="docker-compose"
    else
        log_error "Docker Compose is not installed."
        exit 1
    fi

    log_info "Docker is ready. Using: ${DOCKER_COMPOSE}"
}

# ── Build ─────────────────────────────────────────────────────────────────────
do_build() {
    log_step "Building DialogMesh image..."
    cd "${PROJECT_ROOT}"
    ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" build
    log_info "Build complete."
}

# ── Up ────────────────────────────────────────────────────────────────────────
do_up() {
    log_step "Starting DialogMesh services..."
    cd "${PROJECT_ROOT}"

    # Ensure data directory exists for volume bind
    mkdir -p "${PROJECT_ROOT}/data"
    mkdir -p "${PROJECT_ROOT}/config"

    ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" up -d

    log_info "DialogMesh is running."
    echo ""
    echo -e "  ${BLUE}API Health:${NC} http://localhost:8000/health"
    echo -e "  ${BLUE}API Docs:  ${NC} http://localhost:8000/docs"
    echo -e "  ${BLUE}OpenAPI:   ${NC} http://localhost:8000/redoc"
    echo -e "  ${BLUE}WebSocket: ${NC} ws://localhost:8000/ws/{session_id}"
    echo ""
    echo -e "  ${YELLOW}Tip:${NC} Run './scripts/run.sh logs' to tail logs."
}

# ── Down ──────────────────────────────────────────────────────────────────────
do_down() {
    log_step "Stopping DialogMesh services..."
    cd "${PROJECT_ROOT}"
    ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" down
    log_info "Services stopped."
}

# ── Restart ───────────────────────────────────────────────────────────────────
do_restart() {
    log_step "Restarting DialogMesh services..."
    do_down
    do_up
}

# ── Logs ──────────────────────────────────────────────────────────────────────
do_logs() {
    cd "${PROJECT_ROOT}"
    ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" logs -f app
}

# ── Test ──────────────────────────────────────────────────────────────────────
do_test() {
    log_step "Running tests inside container..."
    cd "${PROJECT_ROOT}"
    ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" exec app pytest tests/ -v --tb=short
}

# ── Shell ─────────────────────────────────────────────────────────────────────
do_shell() {
    cd "${PROJECT_ROOT}"
    ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" exec app /bin/bash
}

# ── Status ────────────────────────────────────────────────────────────────────
do_status() {
    cd "${PROJECT_ROOT}"
    ${DOCKER_COMPOSE} -f "${COMPOSE_FILE}" ps
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    check_docker

    case "${1:-up}" in
        build)
            do_build
            ;;
        up|start)
            do_up
            ;;
        down|stop)
            do_down
            ;;
        restart)
            do_restart
            ;;
        logs)
            do_logs
            ;;
        test)
            do_test
            ;;
        shell|bash)
            do_shell
            ;;
        status|ps)
            do_status
            ;;
        *)
            echo "Usage: $0 [build|up|down|restart|logs|test|shell|status]"
            echo ""
            echo "Commands:"
            echo "  build    Build the Docker image"
            echo "  up       Start services (default)"
            echo "  down     Stop services"
            echo "  restart  Restart services"
            echo "  logs     Tail application logs"
            echo "  test     Run pytest inside the container"
            echo "  shell    Open a bash shell in the app container"
            echo "  status   Show container status"
            exit 1
            ;;
    esac
}

main "$@"
