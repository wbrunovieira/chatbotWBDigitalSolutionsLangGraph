# Ansible Deployment for WB Digital Solutions Chatbot

Este diretório contém a automação Ansible para deploy do chatbot no servidor de produção.

## Servidor de Produção

- **IP**: 45.90.123.190
- **Domínio**: chatbot.wbdigitalsolutions.com
- **Portas utilizadas**:
  - 8001: Aplicação Chatbot
  - 6333: Qdrant (Vector Database)
  - 6380: Redis (Cache do Chatbot)

## Containers já em execução no servidor

- n8n (porta 5678)
- PostgreSQL para n8n (porta 5432)
- Redis para Nextcloud (porta 6379)
- MariaDB para Nextcloud (porta 3306)

## Pré-requisitos

1. Instalar Ansible:
```bash
pip install ansible
```

2. Configurar as credenciais em `inventory.ini`:
   - `deepseek_api_key`: Sua chave API do DeepSeek
   - `qdrant_api_key`: Chave API para o Qdrant (será gerada automaticamente se não fornecida)
   - `redis_password`: Senha do Redis (será gerada automaticamente se não fornecida)

## Deploy

### Método 1: Script automatizado

```bash
cd ansible
./deploy.sh
```

### Método 2: Comando direto

```bash
cd ansible
ansible-playbook -i inventory.ini playbook.yml
```

## O que o deploy faz

1. **Verifica o ambiente**: Docker e Docker Compose
2. **Cria estrutura de diretórios**: `/root/chatbot`
3. **Configura rede Docker**: Usa a rede `wb_network` existente
4. **Deploy dos containers**:
   - Qdrant (vector database)
   - Redis (cache)
   - Aplicação Chatbot
5. **Configura Nginx** (se SSL habilitado)
6. **Instala certificado SSL** com Certbot

## Verificar o status após deploy

SSH no servidor e execute:

```bash
# Ver todos os containers do chatbot
docker ps | grep chatbot

# Ver logs da aplicação
docker logs chatbot_app

# Ver logs do Qdrant
docker logs chatbot_qdrant

# Ver logs do Redis
docker logs chatbot_redis

# Testar a aplicação
curl http://localhost:8001/health
```

## Estrutura de arquivos

```
ansible/
├── inventory.ini           # Configuração do servidor e variáveis
├── playbook.yml           # Playbook principal de deploy
├── deploy.sh             # Script de deploy automatizado
├── templates/
│   ├── docker-compose.prod.yml.j2  # Template do docker-compose
│   ├── env.j2                      # Template das variáveis de ambiente
│   └── nginx-chatbot.conf.j2      # Template de configuração Nginx
└── README.md             # Esta documentação
```

## Rollback

Para fazer rollback em caso de problemas:

```bash
# SSH no servidor
ssh root@45.90.123.190

# Parar os containers do chatbot
cd /root/chatbot
docker-compose down

# Remover os containers (mantém os volumes)
docker-compose rm -f

# Para remover completamente (incluindo dados)
docker-compose down -v
```

## Troubleshooting

### Conflito de portas
Se houver conflito de portas, edite `inventory.ini` e ajuste:
- `app_port`: Porta da aplicação (padrão: 8001)
- `qdrant_port`: Porta do Qdrant (padrão: 6333)
- `redis_port`: Porta do Redis (padrão: 6380)

### Erro de permissão SSH
Certifique-se de ter a chave SSH configurada para o servidor.

### Container não inicia
Verifique os logs:
```bash
docker logs chatbot_app
```

## Manutenção

### Atualizar a aplicação
```bash
./deploy.sh
```

### Backup dos dados
```bash
# No servidor
cd /root/chatbot
tar -czf backup-$(date +%Y%m%d).tar.gz volumes/
```

### Monitorar recursos
```bash
docker stats chatbot_app chatbot_qdrant chatbot_redis
```