# deepseek_optimizer.py
"""
Otimizações para reduzir custos da API DeepSeek
- Detecção de horário de desconto (50% OFF)
- Context Caching
- Monitoramento de custos
"""

from datetime import datetime
import pytz
import logging
from typing import Dict, Tuple, Optional

class DeepSeekOptimizer:
    """Gerencia otimizações de custo para API DeepSeek"""
    
    # Preços por 1M tokens (em USD)
    PRICING = {
        "standard": {
            "input_cache_hit": 0.07,
            "input_cache_miss": 0.27,
            "output": 1.10
        },
        "discount": {  # 16:30-00:30 UTC
            "input_cache_hit": 0.035,
            "input_cache_miss": 0.135,
            "output": 0.55
        }
    }
    
    # Contadores para monitoramento
    token_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_hits": 0,
        "cache_misses": 0,
        "api_calls": 0,
        "cached_responses": 0
    }
    
    @staticmethod
    def is_discount_time() -> bool:
        """
        Verifica se está no horário de desconto (16:30-00:30 UTC)
        No Brasil: 13:30-21:30 (horário de Brasília)
        
        Returns:
            bool: True se está no horário de desconto
        """
        utc_now = datetime.now(pytz.UTC)
        hour = utc_now.hour
        minute = utc_now.minute
        
        # Converter para decimal para facilitar comparação
        current_time = hour + (minute / 60)
        
        # Desconto: 16:30 (16.5) até 00:30 (0.5)
        if current_time >= 16.5 or current_time < 0.5:
            return True
        return False
    
    @staticmethod
    def get_brazil_time() -> str:
        """Retorna horário atual no Brasil (São Paulo)"""
        brazil_tz = pytz.timezone('America/Sao_Paulo')
        brazil_time = datetime.now(brazil_tz)
        return brazil_time.strftime("%H:%M:%S")
    
    @staticmethod
    def should_use_aggressive_cache() -> bool:
        """
        Determina se deve usar cache agressivo baseado no horário
        
        Returns:
            bool: True se deve priorizar cache (fora do desconto)
        """
        # Use cache agressivo FORA do horário de desconto
        return not DeepSeekOptimizer.is_discount_time()
    
    @staticmethod
    def get_current_pricing() -> Dict[str, float]:
        """
        Retorna preços atuais baseado no horário
        
        Returns:
            dict: Preços atuais por tipo de token
        """
        if DeepSeekOptimizer.is_discount_time():
            return DeepSeekOptimizer.PRICING["discount"]
        return DeepSeekOptimizer.PRICING["standard"]
    
    @staticmethod
    def estimate_cost(input_tokens: int, output_tokens: int, 
                     cache_hit: bool = False) -> Tuple[float, float]:
        """
        Estima custo de uma requisição
        
        Args:
            input_tokens: Número de tokens de entrada
            output_tokens: Número de tokens de saída
            cache_hit: Se houve cache hit no context caching
            
        Returns:
            tuple: (custo_atual, economia_se_desconto)
        """
        pricing = DeepSeekOptimizer.get_current_pricing()
        
        # Calcular custo atual
        if cache_hit:
            input_cost = (input_tokens / 1_000_000) * pricing["input_cache_hit"]
        else:
            input_cost = (input_tokens / 1_000_000) * pricing["input_cache_miss"]
        
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost
        
        # Calcular economia potencial
        if DeepSeekOptimizer.is_discount_time():
            # Já está com desconto, economia seria 0
            savings = 0
        else:
            # Calcular quanto economizaria se fosse horário de desconto
            discount_pricing = DeepSeekOptimizer.PRICING["discount"]
            if cache_hit:
                discount_input = (input_tokens / 1_000_000) * discount_pricing["input_cache_hit"]
            else:
                discount_input = (input_tokens / 1_000_000) * discount_pricing["input_cache_miss"]
            discount_output = (output_tokens / 1_000_000) * discount_pricing["output"]
            discount_total = discount_input + discount_output
            savings = total_cost - discount_total
        
        return total_cost, savings
    
    @staticmethod
    def update_usage(input_tokens: int = 0, output_tokens: int = 0,
                    cache_hit: bool = False, is_cached_response: bool = False):
        """
        Atualiza contadores de uso
        
        Args:
            input_tokens: Tokens de entrada usados
            output_tokens: Tokens de saída gerados
            cache_hit: Se houve cache hit no context caching
            is_cached_response: Se foi resposta do cache local
        """
        if is_cached_response:
            DeepSeekOptimizer.token_usage["cached_responses"] += 1
            logging.info("📦 Resposta do cache local - Custo: $0.00")
        else:
            DeepSeekOptimizer.token_usage["input_tokens"] += input_tokens
            DeepSeekOptimizer.token_usage["output_tokens"] += output_tokens
            DeepSeekOptimizer.token_usage["api_calls"] += 1
            
            if cache_hit:
                DeepSeekOptimizer.token_usage["cache_hits"] += 1
            else:
                DeepSeekOptimizer.token_usage["cache_misses"] += 1
            
            # Calcular e logar custo
            cost, savings = DeepSeekOptimizer.estimate_cost(
                input_tokens, output_tokens, cache_hit
            )
            
            discount_active = DeepSeekOptimizer.is_discount_time()
            brazil_time = DeepSeekOptimizer.get_brazil_time()
            
            logging.info(
                f"💰 API Call - Custo: ${cost:.4f} | "
                f"Desconto: {'✅ ATIVO' if discount_active else '❌ INATIVO'} | "
                f"Horário Brasil: {brazil_time} | "
                f"Tokens: {input_tokens}→{output_tokens}"
            )
            
            if savings > 0:
                logging.info(f"⚠️ Poderia economizar ${savings:.4f} no horário de desconto!")
    
    @staticmethod
    def get_usage_report() -> Dict:
        """
        Gera relatório de uso e custos
        
        Returns:
            dict: Relatório detalhado de uso e custos
        """
        usage = DeepSeekOptimizer.token_usage
        
        # Calcular custos totais (assumindo média de cache hits)
        avg_cache_hit_rate = (
            usage["cache_hits"] / max(usage["api_calls"], 1)
        ) if usage["api_calls"] > 0 else 0
        
        # Estimar custos
        standard_pricing = DeepSeekOptimizer.PRICING["standard"]
        discount_pricing = DeepSeekOptimizer.PRICING["discount"]
        
        # Custo médio ponderado
        input_cost_standard = (
            (usage["input_tokens"] / 1_000_000) * 
            (avg_cache_hit_rate * standard_pricing["input_cache_hit"] +
             (1 - avg_cache_hit_rate) * standard_pricing["input_cache_miss"])
        )
        
        output_cost_standard = (
            (usage["output_tokens"] / 1_000_000) * standard_pricing["output"]
        )
        
        total_cost = input_cost_standard + output_cost_standard
        
        # Calcular economia do cache local
        cache_savings = usage["cached_responses"] * (total_cost / max(usage["api_calls"], 1))
        
        return {
            "total_api_calls": usage["api_calls"],
            "cached_responses": usage["cached_responses"],
            "cache_hit_rate": f"{avg_cache_hit_rate * 100:.1f}%",
            "total_input_tokens": usage["input_tokens"],
            "total_output_tokens": usage["output_tokens"],
            "estimated_cost": f"${total_cost:.4f}",
            "cache_savings": f"${cache_savings:.4f}",
            "current_discount": DeepSeekOptimizer.is_discount_time(),
            "brazil_time": DeepSeekOptimizer.get_brazil_time()
        }
    
    @staticmethod
    def get_optimization_headers() -> Dict[str, str]:
        """
        Retorna headers otimizados para a API DeepSeek
        
        Returns:
            dict: Headers com otimizações ativadas
        """
        headers = {
            "X-Context-Cache": "enabled",  # Ativar context caching
            "X-Response-Format": "json",   # Resposta em JSON quando possível
        }
        
        # Se não está no horário de desconto, sinalizar preferência por cache
        if not DeepSeekOptimizer.is_discount_time():
            headers["X-Prefer-Cache"] = "aggressive"
        
        return headers


# Função auxiliar para decisão de cache
def should_skip_api_call(user_input: str, intent: str = None) -> bool:
    """
    Decide se deve pular chamada à API baseado em otimizações
    
    Args:
        user_input: Entrada do usuário
        intent: Intenção detectada (opcional)
        
    Returns:
        bool: True se deve usar apenas cache local
    """
    # Se está fora do horário de desconto, ser mais agressivo com cache
    if DeepSeekOptimizer.should_use_aggressive_cache():
        # Lista expandida de palavras que indicam perguntas simples
        simple_patterns = [
            "oi", "olá", "hello", "hi", "bom dia", "boa tarde", "boa noite",
            "quanto custa", "preço", "valor", "orçamento",
            "serviços", "o que fazem", "como funciona",
            "contato", "telefone", "whatsapp", "email",
            "prazo", "quanto tempo", "demora",
            "localização", "onde fica", "endereço"
        ]
        
        lower_input = user_input.lower()
        if any(pattern in lower_input for pattern in simple_patterns):
            logging.info("🚫 Pulando API - Cache agressivo ativo (fora do desconto)")
            return True
    
    return False


# Função para estimar tokens (aproximação)
def estimate_tokens(text: str) -> int:
    """
    Estima número de tokens em um texto
    Aproximação: ~4 caracteres por token para português
    
    Args:
        text: Texto para estimar
        
    Returns:
        int: Número estimado de tokens
    """
    return len(text) // 4