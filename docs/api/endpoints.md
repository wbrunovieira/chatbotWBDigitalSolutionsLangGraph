# API Documentation - WB Digital Solutions Chatbot

## Base URL
- **Development**: `http://localhost:8000`
- **Production**: `https://chatbot.wbdigitalsolutions.com`

## Authentication
No authentication required for current endpoints.

---

## Endpoints

### 1. Health Check
Check if the API is running and healthy.

**Endpoint**: `GET /health`

**Response**:
```json
{
  "status": "healthy"
}
```

**Status Codes**:
- `200 OK`: Service is healthy
- `503 Service Unavailable`: Service is down

**Example**:
```bash
curl -X GET https://chatbot.wbdigitalsolutions.com/health
```

---

### 2. Chat Message
Send a message to the chatbot and receive a response.

**Endpoint**: `POST /chat`

**Request Body**:
```json
{
  "message": "string (required)",
  "user_id": "string (optional, default: 'anon')",
  "language": "string (optional, default: 'pt-BR')",
  "current_page": "string (optional, default: '/')",
  "page_url": "string (optional)",
  "timestamp": "string (optional)"
}
```

**Supported Languages**:
- `pt-BR`: Portuguese (Brazil)
- `en-US`: English
- `es-ES`: Spanish
- `it-IT`: Italian

**Response**:
```json
{
  "raw_response": "string",
  "revised_response": "string",
  "response_parts": ["string"],
  "detected_intent": "string",
  "final_step": "string",
  "language_used": "string",
  "context_page": "string",
  "is_greeting": boolean,
  "cached": boolean,
  "cache_type": "string (optional)"
}
```

**Response Fields**:
- `raw_response`: Original response from LLM
- `revised_response`: Formatted and optimized response
- `response_parts`: Response split into natural parts for UI display
- `detected_intent`: Detected user intent (greeting, services_inquiry, quote_request, etc.)
- `final_step`: Last processing step in the workflow
- `language_used`: Language used for the response
- `context_page`: Current page context
- `is_greeting`: Whether the message is a greeting
- `cached`: Whether response was served from cache
- `cache_type`: Type of cache hit ("pattern_match" or "redis")

**Status Codes**:
- `200 OK`: Success
- `400 Bad Request`: Invalid request body
- `500 Internal Server Error`: Processing error

**Examples**:

#### Example 1: Simple Greeting
```bash
curl -X POST https://chatbot.wbdigitalsolutions.com/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Olá, bom dia!",
    "user_id": "user123",
    "language": "pt-BR"
  }'
```

**Response**:
```json
{
  "raw_response": "Olá! Bom dia! 😊 Eu sou o assistente virtual da WB Digital Solutions...",
  "revised_response": "Olá! Bom dia! 😊 Eu sou o assistente virtual da WB Digital Solutions. Estamos aqui para transformar suas ideias em soluções digitais! Como posso ajudar você hoje?",
  "response_parts": [
    "Olá! Bom dia! 😊 Eu sou o assistente virtual da WB Digital Solutions.",
    "Estamos aqui para transformar suas ideias em soluções digitais!",
    "Como posso ajudar você hoje?"
  ],
  "detected_intent": "greeting",
  "final_step": "greeting_response",
  "language_used": "pt-BR",
  "context_page": "/",
  "is_greeting": true,
  "cached": false
}
```

#### Example 2: Services Inquiry
```bash
curl -X POST https://chatbot.wbdigitalsolutions.com/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quais serviços vocês oferecem?",
    "current_page": "/services"
  }'
```

**Response**:
```json
{
  "raw_response": "A WB Digital Solutions oferece diversos serviços...",
  "revised_response": "Oferecemos 3 principais soluções:\n\n🌐 **Sites & E-commerce**: Desenvolvimento de sites modernos e lojas virtuais\n⚙️ **Automação**: Integração de sistemas e processos automatizados\n🤖 **IA & Machine Learning**: Chatbots e análise de dados\n\nQual área te interessa mais?",
  "response_parts": [
    "Oferecemos 3 principais soluções:",
    "🌐 **Sites & E-commerce**: Desenvolvimento de sites modernos e lojas virtuais",
    "⚙️ **Automação**: Integração de sistemas e processos automatizados",
    "🤖 **IA & Machine Learning**: Chatbots e análise de dados",
    "Qual área te interessa mais?"
  ],
  "detected_intent": "services_inquiry",
  "final_step": "revision",
  "language_used": "pt-BR",
  "context_page": "/services",
  "is_greeting": false,
  "cached": false
}
```

#### Example 3: Quote Request
```bash
curl -X POST https://chatbot.wbdigitalsolutions.com/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Preciso de um orçamento para um site",
    "user_id": "client456",
    "current_page": "/websites"
  }'
```

**Response**:
```json
{
  "raw_response": "Perfeito! Vamos preparar um orçamento personalizado...",
  "revised_response": "Perfeito! Vamos preparar um orçamento personalizado. Preciso de algumas informações:\n\n1. Tipo de site (institucional, e-commerce, blog)?\n2. Quantas páginas aproximadamente?\n3. Precisa de funcionalidades especiais?\n\nOu se preferir, clique no botão 'Solicitar Orçamento' para preencher nosso formulário completo.",
  "response_parts": [
    "Perfeito! Vamos preparar um orçamento personalizado. Preciso de algumas informações:",
    "1. Tipo de site (institucional, e-commerce, blog)?",
    "2. Quantas páginas aproximadamente?",
    "3. Precisa de funcionalidades especiais?",
    "Ou se preferir, clique no botão 'Solicitar Orçamento' para preencher nosso formulário completo."
  ],
  "detected_intent": "quote_request",
  "final_step": "revision",
  "language_used": "pt-BR",
  "context_page": "/websites",
  "is_greeting": false,
  "cached": false
}
```

#### Example 4: Cached Response
```bash
curl -X POST https://chatbot.wbdigitalsolutions.com/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "oi"
  }'
```

**Response**:
```json
{
  "raw_response": "Olá! 👋 Bem-vindo à WB Digital Solutions!...",
  "revised_response": "Olá! 👋 Bem-vindo à WB Digital Solutions! Como posso ajudar você hoje?",
  "response_parts": [
    "Olá! 👋 Bem-vindo à WB Digital Solutions!",
    "Como posso ajudar você hoje?"
  ],
  "detected_intent": "greeting",
  "final_step": "cached_response",
  "language_used": "pt-BR",
  "context_page": "/",
  "is_greeting": false,
  "cached": true,
  "cache_type": "pattern_match"
}
```

**Common Errors**:

#### Missing Required Field
```json
{
  "detail": [
    {
      "loc": ["body", "message"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

#### Invalid JSON
```json
{
  "detail": "Invalid JSON in request body"
}
```

#### Server Error
```json
{
  "detail": "Internal server error during message processing"
}
```

---

### 3. Chat Stream (SSE)
Stream chat responses using Server-Sent Events for real-time interaction.

**Endpoint**: `POST /chat/stream`

**Request Body**:
```json
{
  "message": "string (required)",
  "user_id": "string (optional, default: 'anon')",
  "language": "string (optional, default: 'pt-BR')",
  "current_page": "string (optional, default: '/')"
}
```

**Response**: Server-Sent Events stream

**Event Types**:
1. `acknowledgment`: Message received confirmation
2. `thinking`: Processing status
3. `message`: Actual response parts
4. `complete`: Stream completion

**Example**:
```javascript
// JavaScript EventSource example
const eventSource = new EventSource('/chat/stream', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    message: 'Olá!',
    user_id: 'user123'
  })
});

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch(data.type) {
    case 'acknowledgment':
      console.log('Message received:', data.message);
      break;
    case 'thinking':
      console.log('Processing:', data.message);
      break;
    case 'message':
      console.log(`Part ${data.part}/${data.total}:`, data.content);
      break;
    case 'complete':
      console.log('Stream complete');
      eventSource.close();
      break;
  }
};

eventSource.onerror = (error) => {
  console.error('Stream error:', error);
  eventSource.close();
};
```

**Stream Response Example**:
```
data: {"type": "acknowledgment", "message": "Recebi sua mensagem! 😊"}

data: {"type": "thinking", "message": "Estou pensando na melhor resposta..."}

data: {"type": "message", "content": "Olá! 👋 Eu sou o assistente virtual da WB Digital Solutions.", "part": 1, "total": 3}

data: {"type": "message", "content": "Ajudamos empresas a crescer com sites rápidos, automações inteligentes e soluções com IA.", "part": 2, "total": 3}

data: {"type": "message", "content": "Me conta o que você precisa — um orçamento, saber mais sobre algum serviço ou tirar dúvidas? 😊", "part": 3, "total": 3}

data: {"type": "complete", "message": "Resposta completa"}
```

**Status Codes**:
- `200 OK`: Stream started successfully
- `400 Bad Request`: Invalid request
- `500 Internal Server Error`: Stream error

---

### 4. Usage Report
Get DeepSeek API usage statistics and cost report.

**Endpoint**: `GET /usage-report`

**Response**:
```json
{
  "status": "success",
  "report": {
    "total_requests": 150,
    "total_tokens": {
      "input": 45000,
      "output": 32000,
      "total": 77000
    },
    "total_cost_brl": 2.45,
    "average_tokens_per_request": {
      "input": 300,
      "output": 213,
      "total": 513
    },
    "hourly_distribution": {
      "0": 5,
      "1": 3,
      "8": 25,
      "9": 30,
      "10": 20,
      "14": 15,
      "15": 18,
      "16": 12,
      "20": 10,
      "21": 8,
      "22": 4
    },
    "discount_savings_brl": 1.22,
    "current_discount": true,
    "last_reset": "2024-01-15T00:00:00Z"
  },
  "message": "🎉 Desconto de 50% ATIVO!"
}
```

**Response Fields**:
- `total_requests`: Total API calls made
- `total_tokens`: Token usage breakdown
- `total_cost_brl`: Total cost in Brazilian Reais
- `average_tokens_per_request`: Average token consumption
- `hourly_distribution`: Requests per hour of day
- `discount_savings_brl`: Amount saved with discount pricing
- `current_discount`: Whether discount is currently active
- `last_reset`: When statistics were last reset

**Example**:
```bash
curl -X GET https://chatbot.wbdigitalsolutions.com/usage-report
```

**Status Codes**:
- `200 OK`: Report generated successfully
- `500 Internal Server Error`: Error generating report

---

## Error Handling

### Standard Error Response Format
```json
{
  "detail": "string or object with error details"
}
```

### Common HTTP Status Codes
- `200 OK`: Request successful
- `400 Bad Request`: Invalid request format or parameters
- `404 Not Found`: Endpoint not found
- `422 Unprocessable Entity`: Request validation failed
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily unavailable

### Rate Limiting
Currently no rate limiting is implemented, but may be added in future versions.

---

## Cache Strategy

The API implements a two-tier caching system:

1. **Pattern Match Cache** (< 100ms response):
   - Common greetings and frequently asked questions
   - Language-specific responses
   - Instant response without LLM calls

2. **Redis Cache** (7-day TTL):
   - Exact message matches
   - Considers language and current page context
   - SHA256 hash as cache key

Cache keys are generated using: `SHA256(message + language + current_page)`

---

## WebSocket Support (Future)

WebSocket support for real-time bidirectional communication is planned for future releases.

---

## Monitoring

### Health Checks
- Endpoint: `GET /health`
- Recommended interval: 30 seconds
- Timeout: 5 seconds

### Metrics (Future)
Prometheus metrics endpoint planned at `/metrics`

---

## SDK Examples

### Python
```python
import requests

def send_message(message, language="pt-BR"):
    response = requests.post(
        "https://chatbot.wbdigitalsolutions.com/chat",
        json={
            "message": message,
            "language": language,
            "user_id": "python_client"
        }
    )
    return response.json()

# Usage
result = send_message("Olá, preciso de ajuda!")
print(result["revised_response"])
```

### JavaScript/TypeScript
```typescript
async function sendMessage(message: string, language: string = "pt-BR") {
  const response = await fetch("https://chatbot.wbdigitalsolutions.com/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      language,
      user_id: "js_client",
    }),
  });

  return response.json();
}

// Usage
const result = await sendMessage("Olá!");
console.log(result.revised_response);
```

### cURL
```bash
curl -X POST https://chatbot.wbdigitalsolutions.com/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Quero saber sobre automação",
    "language": "pt-BR"
  }'
```

---

## Changelog

### Version 1.0.0 (Current)
- Initial release
- Basic chat functionality
- Multi-language support
- Two-tier caching system
- SSE streaming endpoint
- Usage reporting

### Planned Features
- WebSocket support
- User session management
- Conversation history API
- Admin dashboard endpoints
- Webhook integrations
- Rate limiting
- API key authentication