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
                    "📲 **Quer um orçamento personalizado?**\nNossa equipe responde em até 2h no horário comercial!",
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
Nossa equipe responde em até 2h no horário comercial!

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
                    "📲 **Want a personalized quote?**\nOur team responds within 2h during business hours!",
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
Our team responds within 2h during business hours!

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
                    "📲 **¿Quieres una cotización personalizada?**\nNuestro equipo responde en 2h en horario comercial.",
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
Nuestro equipo responde en 2h en horario comercial.

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
                    "📲 **Vuoi un preventivo personalizzato?**\nIl nostro team risponde in 2h durante l'orario lavorativo.",
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
Il nostro team risponde in 2h durante l'orario lavorativo.

Trasformiamo le tue idee in soluzioni digitali! 🚀"""
            }
        }
    },
    "services": {
        "patterns": [
            # Português
            "quais serviços", "o que fazem", "o que vocês fazem", "serviços disponíveis",
            "serviços oferecidos", "o que oferecem", "como podem ajudar",
            # English
            "what services", "what do you do", "services available", "services offered",
            "how can you help", "what you offer",
            # Spanish
            "qué servicios", "qué hacen", "servicios disponibles", "servicios ofrecidos",
            "cómo pueden ayudar", "qué ofrecen",
            # Italian
            "quali servizi", "cosa fate", "servizi disponibili", "servizi offerti",
            "come potete aiutare", "cosa offrite"
        ],
        "intent": "inquire_services",
        "responses": {
            "pt-BR": {
                "response_parts": [
                    "🚀 Somos especialistas em transformação digital! Oferecemos:",
                    "**1. 🌐 Desenvolvimento Web Premium**",
                    "• Sites institucionais de alta performance",
                    "• E-commerce com conversão otimizada",
                    "• Landing pages que convertem visitantes em clientes",
                    "• Progressive Web Apps (PWA)",
                    "**2. 🤖 Automação Inteligente**",
                    "• Automação de processos repetitivos",
                    "• Integração entre sistemas (APIs)",
                    "• Chatbots com IA para atendimento 24/7",
                    "• Workflows automatizados",
                    "**3. 🧠 Soluções com Inteligência Artificial**",
                    "• Análise preditiva de dados",
                    "• Processamento de linguagem natural",
                    "• Visão computacional",
                    "• Machine Learning personalizado",
                    "💎 **Diferenciais:** Tecnologias modernas (Next.js, TypeScript, Rust), segurança LGPD/GDPR, suporte contínuo.",
                    "Interessado em algum serviço específico? Fale conosco!"
                ],
                "full_response": """🚀 Somos especialistas em transformação digital! Oferecemos:

**1. 🌐 Desenvolvimento Web Premium**
• Sites institucionais de alta performance
• E-commerce com conversão otimizada
• Landing pages que convertem visitantes em clientes
• Progressive Web Apps (PWA)

**2. 🤖 Automação Inteligente**
• Automação de processos repetitivos
• Integração entre sistemas (APIs)
• Chatbots com IA para atendimento 24/7
• Workflows automatizados

**3. 🧠 Soluções com Inteligência Artificial**
• Análise preditiva de dados
• Processamento de linguagem natural
• Visão computacional
• Machine Learning personalizado

💎 **Diferenciais:** Tecnologias modernas (Next.js, TypeScript, Rust), segurança LGPD/GDPR, suporte contínuo.

Interessado em algum serviço específico? Fale conosco!"""
            },
            "en": {
                "response_parts": [
                    "🚀 We're digital transformation experts! We offer:",
                    "**1. 🌐 Premium Web Development**",
                    "• High-performance corporate websites",
                    "• Optimized e-commerce platforms",
                    "• Landing pages that convert",
                    "• Progressive Web Apps (PWA)",
                    "**2. 🤖 Intelligent Automation**",
                    "• Process automation",
                    "• System integrations (APIs)",
                    "• AI chatbots for 24/7 support",
                    "• Automated workflows",
                    "**3. 🧠 AI-Powered Solutions**",
                    "• Predictive data analysis",
                    "• Natural language processing",
                    "• Computer vision",
                    "• Custom machine learning",
                    "💎 **Key Features:** Modern tech stack (Next.js, TypeScript, Rust), GDPR compliance, ongoing support.",
                    "Interested in a specific service? Share your contact!"
                ],
                "full_response": """🚀 We're digital transformation experts! We offer:

**1. 🌐 Premium Web Development**
• High-performance corporate websites
• Optimized e-commerce platforms
• Landing pages that convert
• Progressive Web Apps (PWA)

**2. 🤖 Intelligent Automation**
• Process automation
• System integrations (APIs)
• AI chatbots for 24/7 support
• Automated workflows

**3. 🧠 AI-Powered Solutions**
• Predictive data analysis
• Natural language processing
• Computer vision
• Custom machine learning

💎 **Key Features:** Modern tech stack (Next.js, TypeScript, Rust), GDPR compliance, ongoing support.

Interested in a specific service? Share your contact!"""
            },
            "es": {
                "response_parts": [
                    "🚀 ¡Somos expertos en transformación digital! Ofrecemos:",
                    "**1. 🌐 Desarrollo Web Premium**",
                    "• Sitios corporativos de alto rendimiento",
                    "• E-commerce optimizado",
                    "• Landing pages que convierten",
                    "• Progressive Web Apps (PWA)",
                    "**2. 🤖 Automatización Inteligente**",
                    "• Automatización de procesos",
                    "• Integración de sistemas (APIs)",
                    "• Chatbots con IA 24/7",
                    "• Flujos automatizados",
                    "**3. 🧠 Soluciones con IA**",
                    "• Análisis predictivo",
                    "• Procesamiento de lenguaje natural",
                    "• Visión por computadora",
                    "• Machine Learning personalizado",
                    "💎 **Ventajas:** Tecnología moderna (Next.js, TypeScript, Rust), GDPR, soporte continuo.",
                    "¿Interesado en algún servicio? ¡Comparte tu contacto!"
                ],
                "full_response": """🚀 ¡Somos expertos en transformación digital! Ofrecemos:

**1. 🌐 Desarrollo Web Premium**
• Sitios corporativos de alto rendimiento
• E-commerce optimizado
• Landing pages que convierten
• Progressive Web Apps (PWA)

**2. 🤖 Automatización Inteligente**
• Automatización de procesos
• Integración de sistemas (APIs)
• Chatbots con IA 24/7
• Flujos automatizados

**3. 🧠 Soluciones con IA**
• Análisis predictivo
• Procesamiento de lenguaje natural
• Visión por computadora
• Machine Learning personalizado

💎 **Ventajas:** Tecnología moderna (Next.js, TypeScript, Rust), GDPR, soporte continuo.

¿Interesado en algún servicio? ¡Comparte tu contacto!"""
            },
            "it": {
                "response_parts": [
                    "🚀 Siamo esperti di trasformazione digitale! Offriamo:",
                    "**1. 🌐 Sviluppo Web Premium**",
                    "• Siti aziendali ad alte prestazioni",
                    "• E-commerce ottimizzati",
                    "• Landing page che convertono",
                    "• Progressive Web Apps (PWA)",
                    "**2. 🤖 Automazione Intelligente**",
                    "• Automazione dei processi",
                    "• Integrazione sistemi (API)",
                    "• Chatbot con IA 24/7",
                    "• Workflow automatizzati",
                    "**3. 🧠 Soluzioni con IA**",
                    "• Analisi predittiva",
                    "• Elaborazione del linguaggio",
                    "• Computer vision",
                    "• Machine Learning personalizzato",
                    "💎 **Vantaggi:** Tecnologie moderne (Next.js, TypeScript, Rust), GDPR, supporto continuo.",
                    "Interessato a un servizio? Condividi il tuo contatto!"
                ],
                "full_response": """🚀 Siamo esperti di trasformazione digitale! Offriamo:

**1. 🌐 Sviluppo Web Premium**
• Siti aziendali ad alte prestazioni
• E-commerce ottimizzati
• Landing page che convertono
• Progressive Web Apps (PWA)

**2. 🤖 Automazione Intelligente**
• Automazione dei processi
• Integrazione sistemi (API)
• Chatbot con IA 24/7
• Workflow automatizzati

**3. 🧠 Soluzioni con IA**
• Analisi predittiva
• Elaborazione del linguaggio
• Computer vision
• Machine Learning personalizzato

💎 **Vantaggi:** Tecnologie moderne (Next.js, TypeScript, Rust), GDPR, supporto continuo.

Interessato a un servizio? Condividi il tuo contatto!"""
            }
        }
    },
    "timeline": {
        "patterns": [
            # Português
            "quanto tempo", "prazo", "demora", "quando fica pronto", "tempo de entrega",
            "quantos dias", "quantas semanas", "duração",
            # English
            "how long", "timeline", "deadline", "delivery time", "duration",
            "how many days", "how many weeks", "time frame",
            # Spanish
            "cuánto tiempo", "plazo", "tiempo de entrega", "duración",
            "cuántos días", "cuántas semanas",
            # Italian
            "quanto tempo", "tempi", "scadenza", "durata", "tempistiche",
            "quanti giorni", "quante settimane"
        ],
        "intent": "inquire_services",
        "responses": {
            "pt-BR": {
                "response_parts": [
                    "⏱️ Nossos prazos são transparentes e realistas:",
                    "**📄 Landing Page:** 1-2 semanas",
                    "**🏢 Site Institucional:** 4-6 semanas",
                    "**🛒 E-commerce:** 8-12 semanas",
                    "**🤖 Automações:** 2-4 semanas",
                    "**🧠 Projetos com IA:** 6-12 semanas",
                    "**Fases do projeto:**",
                    "1️⃣ Discovery: 1 semana",
                    "2️⃣ Design: 2-3 semanas",
                    "3️⃣ Desenvolvimento: 3-6 semanas",
                    "4️⃣ Testes e ajustes: 1 semana",
                    "⚡ **Entrega urgente?** Temos opção fast-track com 30% de urgência.",
                    "Precisa para uma data específica? Me conta mais sobre seu projeto!"
                ],
                "full_response": """⏱️ Nossos prazos são transparentes e realistas:

**📄 Landing Page:** 1-2 semanas
**🏢 Site Institucional:** 4-6 semanas
**🛒 E-commerce:** 8-12 semanas
**🤖 Automações:** 2-4 semanas
**🧠 Projetos com IA:** 6-12 semanas

**Fases do projeto:**
1️⃣ Discovery: 1 semana
2️⃣ Design: 2-3 semanas
3️⃣ Desenvolvimento: 3-6 semanas
4️⃣ Testes e ajustes: 1 semana

⚡ **Entrega urgente?** Temos opção fast-track com 30% de urgência.

Precisa para uma data específica? Me conta mais sobre seu projeto!"""
            },
            "en": {
                "response_parts": [
                    "⏱️ Our timelines are transparent and realistic:",
                    "**📄 Landing Page:** 1-2 weeks",
                    "**🏢 Corporate Website:** 4-6 weeks",
                    "**🛒 E-commerce:** 8-12 weeks",
                    "**🤖 Automation:** 2-4 weeks",
                    "**🧠 AI Projects:** 6-12 weeks",
                    "**Project phases:**",
                    "1️⃣ Discovery: 1 week",
                    "2️⃣ Design: 2-3 weeks",
                    "3️⃣ Development: 3-6 weeks",
                    "4️⃣ Testing & Launch: 1 week",
                    "⚡ **Urgent delivery?** Fast-track option with 30% rush fee.",
                    "Need it by a specific date? Tell me more about your project!"
                ],
                "full_response": """⏱️ Our timelines are transparent and realistic:

**📄 Landing Page:** 1-2 weeks
**🏢 Corporate Website:** 4-6 weeks
**🛒 E-commerce:** 8-12 weeks
**🤖 Automation:** 2-4 weeks
**🧠 AI Projects:** 6-12 weeks

**Project phases:**
1️⃣ Discovery: 1 week
2️⃣ Design: 2-3 weeks
3️⃣ Development: 3-6 weeks
4️⃣ Testing & Launch: 1 week

⚡ **Urgent delivery?** Fast-track option with 30% rush fee.

Need it by a specific date? Tell me more about your project!"""
            },
            "es": {
                "response_parts": [
                    "⏱️ Nuestros plazos son transparentes y realistas:",
                    "**📄 Landing Page:** 1-2 semanas",
                    "**🏢 Sitio Corporativo:** 4-6 semanas",
                    "**🛒 E-commerce:** 8-12 semanas",
                    "**🤖 Automatización:** 2-4 semanas",
                    "**🧠 Proyectos IA:** 6-12 semanas",
                    "**Fases del proyecto:**",
                    "1️⃣ Discovery: 1 semana",
                    "2️⃣ Diseño: 2-3 semanas",
                    "3️⃣ Desarrollo: 3-6 semanas",
                    "4️⃣ Pruebas y lanzamiento: 1 semana",
                    "⚡ **¿Entrega urgente?** Opción fast-track con 30% de urgencia.",
                    "¿Necesitas para una fecha específica? ¡Cuéntame más!"
                ],
                "full_response": """⏱️ Nuestros plazos son transparentes y realistas:

**📄 Landing Page:** 1-2 semanas
**🏢 Sitio Corporativo:** 4-6 semanas
**🛒 E-commerce:** 8-12 semanas
**🤖 Automatización:** 2-4 semanas
**🧠 Proyectos IA:** 6-12 semanas

**Fases del proyecto:**
1️⃣ Discovery: 1 semana
2️⃣ Diseño: 2-3 semanas
3️⃣ Desarrollo: 3-6 semanas
4️⃣ Pruebas y lanzamiento: 1 semana

⚡ **¿Entrega urgente?** Opción fast-track con 30% de urgencia.

¿Necesitas para una fecha específica? ¡Cuéntame más!"""
            },
            "it": {
                "response_parts": [
                    "⏱️ I nostri tempi sono trasparenti e realistici:",
                    "**📄 Landing Page:** 1-2 settimane",
                    "**🏢 Sito Aziendale:** 4-6 settimane",
                    "**🛒 E-commerce:** 8-12 settimane",
                    "**🤖 Automazione:** 2-4 settimane",
                    "**🧠 Progetti IA:** 6-12 settimane",
                    "**Fasi del progetto:**",
                    "1️⃣ Discovery: 1 settimana",
                    "2️⃣ Design: 2-3 settimane",
                    "3️⃣ Sviluppo: 3-6 settimane",
                    "4️⃣ Test e lancio: 1 settimana",
                    "⚡ **Consegna urgente?** Opzione fast-track con 30% di urgenza.",
                    "Serve per una data specifica? Raccontami di più!"
                ],
                "full_response": """⏱️ I nostri tempi sono trasparenti e realistici:

**📄 Landing Page:** 1-2 settimane
**🏢 Sito Aziendale:** 4-6 settimane
**🛒 E-commerce:** 8-12 settimane
**🤖 Automazione:** 2-4 settimane
**🧠 Progetti IA:** 6-12 settimane

**Fasi del progetto:**
1️⃣ Discovery: 1 settimana
2️⃣ Design: 2-3 settimane
3️⃣ Sviluppo: 3-6 settimane
4️⃣ Test e lancio: 1 settimana

⚡ **Consegna urgente?** Opzione fast-track con 30% di urgenza.

Serve per una data specifica? Raccontami di più!"""
            }
        }
    },
    "contact": {
        "patterns": [
            # Português
            "como falo", "entrar em contato", "falar com vocês", "contato",
            "telefone", "whatsapp", "email", "como contatar",
            # English
            "how to contact", "contact you", "get in touch", "contact info",
            "phone", "whatsapp", "email", "reach you",
            # Spanish
            "cómo contactar", "contactarlos", "contacto", "teléfono",
            "whatsapp", "correo", "email",
            # Italian
            "come contattare", "contattarvi", "contatto", "telefono",
            "whatsapp", "email", "raggiungervi"
        ],
        "intent": "share_contact",
        "responses": {
            "pt-BR": {
                "response_parts": [
                    "📞 Adoramos conversar com nossos clientes! Aqui estão nossos contatos:",
                    "**📱 WhatsApp Direto:**",
                    "[+55 (11) 98286-4581](https://wa.me/5511982864581)",
                    "**📧 E-mail:**",
                    "[bruno@wbdigitalsolutions.com](mailto:bruno@wbdigitalsolutions.com)",
                    "**💬 Resposta rápida:** WhatsApp em até 2h (horário comercial)",
                    "**📅 Agendar reunião:** Envie 'Quero agendar' no WhatsApp",
                    "Nossa equipe responde rápido - estamos prontos para ajudar! 🚀"
                ],
                "full_response": """📞 Adoramos conversar com nossos clientes! Aqui estão nossos contatos:

**📱 WhatsApp Direto:**
[+55 (11) 98286-4581](https://wa.me/5511982864581)

**📧 E-mail:**
[bruno@wbdigitalsolutions.com](mailto:bruno@wbdigitalsolutions.com)

**💬 Resposta rápida:** WhatsApp em até 2h (horário comercial)
**📅 Agendar reunião:** Envie 'Quero agendar' no WhatsApp

Nossa equipe responde rápido - estamos prontos para ajudar! 🚀"""
            },
            "en": {
                "response_parts": [
                    "📞 We love talking to our clients! Here's how to reach us:",
                    "**📱 WhatsApp Direct:**",
                    "[+55 (11) 98286-4581](https://wa.me/5511982864581)",
                    "**📧 Email:**",
                    "[bruno@wbdigitalsolutions.com](mailto:bruno@wbdigitalsolutions.com)",
                    "**💬 Quick response:** WhatsApp within 2h (business hours)",
                    "**📅 Schedule meeting:** Send 'Schedule meeting' on WhatsApp",
                    "Our team responds quickly - we're ready to help! 🚀"
                ],
                "full_response": """📞 We love talking to our clients! Here's how to reach us:

**📱 WhatsApp Direct:**
[+55 (11) 98286-4581](https://wa.me/5511982864581)

**📧 Email:**
[bruno@wbdigitalsolutions.com](mailto:bruno@wbdigitalsolutions.com)

**💬 Quick response:** WhatsApp within 2h (business hours)
**📅 Schedule meeting:** Send 'Schedule meeting' on WhatsApp

Our team responds quickly - we're ready to help! 🚀"""
            },
            "es": {
                "response_parts": [
                    "📞 ¡Nos encanta hablar con nuestros clientes! Contáctanos:",
                    "**📱 WhatsApp Directo:**",
                    "[+55 (11) 98286-4581](https://wa.me/5511982864581)",
                    "**📧 Email:**",
                    "[bruno@wbdigitalsolutions.com](mailto:bruno@wbdigitalsolutions.com)",
                    "**💬 Respuesta rápida:** WhatsApp en 2h (horario comercial)",
                    "**📅 Agendar reunión:** Envía 'Quiero agendar' por WhatsApp",
                    "Nuestro equipo responde rápido - ¡estamos listos para ayudar! 🚀"
                ],
                "full_response": """📞 ¡Nos encanta hablar con nuestros clientes! Contáctanos:

**📱 WhatsApp Directo:**
[+55 (11) 98286-4581](https://wa.me/5511982864581)

**📧 Email:**
[bruno@wbdigitalsolutions.com](mailto:bruno@wbdigitalsolutions.com)

**💬 Respuesta rápida:** WhatsApp en 2h (horario comercial)
**📅 Agendar reunión:** Envía 'Quiero agendar' por WhatsApp

Nuestro equipo responde rápido - ¡estamos listos para ayudar! 🚀"""
            },
            "it": {
                "response_parts": [
                    "📞 Amiamo parlare con i nostri clienti! Ecco i contatti:",
                    "**📱 WhatsApp Diretto:**",
                    "[+55 (11) 98286-4581](https://wa.me/5511982864581)",
                    "**📧 Email:**",
                    "[bruno@wbdigitalsolutions.com](mailto:bruno@wbdigitalsolutions.com)",
                    "**💬 Risposta rapida:** WhatsApp in 2h (orario lavorativo)",
                    "**📅 Fissare riunione:** Invia 'Voglio fissare' su WhatsApp",
                    "Il nostro team risponde velocemente - siamo pronti ad aiutarti! 🚀"
                ],
                "full_response": """📞 Amiamo parlare con i nostri clienti! Ecco i contatti:

**📱 WhatsApp Diretto:**
[+55 (11) 98286-4581](https://wa.me/5511982864581)

**📧 Email:**
[bruno@wbdigitalsolutions.com](mailto:bruno@wbdigitalsolutions.com)

**💬 Risposta rapida:** WhatsApp in 2h (orario lavorativo)
**📅 Fissare riunione:** Invia 'Voglio fissare' su WhatsApp

Il nostro team risponde velocemente - siamo pronti ad aiutarti! 🚀"""
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