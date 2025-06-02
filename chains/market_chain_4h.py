"""
4시간 시장 분석 체인 - 에러 수정
- DataFrame 생성 안전 처리
- 변수 스코프 문제 해결
- 메모리 관리 개선
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


class MarketChain4H:
    """4시간 시장 분석 체인 - 안정성 개선"""
    
    def __init__(self):
        """초기화"""
        self.db = get_chain_db()
        self.model_name = Config.get_chain_model("market_4h")
        self.settings = Config.get_chain_settings("market_4h")
        
        # 바이낸스 거래소 초기화
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })
        
        # LLM 생성
        try:
            self.llm = create_llm(self.model_name, **self.settings)
            log_chain("market_4h", "INFO", f"Initialized with model: {self.model_name}")
        except Exception as e:
            log_chain("market_4h", "ERROR", f"Failed to initialize LLM: {e}")
            raise
        
        # 분석 프롬프트
        self.analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a senior cryptocurrency technical analyst specializing in 4-hour timeframe analysis for medium-term trading strategies.

Analyze the provided 4-hour BTC/USDT data to identify structural trends, key levels, and medium-term opportunities.

Key focus areas:
1. Primary trend direction and structural changes
2. Major support/resistance zones
3. Market structure (higher highs/lower lows)
4. Volume confirmation and divergences
5. Multi-timeframe context (daily alignment)
6. Swing trading opportunities

Your analysis should emphasize:
- Structural trend changes and confirmations
- Key weekly/daily levels interaction
- Market cycles and phases
- Medium-term risk/reward setups
- Institutional interest levels

Respond in JSON format:
{
  "primary_trend": "strong_bullish/bullish/neutral/bearish/strong_bearish",
  "trend_confidence": 0.0-1.0,
  "market_structure": "higher_highs_lows/lower_highs_lows/consolidation/distribution",
  "major_support": [price1, price2],
  "major_resistance": [price1, price2],
  "weekly_bias": "bullish/bearish/neutral",
  "daily_alignment": "aligned/conflicted/neutral",
  "cycle_phase": "accumulation/markup/distribution/markdown",
  "volume_confirmation": "strong/weak/neutral",
  "swing_opportunity": {
    "direction": "long/short/none",
    "entry_zone": [price1, price2],
    "target_zone": [price1, price2],
    "invalidation": price
  },
  "risk_assessment": "low/medium/high",
  "key_levels": {
    "critical_support": price,
    "critical_resistance": price,
    "breakout_level": price
  },
  "medium_term_outlook": "bullish/bearish/neutral",
  "confidence": 0.0-1.0,
  "summary": "3-4 sentence analysis of 4H structure and outlook"
}

Focus on structural analysis rather than short-term noise. Identify key zones where institutional participants would likely act."""),
            ("human", "Analyze this 4-hour BTC/USDT data:\n\nCurrent Price: ${current_price}\n\n4H Candlestick Data:\n{candle_data}\n\nStructural Analysis:\n{structure_data}\n\nVolume & Momentum:\n{momentum_data}")
        ])
    
    def run(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        4시간 시장 분석 실행
        
        Args:
            force_refresh: 캐시 무시하고 강제 갱신
            
        Returns:
            4시간 시장 분석 결과
        """
        start_time = time.time()
        
        try:
            # 캐시된 결과 확인
            if not force_refresh:
                cached_result = self.db.get_latest_trend_summary("4h")
                if cached_result:
                    log_chain("market_4h", "INFO", "Using cached 4H analysis")
                    return {
                        "success": True,
                        "source": "cache",
                        "timestamp": cached_result["timestamp"],
                        "data": cached_result["trend"],
                        "confidence": cached_result["confidence"]
                    }
            
            # 시장 데이터 수집
            log_chain("market_4h", "INFO", "Collecting 4H market data")
            market_data = self._collect_market_data()
            
            if not market_data:
                log_chain("market_4h", "ERROR", "Failed to collect market data")
                return self._error_result("Failed to collect market data")
            
            # 구조적 분석 데이터 계산
            structure_analysis = self._analyze_structure(market_data["df_4h"])
            momentum_analysis = self._analyze_momentum(market_data["df_4h"])
            
            # AI 분석
            log_chain("market_4h", "INFO", "Performing 4H structural analysis")
            analysis_result = self._analyze_market(market_data, structure_analysis, momentum_analysis)
            
            # 결과 저장
            confidence = analysis_result.get("confidence", 0.5)
            self.db.save_trend_summary("4h", analysis_result, confidence)
            
            processing_time = time.time() - start_time
            log_chain("market_4h", "INFO", f"4H analysis completed in {processing_time:.2f}s")
            
            return {
                "success": True,
                "source": "fresh",
                "timestamp": datetime.now().isoformat(),
                "data": analysis_result,
                "confidence": confidence,
                "processing_time": processing_time
            }
            
        except Exception as e:
            log_chain("market_4h", "ERROR", f"4H market analysis failed: {e}")
            return self._error_result(str(e))
    
    def _collect_market_data(self) -> Optional[Dict[str, Any]]:
        """4시간 시장 데이터 수집 - 안전성 강화"""
        df_4h = None
        df_1d = None
        
        try:
            symbol = "BTC/USDT:USDT"
            
            # 4시간 봉 데이터 (최근 90개 = 15일)
            log_chain("market_4h", "INFO", "Fetching 4H OHLCV data")
            ohlcv_4h = self.exchange.fetch_ohlcv(symbol, "4h", limit=90)
            
            if not ohlcv_4h or len(ohlcv_4h) < 10:
                log_chain("market_4h", "ERROR", f"Insufficient 4H data: {len(ohlcv_4h) if ohlcv_4h else 0} candles")
                return None
            
            # 일봉 데이터 (최근 30개 = 30일)
            log_chain("market_4h", "INFO", "Fetching 1D OHLCV data")
            ohlcv_1d = self.exchange.fetch_ohlcv(symbol, "1d", limit=30)
            
            if not ohlcv_1d or len(ohlcv_1d) < 5:
                log_chain("market_4h", "ERROR", f"Insufficient 1D data: {len(ohlcv_1d) if ohlcv_1d else 0} candles")
                return None
            
            # DataFrame 변환 (안전한 방식)
            try:
                df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df_4h['timestamp'] = pd.to_datetime(df_4h['timestamp'], unit='ms')
                
                df_1d = pd.DataFrame(ohlcv_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df_1d['timestamp'] = pd.to_datetime(df_1d['timestamp'], unit='ms')
                
                # 데이터 검증
                if df_4h.empty or df_1d.empty:
                    log_chain("market_4h", "ERROR", "Empty DataFrame after conversion")
                    return None
                
                # NaN 값 체크
                if df_4h.isnull().any().any() or df_1d.isnull().any().any():
                    log_chain("market_4h", "WARNING", "NaN values detected in data")
                    df_4h = df_4h.dropna()
                    df_1d = df_1d.dropna()
                
            except Exception as e:
                log_chain("market_4h", "ERROR", f"DataFrame conversion failed: {e}")
                return None
            
            # 현재가 조회
            try:
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker.get('mark', ticker['last'])
                
                if not current_price or current_price <= 0:
                    log_chain("market_4h", "ERROR", f"Invalid current price: {current_price}")
                    return None
                    
            except Exception as e:
                log_chain("market_4h", "ERROR", f"Current price fetch failed: {e}")
                return None
            
            result = {
                "df_4h": df_4h,
                "df_1d": df_1d,
                "current_price": current_price,
                "symbol": symbol,
                "data_points_4h": len(df_4h),
                "data_points_1d": len(df_1d)
            }
            
            log_chain("market_4h", "INFO", f"Market data collected: {len(df_4h)} 4H candles, {len(df_1d)} 1D candles")
            return result
            
        except Exception as e:
            log_chain("market_4h", "ERROR", f"Market data collection failed: {e}")
            return None
        finally:
            # 메모리 정리는 하지 않음 (사용 중인 데이터이므로)
            pass
    
    def _analyze_structure(self, df_4h: pd.DataFrame) -> Dict[str, Any]:
        """시장 구조 분석 - 안전한 처리"""
        structure_data = {}
        
        try:
            if df_4h is None or df_4h.empty:
                log_chain("market_4h", "ERROR", "Empty DataFrame for structure analysis")
                return {"error": "Empty DataFrame"}
            
            # DataFrame 복사본 사용 (원본 보호)
            df = df_4h.copy()
            
            # 이동평균들
            df['ema_20'] = df['close'].ewm(span=20).mean()
            df['ema_50'] = df['close'].ewm(span=50).mean()
            
            # 200 SMA (충분한 데이터가 있을 때만)
            if len(df) >= 200:
                df['sma_200'] = df['close'].rolling(window=200).mean()
            else:
                df['sma_200'] = df['close'].mean()  # 평균값으로 대체
            
            # 최근 스윙 고점/저점 찾기 (안전한 방법)
            try:
                recent_data = df.tail(min(30, len(df)))  # 최대 30개 또는 전체 데이터
                
                if len(recent_data) >= 5:
                    highs = recent_data['high'].rolling(window=5, center=True).max()
                    lows = recent_data['low'].rolling(window=5, center=True).min()
                    
                    swing_highs = recent_data[recent_data['high'] == highs]['high'].tolist()
                    swing_lows = recent_data[recent_data['low'] == lows]['low'].tolist()
                else:
                    swing_highs = [recent_data['high'].max()]
                    swing_lows = [recent_data['low'].min()]
                    
            except Exception as e:
                log_chain("market_4h", "WARNING", f"Swing analysis failed: {e}")
                swing_highs = [df['high'].max()]
                swing_lows = [df['low'].min()]
            
            # 최신 값들 (안전한 접근)
            latest = df.iloc[-1]
            
            structure_data = {
                "current_price": float(latest['close']),
                "ema_20": float(latest.get('ema_20', latest['close'])),
                "ema_50": float(latest.get('ema_50', latest['close'])),
                "sma_200": float(latest.get('sma_200', latest['close'])),
                "recent_swing_highs": sorted(swing_highs[-3:], reverse=True) if swing_highs else [float(latest['close'])],
                "recent_swing_lows": sorted(swing_lows[-3:]) if swing_lows else [float(latest['close'])],
                "price_vs_ema20": "above" if latest['close'] > latest.get('ema_20', latest['close']) else "below",
                "ema20_vs_ema50": "above" if latest.get('ema_20', 0) > latest.get('ema_50', 0) else "below",
                "distance_from_200sma": float((latest['close'] - latest.get('sma_200', latest['close'])) / latest['close'] * 100),
                "weekly_high": float(df['high'].tail(min(42, len(df))).max()),  # 7일 = 42개 4시간봉
                "weekly_low": float(df['low'].tail(min(42, len(df))).min()),
                "monthly_high": float(df['high'].tail(min(180, len(df))).max()),  # 30일 = 180개 4시간봉
                "monthly_low": float(df['low'].tail(min(180, len(df))).min())
            }
            
            return structure_data
            
        except Exception as e:
            log_chain("market_4h", "ERROR", f"Structure analysis failed: {e}")
            return {"error": str(e)}
    
    def _analyze_momentum(self, df_4h: pd.DataFrame) -> Dict[str, Any]:
        """모멘텀 및 볼륨 분석 - 안전한 처리"""
        try:
            if df_4h is None or df_4h.empty:
                log_chain("market_4h", "ERROR", "Empty DataFrame for momentum analysis")
                return {"error": "Empty DataFrame"}
            
            # DataFrame 복사본 사용
            df = df_4h.copy()
            
            # RSI 계산 (안전한 방식)
            try:
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=min(14, len(df))).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=min(14, len(df))).mean()
                
                # 0으로 나누기 방지
                rs = gain / loss.replace(0, 1e-10)
                rsi = 100 - (100 / (1 + rs))
                
            except Exception as e:
                log_chain("market_4h", "WARNING", f"RSI calculation failed: {e}")
                rsi = pd.Series([50] * len(df), index=df.index)  # 기본값 50
            
            # MACD 계산 (안전한 방식)
            try:
                ema_12 = df['close'].ewm(span=12).mean()
                ema_26 = df['close'].ewm(span=26).mean()
                macd_line = ema_12 - ema_26
                signal_line = macd_line.ewm(span=9).mean()
                
            except Exception as e:
                log_chain("market_4h", "WARNING", f"MACD calculation failed: {e}")
                macd_line = pd.Series([0] * len(df), index=df.index)
                signal_line = pd.Series([0] * len(df), index=df.index)
            
            # 볼륨 분석
            try:
                volume_sma = df['volume'].rolling(window=min(20, len(df))).mean()
            except Exception as e:
                log_chain("market_4h", "WARNING", f"Volume analysis failed: {e}")
                volume_sma = df['volume']
            
            # 최신 값들 (안전한 접근)
            latest = df.iloc[-1]
            
            momentum_data = {
                "rsi": float(rsi.iloc[-1] if not rsi.empty and not pd.isna(rsi.iloc[-1]) else 50),
                "macd_line": float(macd_line.iloc[-1] if not macd_line.empty and not pd.isna(macd_line.iloc[-1]) else 0),
                "signal_line": float(signal_line.iloc[-1] if not signal_line.empty and not pd.isna(signal_line.iloc[-1]) else 0),
                "macd_histogram": float((macd_line.iloc[-1] - signal_line.iloc[-1]) if not macd_line.empty and not signal_line.empty else 0),
                "volume_ratio": float(latest['volume'] / volume_sma.iloc[-1] if not volume_sma.empty and volume_sma.iloc[-1] > 0 else 1),
                "price_change_4h": float((latest['close'] - df.iloc[-2]['close']) / df.iloc[-2]['close'] * 100) if len(df) >= 2 else 0,
                "price_change_24h": float((latest['close'] - df.iloc[-7]['close']) / df.iloc[-7]['close'] * 100) if len(df) >= 7 else 0,
                "price_change_7d": float((latest['close'] - df.iloc[-43]['close']) / df.iloc[-43]['close'] * 100) if len(df) >= 43 else 0,
                "volume_trend": "increasing" if latest['volume'] > volume_sma.iloc[-1] * 1.2 else "decreasing" if latest['volume'] < volume_sma.iloc[-1] * 0.8 else "normal"
            }
            
            return momentum_data
            
        except Exception as e:
            log_chain("market_4h", "ERROR", f"Momentum analysis failed: {e}")
            return {"error": str(e)}
    
    def _analyze_market(self, market_data: Dict[str, Any], structure_data: Dict[str, Any], momentum_data: Dict[str, Any]) -> Dict[str, Any]:
        """AI를 통한 4시간 시장 분석"""
        try:
            df_4h = market_data["df_4h"]
            current_price = market_data["current_price"]
            
            # 에러가 있는지 체크
            if "error" in structure_data or "error" in momentum_data:
                log_chain("market_4h", "ERROR", "Structure or momentum analysis failed")
                return self._fallback_analysis(structure_data, momentum_data, current_price)
            
            # 최근 4시간 캔들 데이터 (최근 20개)
            recent_candles = df_4h.tail(min(20, len(df_4h)))
            candle_text = ""
            
            for idx, row in recent_candles.iterrows():
                timestamp = row['timestamp'].strftime('%m/%d %H:%M')
                candle_text += f"{timestamp}: O:{row['open']:.0f} H:{row['high']:.0f} L:{row['low']:.0f} C:{row['close']:.0f} V:{row['volume']:.0f}\n"
            
            # 구조적 분석 데이터
            structure_text = f"""
EMA(20): {structure_data.get('ema_20', 0):.0f}
EMA(50): {structure_data.get('ema_50', 0):.0f}
SMA(200): {structure_data.get('sma_200', 0):.0f}
Price vs EMA20: {structure_data.get('price_vs_ema20', 'unknown')}
EMA20 vs EMA50: {structure_data.get('ema20_vs_ema50', 'unknown')}
Distance from 200SMA: {structure_data.get('distance_from_200sma', 0):.1f}%
Weekly High: {structure_data.get('weekly_high', 0):.0f}
Weekly Low: {structure_data.get('weekly_low', 0):.0f}
Monthly High: {structure_data.get('monthly_high', 0):.0f}
Monthly Low: {structure_data.get('monthly_low', 0):.0f}
Recent Swing Highs: {structure_data.get('recent_swing_highs', [])}
Recent Swing Lows: {structure_data.get('recent_swing_lows', [])}
"""
            
            # 모멘텀 데이터
            momentum_text = f"""
RSI(14): {momentum_data.get('rsi', 50):.1f}
MACD Line: {momentum_data.get('macd_line', 0):.1f}
Signal Line: {momentum_data.get('signal_line', 0):.1f}
MACD Histogram: {momentum_data.get('macd_histogram', 0):.1f}
Volume Ratio: {momentum_data.get('volume_ratio', 1):.2f}
Volume Trend: {momentum_data.get('volume_trend', 'normal')}
4H Change: {momentum_data.get('price_change_4h', 0):.2f}%
24H Change: {momentum_data.get('price_change_24h', 0):.2f}%
7D Change: {momentum_data.get('price_change_7d', 0):.2f}%
"""
            
            # AI 분석 요청
            messages = self.analysis_prompt.format_messages(
                current_price=f"{current_price:,.0f}",
                candle_data=candle_text,
                structure_data=structure_text,
                momentum_data=momentum_text
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
            analysis_result = self._validate_analysis_result(analysis_result, structure_data, momentum_data)
            
            log_chain("market_4h", "INFO", f"4H Analysis: {analysis_result['primary_trend']} trend, {analysis_result['confidence']:.2f} confidence")
            return analysis_result
            
        except json.JSONDecodeError as e:
            log_chain("market_4h", "ERROR", f"Failed to parse AI response: {e}")
            return self._fallback_analysis(structure_data, momentum_data, current_price)
        except Exception as e:
            log_chain("market_4h", "ERROR", f"Market analysis failed: {e}")
            return self._fallback_analysis(structure_data, momentum_data, current_price)
    
    def _validate_analysis_result(self, result: Dict[str, Any], structure_data: Dict[str, Any], momentum_data: Dict[str, Any]) -> Dict[str, Any]:
        """분석 결과 검증 및 기본값 설정"""
        current_price = structure_data.get('current_price', 50000)
        
        # 기본값 설정
        defaults = {
            "primary_trend": "neutral",
            "trend_confidence": 0.5,
            "market_structure": "consolidation",
            "major_support": [current_price * 0.95, current_price * 0.90],
            "major_resistance": [current_price * 1.05, current_price * 1.10],
            "weekly_bias": "neutral",
            "daily_alignment": "neutral",
            "cycle_phase": "consolidation",
            "volume_confirmation": "neutral",
            "swing_opportunity": {
                "direction": "none",
                "entry_zone": [current_price * 0.99, current_price * 1.01],
                "target_zone": [current_price * 1.02, current_price * 1.05],
                "invalidation": current_price * 0.95
            },
            "risk_assessment": "medium",
            "key_levels": {
                "critical_support": current_price * 0.95,
                "critical_resistance": current_price * 1.05,
                "breakout_level": current_price * 1.02
            },
            "medium_term_outlook": "neutral",
            "confidence": 0.5,
            "summary": "4-hour analysis shows consolidation with mixed signals"
        }
        
        # 기본값으로 채우기
        for key, default_value in defaults.items():
            if key not in result:
                result[key] = default_value
        
        # 값 범위 검증
        result["trend_confidence"] = max(0.0, min(1.0, result.get("trend_confidence", 0.5)))
        result["confidence"] = max(0.0, min(1.0, result.get("confidence", 0.5)))
        
        # 가격 레벨 검증 (현재가 ±30% 범위 내)
        price_min = current_price * 0.7
        price_max = current_price * 1.3
        
        if "major_support" in result and isinstance(result["major_support"], list):
            result["major_support"] = [max(price_min, min(price_max, price)) for price in result["major_support"][:2]]
        
        if "major_resistance" in result and isinstance(result["major_resistance"], list):
            result["major_resistance"] = [max(price_min, min(price_max, price)) for price in result["major_resistance"][:2]]
        
        # 유효한 enum 값 검증
        valid_trends = ["strong_bullish", "bullish", "neutral", "bearish", "strong_bearish"]
        if result.get("primary_trend") not in valid_trends:
            result["primary_trend"] = "neutral"
        
        valid_structures = ["higher_highs_lows", "lower_highs_lows", "consolidation", "distribution"]
        if result.get("market_structure") not in valid_structures:
            result["market_structure"] = "consolidation"
        
        valid_bias = ["bullish", "bearish", "neutral"]
        if result.get("weekly_bias") not in valid_bias:
            result["weekly_bias"] = "neutral"
        
        return result
    
    def _fallback_analysis(self, structure_data: Dict[str, Any], momentum_data: Dict[str, Any], current_price: float = None) -> Dict[str, Any]:
        """AI 분석 실패시 폴백 분석"""
        if current_price is None:
            current_price = structure_data.get('current_price', 50000)
        
        ema_20 = structure_data.get('ema_20', current_price)
        ema_50 = structure_data.get('ema_50', current_price)
        rsi = momentum_data.get('rsi', 50)
        price_change_7d = momentum_data.get('price_change_7d', 0)
        
        # 간단한 추세 판정
        if current_price > ema_20 > ema_50 and rsi > 60 and price_change_7d > 5:
            primary_trend = "strong_bullish"
            trend_confidence = 0.8
        elif current_price > ema_20 and rsi > 50:
            primary_trend = "bullish"
            trend_confidence = 0.6
        elif current_price < ema_20 < ema_50 and rsi < 40 and price_change_7d < -5:
            primary_trend = "strong_bearish"
            trend_confidence = 0.8
        elif current_price < ema_20 and rsi < 50:
            primary_trend = "bearish"
            trend_confidence = 0.6
        else:
            primary_trend = "neutral"
            trend_confidence = 0.4
        
        return {
            "primary_trend": primary_trend,
            "trend_confidence": trend_confidence,
            "market_structure": "consolidation",
            "major_support": [current_price * 0.95, current_price * 0.90],
            "major_resistance": [current_price * 1.05, current_price * 1.10],
            "weekly_bias": "neutral",
            "daily_alignment": "neutral",
            "cycle_phase": "consolidation",
            "volume_confirmation": "neutral",
            "swing_opportunity": {
                "direction": "none",
                "entry_zone": [current_price * 0.99, current_price * 1.01],
                "target_zone": [current_price * 1.02, current_price * 1.05],
                "invalidation": current_price * 0.95
            },
            "risk_assessment": "medium",
            "key_levels": {
                "critical_support": ema_20,
                "critical_resistance": current_price * 1.05,
                "breakout_level": current_price * 1.02
            },
            "medium_term_outlook": primary_trend.replace("strong_", ""),
            "confidence": 0.3,  # 낮은 신뢰도
            "summary": f"Fallback analysis: {primary_trend} trend with {trend_confidence:.1f} confidence based on EMA and RSI"
        }
    
    def _error_result(self, error_msg: str) -> Dict[str, Any]:
        """에러 결과 반환"""
        return {
            "success": False,
            "source": "error",
            "error": error_msg,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "primary_trend": "neutral",
                "confidence": 0.0,
                "summary": "Error occurred during 4H market analysis"
            },
            "confidence": 0.0
        }


# 편의 함수들
def run_4h_analysis(force_refresh: bool = False) -> Dict[str, Any]:
    """4시간 분석 실행 편의 함수"""
    chain = MarketChain4H()
    return chain.run(force_refresh)


def get_4h_trend() -> str:
    """4시간 주요 추세 반환"""
    db = get_chain_db()
    trend_summary = db.get_latest_trend_summary("4h")
    if trend_summary:
        return trend_summary["trend"].get("primary_trend", "neutral")
    return "neutral"


def get_4h_key_levels() -> Dict[str, float]:
    """4시간 핵심 레벨 반환"""
    db = get_chain_db()
    trend_summary = db.get_latest_trend_summary("4h")
    
    if trend_summary:
        data = trend_summary["trend"]
        key_levels = data.get("key_levels", {})
        return {
            "critical_support": key_levels.get("critical_support", 0),
            "critical_resistance": key_levels.get("critical_resistance", 0),
            "breakout_level": key_levels.get("breakout_level", 0)
        }
    return {"critical_support": 0, "critical_resistance": 0, "breakout_level": 0}


def get_swing_opportunity() -> Dict[str, Any]:
    """4시간 스윙 기회 반환"""
    db = get_chain_db()
    trend_summary = db.get_latest_trend_summary("4h")
    
    if trend_summary:
        return trend_summary["trend"].get("swing_opportunity", {"direction": "none"})
    return {"direction": "none"}


def print_4h_summary() -> None:
    """4시간 분석 요약 출력"""
    db = get_chain_db()
    trend_summary = db.get_latest_trend_summary("4h")
    
    if trend_summary:
        data = trend_summary["trend"]
        print(f"\n📊 4H Market Analysis")
        print(f"Primary Trend: {data['primary_trend']} (confidence: {data.get('trend_confidence', 0.5):.2f})")
        print(f"Market Structure: {data.get('market_structure', 'unknown')}")
        print(f"Weekly Bias: {data.get('weekly_bias', 'neutral')}")
        print(f"Cycle Phase: {data.get('cycle_phase', 'unknown')}")
        print(f"Swing Opportunity: {data.get('swing_opportunity', {}).get('direction', 'none')}")
        print(f"Risk Assessment: {data.get('risk_assessment', 'medium')}")
        print(f"Summary: {data.get('summary', 'No summary available')}")
    else:
        print("\n📊 No recent 4H analysis available")