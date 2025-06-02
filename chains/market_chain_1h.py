"""
1시간 시장 분석 체인
- 1시간 봉 기술적 분석
- 단기 추세 및 모멘텀 분석
- 지지/저항 레벨 식별
- 결과 캐싱 (1.5시간 주기)
"""
import json
import time
import pandas as pd
import ccxt
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from langchain.prompts import ChatPromptTemplate

from config import Config
from llm_factory import create_llm
from utils.db import get_chain_db, log_chain


class MarketChain1H:
    """1시간 시장 분석 체인"""
    
    def __init__(self):
        """초기화"""
        self.db = get_chain_db()
        self.model_name = Config.get_chain_model("market_1h")
        self.settings = Config.get_chain_settings("market_1h")
        
        # 바이낸스 거래소 초기화 (데이터 수집용)
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        # LLM 생성
        try:
            self.llm = create_llm(self.model_name, **self.settings)
            log_chain("market_1h", "INFO", f"Initialized with model: {self.model_name}")
        except Exception as e:
            log_chain("market_1h", "ERROR", f"Failed to initialize LLM: {e}")
            raise
        
        # 분석 프롬프트
        self.analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert cryptocurrency technical analyst specializing in 1-hour timeframe analysis.

Analyze the provided 1-hour BTC/USDT candlestick data and provide a comprehensive technical analysis focused on short-term trading opportunities.

Key analysis points:
1. Price action and trend direction
2. Support and resistance levels
3. Momentum indicators (based on price movement patterns)
4. Volume analysis
5. Short-term trading signals

Your analysis should focus on:
- Current 1H trend direction and strength
- Key price levels for the next 2-4 hours
- Momentum shifts and reversal signals
- Entry/exit opportunities

Respond in JSON format:
{
  "trend_direction": "bullish/bearish/sideways",
  "trend_strength": 0.0-1.0,
  "support_levels": [price1, price2, price3],
  "resistance_levels": [price1, price2, price3],
  "momentum": "strong_bullish/bullish/neutral/bearish/strong_bearish",
  "volume_analysis": "increasing/decreasing/normal",
  "key_observations": ["observation1", "observation2"],
  "short_term_bias": "bullish/bearish/neutral",
  "confidence": 0.0-1.0,
  "next_targets": {
    "upside": [price1, price2],
    "downside": [price1, price2]
  },
  "summary": "2-3 sentence summary of 1H analysis"
}

Base your analysis on the actual price movements, highs, lows, and volume patterns shown in the data."""),
            ("human", "Analyze this 1-hour BTC/USDT data:\n\nCurrent Price: ${current_price}\n\nCandlestick Data:\n{candle_data}\n\nTechnical Indicators:\n{indicators}")
        ])
    
    def run(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        1시간 시장 분석 실행
        
        Args:
            force_refresh: 캐시 무시하고 강제 갱신
            
        Returns:
            1시간 시장 분석 결과
        """
        start_time = time.time()
        
        try:
            # 캐시된 결과 확인
            if not force_refresh:
                cached_result = self.db.get_latest_trend_summary("1h")
                if cached_result:
                    log_chain("market_1h", "INFO", "Using cached 1H analysis")
                    return {
                        "success": True,
                        "source": "cache",
                        "timestamp": cached_result["timestamp"],
                        "data": cached_result["trend"],
                        "confidence": cached_result["confidence"]
                    }
            
            # 시장 데이터 수집
            log_chain("market_1h", "INFO", "Collecting 1H market data")
            market_data = self._collect_market_data()
            
            if not market_data:
                log_chain("market_1h", "ERROR", "Failed to collect market data")
                return self._error_result("Failed to collect market data")
            
            # 기술적 지표 계산
            indicators = self._calculate_indicators(market_data["df"])
            
            # AI 분석
            log_chain("market_1h", "INFO", "Performing 1H technical analysis")
            analysis_result = self._analyze_market(market_data, indicators)
            
            # 결과 저장
            confidence = analysis_result.get("confidence", 0.5)
            self.db.save_trend_summary("1h", analysis_result, confidence)
            
            processing_time = time.time() - start_time
            log_chain("market_1h", "INFO", f"1H analysis completed in {processing_time:.2f}s")
            
            return {
                "success": True,
                "source": "fresh",
                "timestamp": datetime.now().isoformat(),
                "data": analysis_result,
                "confidence": confidence,
                "processing_time": processing_time
            }
            
        except Exception as e:
            log_chain("market_1h", "ERROR", f"1H market analysis failed: {e}")
            return self._error_result(str(e))
    
    def _collect_market_data(self) -> Optional[Dict[str, Any]]:
        """1시간 시장 데이터 수집"""
        try:
            # 1시간 봉 데이터 수집 (최근 48개)
            symbol = "BTC/USDT:USDT"  # 선물 심볼
            ohlcv = self.exchange.fetch_ohlcv(symbol, "1h", limit=48)
            
            if not ohlcv:
                return None
            
            # DataFrame 변환
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            # 현재가 조회
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker.get('mark', ticker['last'])
            
            return {
                "df": df,
                "current_price": current_price,
                "symbol": symbol,
                "data_points": len(df)
            }
            
        except Exception as e:
            log_chain("market_1h", "ERROR", f"Market data collection failed: {e}")
            return None
    
    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """기술적 지표 계산"""
        try:
            # 기본 이동평균
            df['sma_9'] = df['close'].rolling(window=9).mean()
            df['sma_21'] = df['close'].rolling(window=21).mean()
            
            # 단순 RSI 계산 (14 기간)
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # 볼린저 밴드 (20 기간, 2 표준편차)
            sma_20 = df['close'].rolling(window=20).mean()
            std_20 = df['close'].rolling(window=20).std()
            bb_upper = sma_20 + (std_20 * 2)
            bb_lower = sma_20 - (std_20 * 2)
            
            # 최신 값들
            latest = df.iloc[-1]
            
            indicators = {
                "current_price": float(latest['close']),
                "sma_9": float(latest.get('sma_9', 0) or 0),
                "sma_21": float(latest.get('sma_21', 0) or 0),
                "rsi": float(rsi.iloc[-1] if not rsi.empty else 50),
                "bb_upper": float(bb_upper.iloc[-1] if not bb_upper.empty else 0),
                "bb_lower": float(bb_lower.iloc[-1] if not bb_lower.empty else 0),
                "volume_avg": float(df['volume'].rolling(window=10).mean().iloc[-1]),
                "current_volume": float(latest['volume']),
                "price_change_1h": float((latest['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'] * 100),
                "price_change_4h": float((latest['close'] - df.iloc[-5]['close']) / df.iloc[-5]['close'] * 100) if len(df) >= 5 else 0,
                "high_24h": float(df['high'].tail(24).max()),
                "low_24h": float(df['low'].tail(24).min())
            }
            
            return indicators
            
        except Exception as e:
            log_chain("market_1h", "ERROR", f"Indicator calculation failed: {e}")
            return {"error": str(e)}
    
    def _analyze_market(self, market_data: Dict[str, Any], indicators: Dict[str, Any]) -> Dict[str, Any]:
        """AI를 통한 시장 분석"""
        try:
            df = market_data["df"]
            current_price = market_data["current_price"]
            
            # 캔들 데이터를 텍스트로 변환 (최근 12개만)
            recent_candles = df.tail(12)
            candle_text = ""
            
            for idx, row in recent_candles.iterrows():
                timestamp = row['timestamp'].strftime('%H:%M')
                candle_text += f"{timestamp}: O:{row['open']:.1f} H:{row['high']:.1f} L:{row['low']:.1f} C:{row['close']:.1f} V:{row['volume']:.0f}\n"
            
            # 지표 정보를 텍스트로 변환
            indicators_text = f"""
RSI(14): {indicators.get('rsi', 50):.1f}
SMA(9): {indicators.get('sma_9', 0):.1f}
SMA(21): {indicators.get('sma_21', 0):.1f}
Bollinger Upper: {indicators.get('bb_upper', 0):.1f}
Bollinger Lower: {indicators.get('bb_lower', 0):.1f}
Volume (current): {indicators.get('current_volume', 0):.0f}
Volume (avg): {indicators.get('volume_avg', 0):.0f}
1H Change: {indicators.get('price_change_1h', 0):.2f}%
4H Change: {indicators.get('price_change_4h', 0):.2f}%
24H High: {indicators.get('high_24h', 0):.1f}
24H Low: {indicators.get('low_24h', 0):.1f}
"""
            
            # AI 분석 요청
            messages = self.analysis_prompt.format_messages(
                current_price=f"{current_price:,.2f}",
                candle_data=candle_text,
                indicators=indicators_text
            )
            
            response = self.llm.invoke(messages)
            response_text = response.content.strip()
            
            # JSON 응답 정리
            if "```json" in response_text:
                start_idx = response_text.find("```json") + 7
                end_idx = response_text.find("```", start_idx)
                if end_idx != -1:
                    response_text = response_text[start_idx:end_idx].strip()
            elif "```" in response_text:
                parts = response_text.split("```")
                if len(parts) >= 3:
                    response_text = parts[1].strip()
            
            analysis_result = json.loads(response_text)
            
            # 결과 검증 및 보강
            analysis_result = self._validate_analysis_result(analysis_result, indicators)
            
            log_chain("market_1h", "INFO", f"1H Analysis: {analysis_result['trend_direction']} trend, {analysis_result['confidence']:.2f} confidence")
            return analysis_result
            
        except json.JSONDecodeError as e:
            log_chain("market_1h", "ERROR", f"Failed to parse AI response: {e}")
            return self._fallback_analysis(indicators)
        except Exception as e:
            log_chain("market_1h", "ERROR", f"Market analysis failed: {e}")
            return self._fallback_analysis(indicators)
    
    def _validate_analysis_result(self, result: Dict[str, Any], indicators: Dict[str, Any]) -> Dict[str, Any]:
        """분석 결과 검증 및 기본값 설정"""
        current_price = indicators.get('current_price', 50000)
        
        # 기본값 설정
        defaults = {
            "trend_direction": "sideways",
            "trend_strength": 0.5,
            "support_levels": [current_price * 0.98, current_price * 0.96, current_price * 0.94],
            "resistance_levels": [current_price * 1.02, current_price * 1.04, current_price * 1.06],
            "momentum": "neutral",
            "volume_analysis": "normal",
            "key_observations": [],
            "short_term_bias": "neutral",
            "confidence": 0.5,
            "next_targets": {
                "upside": [current_price * 1.02, current_price * 1.04],
                "downside": [current_price * 0.98, current_price * 0.96]
            },
            "summary": "1-hour technical analysis shows mixed signals"
        }
        
        # 기본값으로 채우기
        for key, default_value in defaults.items():
            if key not in result:
                result[key] = default_value
        
        # 값 범위 검증
        result["trend_strength"] = max(0.0, min(1.0, result.get("trend_strength", 0.5)))
        result["confidence"] = max(0.0, min(1.0, result.get("confidence", 0.5)))
        
        # 가격 레벨 검증 (현재가 ±20% 범위 내)
        price_min = current_price * 0.8
        price_max = current_price * 1.2
        
        if "support_levels" in result:
            result["support_levels"] = [max(price_min, min(price_max, price)) for price in result["support_levels"][:3]]
        
        if "resistance_levels" in result:
            result["resistance_levels"] = [max(price_min, min(price_max, price)) for price in result["resistance_levels"][:3]]
        
        # 유효한 방향값 검증
        valid_directions = ["bullish", "bearish", "sideways"]
        if result.get("trend_direction") not in valid_directions:
            result["trend_direction"] = "sideways"
        
        valid_bias = ["bullish", "bearish", "neutral"]
        if result.get("short_term_bias") not in valid_bias:
            result["short_term_bias"] = "neutral"
        
        return result
    
    def _fallback_analysis(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """AI 분석 실패시 폴백 분석"""
        current_price = indicators.get('current_price', 50000)
        rsi = indicators.get('rsi', 50)
        sma_9 = indicators.get('sma_9', current_price)
        sma_21 = indicators.get('sma_21', current_price)
        price_change_1h = indicators.get('price_change_1h', 0)
        
        # 간단한 추세 판정
        if current_price > sma_9 > sma_21 and rsi > 55:
            trend_direction = "bullish"
            trend_strength = 0.7
            short_term_bias = "bullish"
        elif current_price < sma_9 < sma_21 and rsi < 45:
            trend_direction = "bearish"
            trend_strength = 0.7
            short_term_bias = "bearish"
        else:
            trend_direction = "sideways"
            trend_strength = 0.4
            short_term_bias = "neutral"
        
        # 모멘텀 판정
        if price_change_1h > 2:
            momentum = "strong_bullish"
        elif price_change_1h > 0.5:
            momentum = "bullish"
        elif price_change_1h < -2:
            momentum = "strong_bearish"
        elif price_change_1h < -0.5:
            momentum = "bearish"
        else:
            momentum = "neutral"
        
        return {
            "trend_direction": trend_direction,
            "trend_strength": trend_strength,
            "support_levels": [current_price * 0.99, current_price * 0.97, current_price * 0.95],
            "resistance_levels": [current_price * 1.01, current_price * 1.03, current_price * 1.05],
            "momentum": momentum,
            "volume_analysis": "normal",
            "key_observations": ["fallback_analysis"],
            "short_term_bias": short_term_bias,
            "confidence": 0.3,  # 낮은 신뢰도
            "next_targets": {
                "upside": [current_price * 1.02, current_price * 1.04],
                "downside": [current_price * 0.98, current_price * 0.96]
            },
            "summary": f"Fallback analysis: {trend_direction} trend with {momentum} momentum"
        }
    
    def _error_result(self, error_msg: str) -> Dict[str, Any]:
        """에러 결과 반환"""
        return {
            "success": False,
            "source": "error",
            "error": error_msg,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "trend_direction": "sideways",
                "confidence": 0.0,
                "summary": "Error occurred during 1H market analysis"
            },
            "confidence": 0.0
        }


# 편의 함수들
def run_1h_analysis(force_refresh: bool = False) -> Dict[str, Any]:
    """1시간 분석 실행 편의 함수"""
    chain = MarketChain1H()
    return chain.run(force_refresh)


def get_1h_trend() -> str:
    """1시간 추세 방향만 반환"""
    db = get_chain_db()
    trend_summary = db.get_latest_trend_summary("1h")
    if trend_summary:
        return trend_summary["trend"].get("trend_direction", "sideways")
    return "sideways"


def get_1h_support_resistance() -> Dict[str, List[float]]:
    """1시간 지지/저항 레벨 반환"""
    db = get_chain_db()
    trend_summary = db.get_latest_trend_summary("1h")
    
    if trend_summary:
        trend_data = trend_summary["trend"]
        return {
            "support": trend_data.get("support_levels", []),
            "resistance": trend_data.get("resistance_levels", [])
        }
    return {"support": [], "resistance": []}


def print_1h_summary() -> None:
    """1시간 분석 요약 출력"""
    db = get_chain_db()
    trend_summary = db.get_latest_trend_summary("1h")
    
    if trend_summary:
        data = trend_summary["trend"]
        print(f"\n📈 1H Market Analysis")
        print(f"Trend: {data['trend_direction']} (strength: {data.get('trend_strength', 0.5):.2f})")
        print(f"Momentum: {data.get('momentum', 'neutral')}")
        print(f"Short-term Bias: {data.get('short_term_bias', 'neutral')}")
        print(f"Confidence: {trend_summary['confidence']:.2f}")
        print(f"Summary: {data.get('summary', 'No summary available')}")
    else:
        print("\n📈 No recent 1H analysis available")