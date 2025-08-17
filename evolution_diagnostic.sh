#!/bin/bash

# Evolution API Diagnostic Script
# Execute este script NO SERVIDOR onde a Evolution está rodando

echo "==========================================="
echo "🔍 DIAGNÓSTICO EVOLUTION API"
echo "==========================================="
echo ""

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Verificar containers
echo "1️⃣ VERIFICANDO CONTAINERS..."
echo "-------------------------------------------"
docker ps | grep evolution
echo ""

# 2. Verificar logs recentes
echo "2️⃣ ÚLTIMOS LOGS DA EVOLUTION API..."
echo "-------------------------------------------"
docker logs --tail 20 evolution_api 2>&1 | grep -E "(ERROR|WARN|connected|disconnected|timeout)"
echo ""

# 3. Verificar uso de recursos
echo "3️⃣ USO DE RECURSOS..."
echo "-------------------------------------------"
docker stats --no-stream evolution_api evolution_redis evolution_postgres
echo ""

# 4. Verificar conectividade interna
echo "4️⃣ TESTE DE CONECTIVIDADE INTERNA..."
echo "-------------------------------------------"
docker exec evolution_api curl -s http://localhost:8080/health || echo -e "${RED}❌ Health check falhou${NC}"
echo ""

# 5. Verificar Redis
echo "5️⃣ VERIFICANDO REDIS..."
echo "-------------------------------------------"
docker exec evolution_redis redis-cli ping || echo -e "${RED}❌ Redis não responde${NC}"
docker exec evolution_redis redis-cli info clients | grep connected_clients
echo ""

# 6. Verificar Postgres
echo "6️⃣ VERIFICANDO POSTGRES..."
echo "-------------------------------------------"
docker exec evolution_postgres psql -U evolution -c "SELECT COUNT(*) as total_instances FROM instances;" 2>/dev/null || echo -e "${YELLOW}⚠️ Não foi possível conectar ao Postgres${NC}"
echo ""

# 7. Verificar portas
echo "7️⃣ VERIFICANDO PORTAS..."
echo "-------------------------------------------"
netstat -tlnp | grep -E "(8080|6379|5432)" 2>/dev/null || ss -tlnp | grep -E "(8080|6379|5432)"
echo ""

# 8. Verificar memória e disco
echo "8️⃣ MEMÓRIA E DISCO..."
echo "-------------------------------------------"
free -h
df -h | grep -E "(/$|/var/lib/docker)"
echo ""

# 9. Tentar reiniciar com logs
echo "==========================================="
echo "🔧 AÇÕES RECOMENDADAS:"
echo "==========================================="
echo ""
echo "Se os testes acima falharam, execute:"
echo ""
echo -e "${YELLOW}# 1. Reiniciar apenas Evolution API:${NC}"
echo "docker restart evolution_api"
echo ""
echo -e "${YELLOW}# 2. Reiniciar todo o stack:${NC}"
echo "docker restart evolution_api evolution_redis evolution_postgres"
echo ""
echo -e "${YELLOW}# 3. Ver logs em tempo real:${NC}"
echo "docker logs -f evolution_api"
echo ""
echo -e "${YELLOW}# 4. Recreate completo (CUIDADO - perde sessões):${NC}"
echo "cd /caminho/evolution && docker-compose down && docker-compose up -d"
echo ""
echo -e "${YELLOW}# 5. Limpar cache Redis se necessário:${NC}"
echo "docker exec evolution_redis redis-cli FLUSHALL"
echo ""
echo "==========================================="

# 10. Testar API diretamente
echo "🔌 TESTE DIRETO DA API..."
echo "-------------------------------------------"
API_KEY="63473E9C4DD7-447D-A046-CB835D1DD82E"

# Teste local no servidor
echo "Testando localhost:8080..."
curl -s -w "\nStatus: %{http_code} - Time: %{time_total}s\n" \
  http://localhost:8080/instance/fetchInstances \
  -H "apikey: $API_KEY" | head -5

echo ""
echo "==========================================="
echo "✅ DIAGNÓSTICO COMPLETO"
echo "==========================================="