#!/bin/bash
# Firecrawl Self-Hosted Health Check
# Uso: ~/firecrawl/healthcheck.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Firecrawl Self-Hosted — Health Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Containers
echo "📦 Containers:"
docker ps --filter "name=firecrawl" --format '  {{.Names}}: {{.Status}}' 2>/dev/null || echo "  ${RED}Nenhum container rodando${NC}"

API_STATUS=$(docker ps --filter "name=firecrawl-api-1" --format '{{.Status}}' 2>/dev/null)
if [ -z "$API_STATUS" ]; then
    echo ""
    echo "${RED}❌ firecrawl-api-1 está DOWN${NC}"
    echo "   → cd ~/firecrawl && docker compose up -d"
    exit 1
fi
echo ""

# 2. API
echo "🔌 API (localhost:3002):"
API_RESPONSE=$(curl -s --max-time 10 -X POST http://localhost:3002/v1/scrape \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local-dev-key" \
  -d '{"url":"https://example.com","formats":["markdown"],"onlyMainContent":true}' 2>&1)

if echo "$API_RESPONSE" | grep -q '"success":true'; then
    echo -e "  ${GREEN}✅ Scrape OK${NC}"
else
    echo -e "  ${RED}❌ Scrape falhou${NC}"
    echo "  Resposta: $(echo $API_RESPONSE | head -c 200)"
fi
echo ""

# 3. MCP Bridge
echo "🔗 MCP Bridge:"
MCP_COUNT=$(ps aux | grep -c '[f]irecrawl-mcp' 2>/dev/null || echo 0)
if [ "$MCP_COUNT" -ge 2 ]; then
    echo -e "  ${GREEN}✅ $MCP_COUNT processos rodando${NC}"
else
    echo -e "  ${RED}❌ Apenas $MCP_COUNT processo(s)${NC}"
    echo "   → systemctl --user restart hermes-agent"
fi
echo ""

# 4. LLM (Ollama)
echo "🤖 LLM (Ollama):"
OLLAMA_STATUS=$(systemctl --user is-active ollama 2>/dev/null || echo "inactive")
if [ "$OLLAMA_STATUS" = "active" ]; then
    echo -e "  ${GREEN}✅ Ollama ativo${NC}"
else
    echo -e "  ${YELLOW}⚠️  Ollama $OLLAMA_STATUS${NC}"
fi

MODEL=$(grep MODEL_NAME ~/firecrawl/.env 2>/dev/null | cut -d'"' -f2)
echo "  Modelo: $MODEL"
echo ""

# 5. Restart Policy
echo "🔄 Restart Policy:"
RESTART_COUNT=$(grep -c 'restart: always' ~/firecrawl/docker-compose.yaml 2>/dev/null || echo 0)
if [ "$RESTART_COUNT" -ge 5 ]; then
    echo -e "  ${GREEN}✅ $RESTART_COUNT serviços com restart: always${NC}"
else
    echo -e "  ${RED}❌ Apenas $RESTART_COUNT/5 serviços com restart: always${NC}"
fi
echo ""

# 6. Logs recentes
echo "📋 Últimos logs (erros):"
docker logs firecrawl-api-1 --tail 20 2>&1 | grep -iE 'error|fatal|crash|warn' | tail -5 || echo "  (sem erros recentes)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
