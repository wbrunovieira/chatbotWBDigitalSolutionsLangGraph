# Status do Servidor Contabo - 17/01/2025

## 📊 Recursos do Servidor

### Hardware
- **CPU:** AMD EPYC (4 cores)
- **RAM:** 6GB
- **Disco:** 96GB SSD

### Uso Atual de Recursos
- **CPU:** < 1% utilização
- **RAM:** 343MB usados / 5.6GB livres (94% disponível)
- **Disco:** ~9GB usados / ~83GB livres (86% disponível)
- **Load Average:** 0.01 (servidor praticamente idle)

## 🚀 Aplicações Instaladas

### 1. ChatbotWB (Projeto Principal)
**Status:** Parcialmente ativo
- **Redis:** ✅ Rodando (porta 6379)
- **API FastAPI:** ⚠️ Container parado (pronto para reiniciar)
- **Nginx:** Configurado em chatbotwb.wbdigitalsolutions.com

**Componentes:**
- LangGraph para orquestração de fluxo
- Qdrant (vector database)
- Redis (cache com TTL de 7 dias)
- DeepSeek API (LLM)
- Suporte multi-idioma (PT-BR, EN, ES, IT)

### 2. Nextcloud
**Status:** Parcialmente ativo
- **MariaDB:** ✅ Rodando (porta 3306)
- **Redis:** ✅ Rodando (porta 6379)
- **App Principal:** ⚠️ Container parado
- **Nginx:** Configurado em nextcloud.wbdigitalsolutions.com

## 🐳 Docker

### Containers Ativos
```
CONTAINER ID   NAME              CPU %     MEM USAGE     STATUS
8b040fcdde09   wb_redis          0.38%     5.6MiB        Up 2 days
08004fc5267b   nextcloud-redis   0.41%     4.3MiB        Up 7 weeks
c9ce36330bfd   nextcloud-db      0.01%     108.4MiB      Up 7 weeks
```

### Containers Parados
- wb_fastapi (ChatbotWB API)
- nextcloud (App principal)

## 🌐 Nginx

### Sites Configurados
- chatbotwb.wbdigitalsolutions.com
- nextcloud.wbdigitalsolutions.com

## 📁 Estrutura de Diretórios

```
/
├── chatbotWB/      # Projeto do chatbot
├── nextcloud/      # Arquivos do Nextcloud
└── opt/            # Vazio (limpo)
```

## 🔧 Comandos Úteis

### Reiniciar ChatbotWB
```bash
cd /chatbotWB
docker-compose up -d
```

### Verificar logs
```bash
docker logs wb_fastapi
docker logs wb_redis
```

### Monitorar recursos
```bash
docker stats --no-stream
df -h
free -h
```

## 📝 Notas

- Servidor otimizado e limpo
- Amplo espaço disponível para novos projetos
- Todos os serviços desnecessários foram removidos
- Sistema pronto para escalar conforme necessidade