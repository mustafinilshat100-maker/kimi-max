import asyncio
import logging
from datetime import datetime
from typing import Optional
from telegram import Bot
from telegram.constants import ParseMode
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global bot instance for simple messaging
_bot = None
_chat_id = None

def _init_bot():
    """Initialize global bot instance"""
    global _bot, _chat_id
    if _bot is None:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        _chat_id = os.getenv('TELEGRAM_CHAT_ID')
        if bot_token:
            _bot = Bot(token=bot_token)
            logger.info("Global bot instance initialized")
    return _bot

def send_message(text):
    """
    Send simple text message to Telegram.
    Synchronous wrapper for async send.
    """
    import asyncio
    
    bot = _init_bot()
    if not bot or not _chat_id:
        logger.error("Bot not initialized or chat_id missing")
        return
    
    try:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        loop.run_until_complete(
            bot.send_message(chat_id=_chat_id, text=text)
        )
        logger.info(f"Message sent: {text[:50]}...")
    except Exception as e:
        logger.error(f"Error sending message: {e}")


class TelegramNotifier:
    """Send signals and alerts to Telegram - v2.0 Professional Format"""
    
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.bot: Optional[Bot] = None
        
        if self.bot_token:
            self.bot = Bot(token=self.bot_token)
            logger.info("TelegramNotifier v2.0 initialized")
        else:
            logger.error("TELEGRAM_BOT_TOKEN not set")
    
    def _get_chain_dex_url(self, chain: str) -> str:
        """Get chain identifier for DexScreener URLs"""
        chain_map = {
            'ethereum': 'ethereum',
            'bsc': 'bsc',
            'solana': 'solana',
            'base': 'base',
            'arbitrum': 'arbitrum',
            'polygon': 'polygon',
            'optimism': 'optimism',
            'avalanche': 'avalanche',
        }
        return chain_map.get(chain.lower(), chain.lower())
    
    def _get_chain_gecko_url(self, chain: str) -> str:
        """Get chain identifier for GeckoTerminal URLs"""
        chain_map = {
            'ethereum': 'eth',
            'bsc': 'bsc',
            'solana': 'solana',
            'base': 'base',
            'arbitrum': 'arbitrum',
            'polygon': 'polygon_pos',
            'optimism': 'optimism',
            'avalanche': 'avax',
        }
        return chain_map.get(chain.lower(), chain.lower())
    
    def _get_explorer_url(self, chain: str, address: str) -> str:
        """Get block explorer URL for token address"""
        explorers = {
            'solana': f'https://solscan.io/token/{address}',
            'ethereum': f'https://etherscan.io/token/{address}',
            'bsc': f'https://bscscan.com/token/{address}',
            'base': f'https://basescan.org/token/{address}',
            'arbitrum': f'https://arbiscan.io/token/{address}',
            'polygon': f'https://polygonscan.com/token/{address}',
            'optimism': f'https://optimistic.etherscan.io/token/{address}',
            'avalanche': f'https://snowtrace.io/token/{address}',
        }
        return explorers.get(chain.lower(), f'https://dexscreener.com/{chain}/{address}')
    
    def _get_emoji_for_metric(self, value: float, metric_type: str) -> str:
        """Get color emoji based on metric value"""
        if metric_type == 'volume_velocity':
            if value >= 5: return "🔥"
            elif value >= 3: return "🟢"
            elif value >= 1.5: return "🟡"
            else: return "🟠"
        elif metric_type == 'buy_pressure':
            if value >= 2: return "🔥"
            elif value >= 0.8: return "🟢"
            elif value >= 0.5: return "🟡"
            else: return "🟠"
        elif metric_type == 'tx_growth':
            if value >= 3: return "🔥"
            elif value >= 1.5: return "🟢"
            elif value >= 0.8: return "🟡"
            else: return "🟠"
        elif metric_type == 'liquidity':
            if value >= 10: return "🔥"
            elif value >= 5: return "🟢"
            elif value >= 1: return "🟡"
            else: return "🟠"
        elif metric_type == 'alpha':
            if value >= 1.5: return "🔥"
            elif value >= 1.0: return "🟢"
            elif value >= 0.7: return "🟡"
            elif value >= 0.4: return "🟠"
            else: return "🔴"
        elif metric_type == 'pump_score':
            if value >= 0.7: return "🔥"
            elif value >= 0.5: return "🟢"
            elif value >= 0.4: return "🟡"
            elif value >= 0.3: return "🟠"
            else: return "🔴"
        return "📊"
    
    def _get_metric_comment(self, value: float, metric_type: str) -> str:
        """Get Russian comment for metric"""
        if metric_type == 'volume_velocity':
            if value >= 5: return "Объём взрывается — сильный интерес!"
            elif value >= 3: return "Хороший рост объёма"
            elif value >= 1.5: return "Умеренный рост"
            else: return "Слабый объём"
        elif metric_type == 'buy_pressure':
            if value >= 2: return "Покупатели давят — бычий импульс!"
            elif value >= 0.8: return "Преобладание покупателей"
            elif value >= 0.5: return "Небольшой перевес покупок"
            else: return "Давление продавцов"
        elif metric_type == 'tx_growth':
            if value >= 3: return "Ажиотаж в сети — активность растёт!"
            elif value >= 1.5: return "Хороший рост транзакций"
            elif value >= 0.8: return "Умеренная активность"
            else: return "Низкая активность"
        elif metric_type == 'liquidity':
            if value >= 10: return "Ликвидность сильно растёт!"
            elif value >= 5: return "Хороший приток ликвидности"
            elif value >= 1: return "Умеренный приток"
            else: return "Минимальные изменения"
        return "Нейтрально"
    
    def _get_whale_comment(self, has_whales: bool) -> str:
        """Get comment for whale activity"""
        if has_whales:
            return "Киты активны — крупные движения в пуле"
        return "Китов не замечено"
    
    def _get_signal_strength_text(self, alpha: float) -> tuple:
        """Get signal strength text and emoji"""
        if alpha >= 0.7:
            return "🔥 STRONG", "сильный сигнал — высокая уверенность"
        elif alpha >= 0.4:
            return "🟡 MEDIUM", "средний сигнал — возможен рост"
        else:
            return "🟠 WEAK", "слабый сигнал — нужны подтверждения"
    
    def _build_risk_bar(self, risk_score: int) -> str:
        """Build visual risk bar"""
        filled = min(risk_score // 10, 10)
        empty = 10 - filled
        bar = "▓" * filled + "░" * empty
        return f"{bar} {risk_score}/100"
    
    def _get_rug_risk_emoji(self, is_risk: bool) -> str:
        """Get rug pull risk emoji"""
        return "🔴 ВЫСОКИЙ" if is_risk else "🟢 Низкий"
    
    def _get_final_recommendation(self, alpha: float, risk_score: int, has_rug_risk: bool) -> str:
        """Get final recommendation text"""
        if has_rug_risk:
            return "⚠️ ВЫСОКИЙ РИСК — лучше пропустить"
        if alpha >= 1.0 and risk_score < 30:
            return "🚀 Сильный сигнал — можно входить рано"
        elif alpha >= 0.7 and risk_score < 50:
            return "📈 Хороший вход — наблюдать за подтверждениями"
        elif alpha >= 0.4:
            return "👀 Слабый сигнал — ждать дополнительных признаков"
        else:
            return "⏳ Наблюдать — сигнал слишком слабый"
    
    def _generate_explanation(self, signal_data: dict, signal_type: str) -> str:
        """Generate Russian explanation of what's happening"""
        metrics = signal_data.get('metrics', {})
        vv = metrics.get('volume_velocity', 0)
        bp = metrics.get('buy_pressure', 0)
        whale = metrics.get('whale_activity', False)
        
        parts = []
        
        if signal_type == 'PUMP':
            if vv >= 3 and bp >= 1.5:
                parts.append("Цена растёт на фоне взрывного объёма и сильного давления покупателей.")
            elif vv >= 2:
                parts.append("Объём торгов заметно вырос, цена следует за ним.")
            elif bp >= 1:
                parts.append("Покупатели активны, создавая бычий импульс.")
            else:
                parts.append("Фиксируется начало восходящего движения.")
            
            if whale:
                parts.append("Крупные игроки замечены в пуле — возможно инсайдерское движение.")
        
        else:  # DIP
            price_drop = metrics.get('price_drop', 0)
            if price_drop <= -15:
                parts.append(f"Резкая просадка {-price_drop:.1f}% при высоком объёме — возможен отскок.")
            else:
                parts.append(f"Коррекция {-price_drop:.1f}% с повышенной активностью.")
        
        return " ".join(parts) if parts else "Фиксируется необычная активность в пуле."
    
    async def send_pump_signal(self, signal_data: dict):
        """Send pump signal alert v2.0"""
        if not self.bot:
            return
        
        symbol = signal_data.get('symbol', 'Unknown')
        name = signal_data.get('name', symbol)
        chain = signal_data.get('chain', 'Unknown')
        price = signal_data.get('price', 0)
        address = signal_data.get('token_address', '')
        alpha_score = signal_data.get('alpha_score', 0)
        pump_score = signal_data.get('pump_score', 0)
        signal_strength = signal_data.get('signal_strength', 'UNKNOWN')
        
        metrics = signal_data.get('metrics', {})
        risk = signal_data.get('risk', {})
        
        # Metric values
        vv = metrics.get('volume_velocity', 0)
        bp = metrics.get('buy_pressure', 0)
        txg = metrics.get('tx_growth', 0)
        liq_vel = metrics.get('liquidity_velocity', 1)
        liq_inflow = (liq_vel - 1) * 100 if liq_vel > 1 else 0
        has_whales = metrics.get('whale_activity', False)
        
        # Risk values
        liq_ratio = risk.get('liquidity_ratio', 0) * 100
        has_rug_risk = risk.get('is_rug_pull_risk', False)
        risk_factors = risk.get('risk_factors', [])
        
        # Calculate risk score (0-100)
        risk_score = 0
        if has_rug_risk:
            risk_score += 50
        if liq_ratio < 5:
            risk_score += 30
        elif liq_ratio < 10:
            risk_score += 15
        risk_score = min(risk_score + len(risk_factors) * 5, 100)
        
        # URLs
        chain_dex = self._get_chain_dex_url(chain)
        chain_gecko = self._get_chain_gecko_url(chain)
        explorer_url = self._get_explorer_url(chain, address) if address else ""
        dex_url = f"https://dexscreener.com/{chain_dex}/{address}" if address else ""
        # GeckoTerminal: используем /tokens/ для адреса токена
        gecko_url = f"https://www.geckoterminal.com/{chain_gecko}/tokens/{address}" if address else ""
        
        # Emojis
        vv_emoji = self._get_emoji_for_metric(vv, 'volume_velocity')
        bp_emoji = self._get_emoji_for_metric(bp, 'buy_pressure')
        txg_emoji = self._get_emoji_for_metric(txg, 'tx_growth')
        liq_emoji = self._get_emoji_for_metric(liq_inflow, 'liquidity')
        alpha_emoji = self._get_emoji_for_metric(alpha_score, 'alpha')
        pump_emoji = self._get_emoji_for_metric(pump_score, 'pump_score')
        whales_emoji = "🐋🔥" if has_whales else "❌"
        
        # Comments
        vv_comment = self._get_metric_comment(vv, 'volume_velocity')
        bp_comment = self._get_metric_comment(bp, 'buy_pressure')
        txg_comment = self._get_metric_comment(txg, 'tx_growth')
        liq_comment = self._get_metric_comment(liq_inflow, 'liquidity')
        whales_comment = self._get_whale_comment(has_whales)
        
        # Signal strength
        sig_emoji, sig_text = self._get_signal_strength_text(alpha_score)
        
        # Risk bar
        risk_bar = self._build_risk_bar(risk_score)
        rug_emoji = self._get_rug_risk_emoji(has_rug_risk)
        
        # Explanation and recommendation
        explanation = self._generate_explanation(signal_data, 'PUMP')
        recommendation = self._get_final_recommendation(alpha_score, risk_score, has_rug_risk)
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Short address for display (first 6 + ... + last 4)
        short_address = f"{address[:6]}...{address[-4:]}" if len(address) > 12 else address
        
        message = f"""📊 <b>PUMP SIGNAL (RU v2.0)</b>

💠 <b>Токен:</b> {symbol} ({name})
🪙 <b>Сеть:</b> {chain}
💵 <b>Цена:</b> ${price:.8f}

📜 <b>Контракт:</b>
<a href='{explorer_url}'><code>{address}</code></a>

📋 <b>Копировать:</b> <code>{address}</code>

🔗 <b>Ссылки:</b>
• <a href='{dex_url}'>DexScreener</a>
• <a href='{gecko_url}'>GeckoTerminal</a>
• <a href='{explorer_url}'>Block Explorer</a>

────────────────────────
📈 <b>Что происходит:</b>
{explanation}

────────────────────────
📊 <b>Метрики:</b>

• Volume Velocity: {vv:.2f}x {vv_emoji}
  💬 Норма: 3–5x хорошо
  → {vv_comment}

• Buy Pressure: {bp:.2f} {bp_emoji}
  💬 Норма: &gt;0.6 хороший спрос
  → {bp_comment}

• Tx Growth: {txg:.2f}x {txg_emoji}
  💬 Норма: &gt;0.4
  → {txg_comment}

• Liquidity Inflow: {liq_inflow:.1f}% {liq_emoji}
  💬 Норма: 1–10%
  → {liq_comment}

• Whale Activity: {whales_emoji}
  → {whales_comment}

────────────────────────
🎚 <b>Оценки:</b>

🔥 Pump Score: {pump_score:.3f} {pump_emoji}
📈 Alpha Score: {alpha_score:.3f} {alpha_emoji}

📡 <b>Сила сигнала:</b> {sig_emoji}
• weak &lt; 0.4
• medium 0.4–0.7
• strong &gt; 0.7

────────────────────────
🛡️ <b>Риски:</b>

• Коэффициент ликвидности: {liq_ratio:.2f}%
• Rug Risk: {rug_emoji}
• Общий риск: {risk_score}/100

🎚 <b>Risk Bar:</b>
{risk_bar}

────────────────────────
📌 <b>Вывод:</b>
{recommendation}

────────────────────────
⏱️ <b>Время (UTC):</b> {timestamp}"""
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            logger.info(f"Pump signal v2.0 sent for {symbol}")
        except Exception as e:
            logger.error(f"Error sending pump signal v2.0: {e}")
    
    async def send_dip_signal(self, signal_data: dict):
        """Send dip recovery signal v2.0"""
        if not self.bot:
            return
        
        symbol = signal_data.get('symbol', 'Unknown')
        name = signal_data.get('name', symbol)
        chain = signal_data.get('chain', 'Unknown')
        price = signal_data.get('price', 0)
        address = signal_data.get('token_address', '')
        dip_score = signal_data.get('dip_score', 0)
        alpha_score = signal_data.get('alpha_score', 0)
        signal_strength = signal_data.get('signal_strength', 'UNKNOWN')
        
        metrics = signal_data.get('metrics', {})
        risk = signal_data.get('risk', {})
        
        # Metric values
        vv = metrics.get('volume_velocity', 0)
        price_drop = metrics.get('price_drop', 0)
        tx_spike = metrics.get('tx_spike', 0)
        liq_stability = metrics.get('liquidity_stability', 0.9)
        has_whales = metrics.get('whale_activity', False)
        
        # Risk values
        liq_ratio = risk.get('liquidity_ratio', 0) * 100
        has_rug_risk = risk.get('is_rug_pull_risk', False)
        risk_factors = risk.get('risk_factors', [])
        
        # Calculate risk score
        risk_score = 0
        if has_rug_risk:
            risk_score += 50
        if liq_ratio < 5:
            risk_score += 30
        elif liq_ratio < 10:
            risk_score += 15
        risk_score = min(risk_score + len(risk_factors) * 5, 100)
        
        # URLs
        chain_dex = self._get_chain_dex_url(chain)
        chain_gecko = self._get_chain_gecko_url(chain)
        explorer_url = self._get_explorer_url(chain, address) if address else ""
        dex_url = f"https://dexscreener.com/{chain_dex}/{address}" if address else ""
        # GeckoTerminal: используем /tokens/ для адреса токена
        gecko_url = f"https://www.geckoterminal.com/{chain_gecko}/tokens/{address}" if address else ""
        
        # Emojis
        vv_emoji = self._get_emoji_for_metric(vv, 'volume_velocity')
        alpha_emoji = self._get_emoji_for_metric(alpha_score, 'alpha')
        dip_emoji = self._get_emoji_for_metric(dip_score, 'pump_score')
        whales_emoji = "🐋🔥" if has_whales else "❌"
        
        # Signal strength
        sig_emoji, sig_text = self._get_signal_strength_text(alpha_score)
        
        # Risk bar
        risk_bar = self._build_risk_bar(risk_score)
        rug_emoji = self._get_rug_risk_emoji(has_rug_risk)
        
        # Explanation and recommendation
        explanation = self._generate_explanation(signal_data, 'DIP')
        recommendation = self._get_final_recommendation(alpha_score, risk_score, has_rug_risk)
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Short address for display
        short_address = f"{address[:6]}...{address[-4:]}" if len(address) > 12 else address
        
        message = f"""🎯 <b>DIP RECOVERY SIGNAL (RU v2.0)</b>

💠 <b>Токен:</b> {symbol} ({name})
🪙 <b>Сеть:</b> {chain}
💵 <b>Цена:</b> ${price:.8f}
📉 <b>Просадка:</b> {price_drop:.2f}%

📜 <b>Контракт:</b>
<a href='{explorer_url}'><code>{address}</code></a>

📋 <b>Копировать:</b> <code>{address}</code>

🔗 <b>Ссылки:</b>
• <a href='{dex_url}'>DexScreener</a>
• <a href='{gecko_url}'>GeckoTerminal</a>
• <a href='{explorer_url}'>Block Explorer</a>

────────────────────────
📈 <b>Что происходит:</b>
{explanation}

────────────────────────
📊 <b>Метрики восстановления:</b>

• Volume Spike: {vv:.2f}x {vv_emoji}
  💬 Высокий объём на просадке = интерес к покупке

• Tx Spike: {tx_spike:.2f}x
  💬 Активность трейдеров растёт

• Liquidity Stability: {liq_stability*100:.1f}%
  💬 Стабильность пула ликвидности

• Whale Activity: {whales_emoji}
  → {"Киты могут поддержать отскок" if has_whales else "Киты пока не активны"}

────────────────────────
🎚 <b>Оценки:</b>

🎯 Dip Score: {dip_score:.3f} {dip_emoji}
📈 Alpha Score: {alpha_score:.3f} {alpha_emoji}

📡 <b>Сила сигнала:</b> {sig_emoji}
• weak &lt; 0.4
• medium 0.4–0.7
• strong &gt; 0.7

────────────────────────
🛡️ <b>Риски:</b>

• Коэффициент ликвидности: {liq_ratio:.2f}%
• Rug Risk: {rug_emoji}
• Общий риск: {risk_score}/100

🎚 <b>Risk Bar:</b>
{risk_bar}

────────────────────────
📌 <b>Вывод:</b>
{recommendation}

────────────────────────
⏱️ <b>Время (UTC):</b> {timestamp}"""
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            logger.info(f"Dip signal v2.0 sent for {symbol}")
        except Exception as e:
            logger.error(f"Error sending dip signal v2.0: {e}")
    
    async def send_skipped_signal(self, skip_data: dict):
        """Send notification about skipped signal"""
        if not self.bot:
            return
        
        symbol = skip_data.get('symbol', 'Unknown')
        chain = skip_data.get('chain', 'Unknown')
        reason = skip_data.get('reason', 'unknown')
        
        message = f"""⚠️ <b>СИГНАЛ ПРОПУЩЕН</b>

🪙 <b>Токен:</b> {symbol}
🔗 <b>Сеть:</b> {chain}
📝 <b>Причина:</b> {reason}

<i>Сигнал не сохранён из-за некорректных метрик</i>"""
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Skipped signal notification sent for {symbol}")
        except Exception as e:
            logger.error(f"Error sending skipped signal notification: {e}")
    
    async def send_heartbeat(self, stats: dict):
        """Send hourly status update"""
        if not self.bot:
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        message = f"""⏱ <b>Crypto Hunter v2 — Heartbeat</b>

✅ <b>Статус:</b> Работает
📅 <b>Время:</b> {timestamp} UTC

📊 <b>Статистика сканирования:</b>
• Циклов выполнено: {stats.get('scan_count', 0)}
• Активных сетей: {stats.get('active_chains', 8)}
• Токенов (последний цикл): {stats.get('tokens_processed', 0)}

📈 <b>Сигналы:</b>
• Всего сгенерировано: {stats.get('total_signals', 0)}
• За последний час: {stats.get('signals_hour', 0)}
• PUMP: {stats.get('pump_signals', 0)} | DIP: {stats.get('dip_signals', 0)}

⚡ <b>Производительность:</b>
• Среднее время цикла: {stats.get('avg_cycle_time', 0):.1f}с
• Ошибок (24ч): {stats.get('errors_24h', 0)}

<i>Работает стабильно • Следующее сканирование через 30с</i>"""
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
            logger.info("Heartbeat v2.0 sent successfully")
        except Exception as e:
            logger.error(f"Error sending heartbeat: {e}")
    
    async def send_error_alert(self, error_msg: str):
        """Send error notification"""
        if not self.bot:
            return
        
        message = f"""⚠️ <b>Ошибка Сканера</b>

<code>{error_msg}</code>

<i>Попытка восстановления...</i>"""
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error sending error alert: {e}")
    
    async def send_test_signal_v2(self):
        """Send test signal in v2.0 format"""
        if not self.bot:
            logger.error("Bot not initialized")
            return
        
        test_data = {
            'symbol': 'PIKAHORSE',
            'name': 'Pika Horse Token',
            'chain': 'solana',
            'price': 0.00012345,
            'token_address': 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v',
            'alpha_score': 0.822,
            'pump_score': 0.425,
            'signal_strength': 'MEDIUM',
            'metrics': {
                'volume_velocity': 4.5,
                'buy_pressure': 1.8,
                'tx_growth': 2.3,
                'liquidity_velocity': 1.15,
                'whale_activity': True,
            },
            'risk': {
                'liquidity_ratio': 0.08,
                'is_rug_pull_risk': False,
                'risk_factors': [],
            },
            'signal_type': 'PUMP'
        }
        
        await self.send_pump_signal(test_data)
        logger.info("Test signal v2.0 sent")
