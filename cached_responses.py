# cached_responses.py
"""
Respostas pré-computadas para perguntas frequentes
Objetivo: Reduzir tempo de resposta de 44s para < 500ms
"""

CACHED_RESPONSES = {
    "pricing": {
        "patterns": [
            # Português
            "quanto custa", "qual o preço", "qual o valor", "quanto é",
            "valores", "preço", "custo", "orçamento", "investimento",
            "quanto cobram", "quanto sai", "quanto fica", "tabela de preço",
            # English
            "how much", "price", "cost", "pricing", "budget", "investment",
            "quote", "rates", "fee", "charge",
            # Spanish
            "cuanto cuesta", "precio", "costo", "presupuesto", "cotización",
            "tarifas", "inversión", "cuánto vale",
            # Italian
            "quanto costa", "prezzo", "costo", "preventivo", "tariffa",
            "investimento", "quotazione"
        ],
        "intent": "request_quote",
        "responses": {
            "pt-BR": {
                "response_parts": [
                    "Ótima pergunta! 😊 Na WB Digital Solutions, o custo de um site depende da complexidade e funcionalidades do projeto.",
                    "📋 **Faixas de investimento:**",
                    "• **Landing Page**: a partir de R$ 3.000",
                    "• **Site Institucional**: R$ 6.000 a R$ 15.000",
                    "• **E-commerce**: a partir de R$ 12.000",
                    "• **Projetos com IA**: valores sob consulta",
                    "💡 O valor final depende de: design exclusivo, funcionalidades específicas, integrações e prazo.",
                    "📲 **Quer um orçamento personalizado?**\nCompartilhe seu WhatsApp ou e-mail e nossa equipe entrará em contato em até 24h!",
                    "Exemplo: 'Meu WhatsApp é (11) 99999-9999'",
                    "Transformamos suas ideias em soluções digitais! 🚀"
                ],
                "full_response": """Ótima pergunta! 😊 Na WB Digital Solutions, o custo de um site depende da complexidade e funcionalidades do projeto.

📋 **Faixas de investimento:**
• **Landing Page**: a partir de R$ 3.000
• **Site Institucional**: R$ 6.000 a R$ 15.000
• **E-commerce**: a partir de R$ 12.000
• **Projetos com IA**: valores sob consulta

💡 O valor final depende de: design exclusivo, funcionalidades específicas, integrações e prazo.

📲 **Quer um orçamento personalizado?**
Compartilhe seu WhatsApp ou e-mail e nossa equipe entrará em contato em até 24h!

Exemplo: 'Meu WhatsApp é (11) 99999-9999'

Transformamos suas ideias em soluções digitais! 🚀"""
            },
            "en": {
                "response_parts": [
                    "Great question! 😊 At WB Digital Solutions, website costs depend on project complexity and features.",
                    "📋 **Investment ranges:**",
                    "• **Landing Page**: from $600 USD",
                    "• **Corporate Website**: $1,200 to $3,000 USD",
                    "• **E-commerce**: from $2,400 USD",
                    "• **AI Projects**: custom quote",
                    "💡 Final price depends on: exclusive design, specific features, integrations, and timeline.",
                    "📲 **Want a personalized quote?**\nShare your WhatsApp or email and our team will contact you within 24h!",
                    "Example: 'My WhatsApp is +1 555-0100'",
                    "We transform your ideas into digital solutions! 🚀"
                ],
                "full_response": """Great question! 😊 At WB Digital Solutions, website costs depend on project complexity and features.

📋 **Investment ranges:**
• **Landing Page**: from $600 USD
• **Corporate Website**: $1,200 to $3,000 USD
• **E-commerce**: from $2,400 USD
• **AI Projects**: custom quote

💡 Final price depends on: exclusive design, specific features, integrations, and timeline.

📲 **Want a personalized quote?**
Share your WhatsApp or email and our team will contact you within 24h!

Example: 'My WhatsApp is +1 555-0100'

We transform your ideas into digital solutions! 🚀"""
            },
            "es": {
                "response_parts": [
                    "¡Excelente pregunta! 😊 En WB Digital Solutions, el costo depende de la complejidad del proyecto.",
                    "📋 **Rangos de inversión:**",
                    "• **Landing Page**: desde $600 USD",
                    "• **Sitio Corporativo**: $1,200 a $3,000 USD",
                    "• **E-commerce**: desde $2,400 USD",
                    "• **Proyectos con IA**: cotización personalizada",
                    "💡 El precio final depende de: diseño exclusivo, funcionalidades, integraciones y plazo.",
                    "📲 **¿Quieres una cotización personalizada?**\nComparte tu WhatsApp o email y te contactaremos en 24h.",
                    "Ejemplo: 'Mi WhatsApp es +34 600 000 000'",
                    "¡Transformamos tus ideas en soluciones digitales! 🚀"
                ],
                "full_response": """¡Excelente pregunta! 😊 En WB Digital Solutions, el costo depende de la complejidad del proyecto.

📋 **Rangos de inversión:**
• **Landing Page**: desde $600 USD
• **Sitio Corporativo**: $1,200 a $3,000 USD
• **E-commerce**: desde $2,400 USD
• **Proyectos con IA**: cotización personalizada

💡 El precio final depende de: diseño exclusivo, funcionalidades, integraciones y plazo.

📲 **¿Quieres una cotización personalizada?**
Comparte tu WhatsApp o email y te contactaremos en 24h.

Ejemplo: 'Mi WhatsApp es +34 600 000 000'

¡Transformamos tus ideas en soluciones digitales! 🚀"""
            },
            "it": {
                "response_parts": [
                    "Ottima domanda! 😊 In WB Digital Solutions, il costo dipende dalla complessità del progetto.",
                    "📋 **Fasce di investimento:**",
                    "• **Landing Page**: da €550",
                    "• **Sito Aziendale**: €1,100 a €2,750",
                    "• **E-commerce**: da €2,200",
                    "• **Progetti con IA**: preventivo personalizzato",
                    "💡 Il prezzo finale dipende da: design esclusivo, funzionalità, integrazioni e tempi.",
                    "📲 **Vuoi un preventivo personalizzato?**\nCondividi il tuo WhatsApp o email e ti contatteremo in 24h.",
                    "Esempio: 'Il mio WhatsApp è +39 333 000 0000'",
                    "Trasformiamo le tue idee in soluzioni digitali! 🚀"
                ],
                "full_response": """Ottima domanda! 😊 In WB Digital Solutions, il costo dipende dalla complessità del progetto.

📋 **Fasce di investimento:**
• **Landing Page**: da €550
• **Sito Aziendale**: €1,100 a €2,750
• **E-commerce**: da €2,200
• **Progetti con IA**: preventivo personalizzato

💡 Il prezzo finale dipende da: design esclusivo, funzionalità, integrazioni e tempi.

📲 **Vuoi un preventivo personalizzato?**
Condividi il tuo WhatsApp o email e ti contatteremo in 24h.

Esempio: 'Il mio WhatsApp è +39 333 000 0000'

Trasformiamo le tue idee in soluzioni digitali! 🚀"""
            }
        }
    }
}


def detect_cached_intent(user_input: str, language: str = "pt-BR") -> dict:
    """
    Detecta se a pergunta do usuário tem uma resposta em cache
    
    Args:
        user_input: Mensagem do usuário
        language: Idioma da resposta
        
    Returns:
        Dict com a resposta cacheada ou None
    """
    lower_input = user_input.lower()
    
    for cache_key, cache_data in CACHED_RESPONSES.items():
        # Verifica se algum padrão corresponde
        if any(pattern in lower_input for pattern in cache_data["patterns"]):
            # Retorna a resposta no idioma correto
            lang_response = cache_data["responses"].get(language, cache_data["responses"]["pt-BR"])
            
            return {
                "cache_key": cache_key,
                "intent": cache_data["intent"],
                "response": lang_response["full_response"],
                "response_parts": lang_response["response_parts"],
                "is_cached": True,
                "cache_type": "pattern_match"
            }
    
    return None