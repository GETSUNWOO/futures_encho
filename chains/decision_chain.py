"""
의사결정 체인 - 최종 트레이딩 결정
- 모든 체인 결과 종합 분석
- 켈리 공식 기반 포지션 사이징
- 최종 매매 신호 생성
- 실시간 실행 (1분 주기)
"""
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from langchain.prompts import ChatPromptTemplate

from config import Config
from llm_factory import create_llm
from utils.db import get_chain_db, log_chain
from utils.kelly_utils import calculate_kelly_position
from chains.news_chain import get_latest_news_sentiment
from chains.market_chain_1h import get_1h_trend, get_1h_support_resistance
from chains.market_chain_4h import get_4h_trend, get_4h_key_levels, get_swing_opportunity
from chains.performance_chain import get_current_performance, get_best_direction, get_confidence_by_market_condition


class DecisionChain:
    """최종 트레이딩 의사결정 체인"""
    
    def __init__(self):
        """초기화"""
        self.db = get_chain_db()
        self.model_name = Config.get_chain_model("decision")
        self.settings = Config.get_chain_settings("decision")
        
        # LLM 생성
        try:
            self.llm = create_llm(self.model_name, **self.settings)
            log_chain("decision", "INFO", f"Initialized with model: {self.model_name}")
        except Exception as e:
            log_chain("decision", "ERROR", f"Failed to initialize LLM: {e}")
            raise
        
        # 의사결정 프롬프트
        self.decision_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an elite cryptocurrency trading decision maker with access to comprehensive market analysis.

Your role is to synthesize all available information and make a final trading decision for BTC/USDT futures.

You have access to:
1. Real-time price and market structure
2. News sentiment analysis
3. 1-hour technical analysis (short-term signals)
4. 4-hour structural analysis (medium-term context)
5. Historical performance patterns
6. Risk management parameters

Decision Framework:
- Only take trades when multiple timeframes align
- Consider news sentiment impact on direction
- Use performance patterns to adjust confidence
- Apply strict risk management
- Account for current market conditions

Risk Management Rules:
- Never exceed maximum position size limits
- Ensure risk-reward ratio > 1.5
- Consider market volatility in position sizing
- Respect stop-loss and take-profit levels
- Account for slippage and fees

Respond in JSON format:
{
  "direction": "LONG/SHORT/NO_POSITION",
  "conviction": 0.0-1.0,
  "reasoning": "detailed explanation of decision logic",
  "confidence_factors": {
    "technical_alignment": 0.0-1.0,
    "news_sentiment": 0.0-1.0,
    "market_structure": 0.0-1.0,
    "risk_reward": 0.0-1.0
  },
  "risk_parameters": {
    "stop_loss_percentage": 0.0-1.0,
    "take_profit_percentage": 0.0-1.0,
    "max_position_size": 0.0-1.0,
    "recommended_leverage": 1-20
  },
  "market_conditions": {
    "volatility_assessment": "low/medium/high",
    "trend_strength": 0.0-1.0,
    "timeframe_alignment": "aligned/conflicted/neutral"
  },
  "expected_outcome": {
    "probability_of_success": 0.0-1.0,
    "risk_reward_ratio": number,
    "expected_return": percentage
  }
}

Decision Criteria:
- NO_POSITION: conviction < 0.55, conflicted signals, high risk conditions
- LONG/SHORT: conviction ≥ 0.55, aligned timeframes, acceptable risk-reward
- High conviction (>0.75): strong alignment across all factors
- Medium conviction (0.55-0.75): partial alignment with risk management focus
- Consider historical performance patterns in similar conditions"""),
            ("human", """Make a trading decision based on this comprehensive analysis:

CURRENT MARKET STATUS:
Current BTC Price: ${current_price}
Time: {current_time}

NEWS ANALYSIS:
{news_summary}

1-HOUR TECHNICAL ANALYSIS:
{market_1h_summary}

4-HOUR STRUCTURAL ANALYSIS:
{market_4h_summary}

PERFORMANCE CONTEXT:
{performance_summary}

RISK MANAGEMENT:
Available Balance: ${available_balance}
Current Position: {current_position}
Daily P/L: ${daily_pnl}

Provide your final trading decision with detailed reasoning.""")
        ])
    
    def run(self, current_price: float, available_balance: float, 
            current_position: Optional[Dict[str, Any]] = None, 
            daily_pnl: float = 0.0) -> Dict[str, Any]:
        """
        최종 트레이딩 의사결정 실행
        
        Args:
            current_price: 현재 BTC 가격
            available_balance: 가용 잔액
            current_position: 현재 포지션 정보
            daily_pnl: 당일 손익
            
        Returns:
            트레이딩 의사결정 결과
        """
        start_time = time.time()
        
        try:
            # 이미 포지션이 있는 경우 NO_POSITION 반환
            if current_position and current_position.get('is_open', False):
                return self._no_position_result(
                    "Position already open",
                    {"has_position": True, "position_side": current_position.get('side')}
                )
            
            log_chain("decision", "INFO", f"Making trading decision at ${current_price:,.2f}")
            
            # 체인 결과 수집
            chain_results = self._collect_chain_results()
            
            # 시장 분석 데이터 준비
            market_analysis = self._prepare_market_analysis(
                current_price, available_balance, daily_pnl, chain_results
            )
            
            # AI 의사결정
            decision_result = self._make_decision(market_analysis)
            
            # 켈리 공식 적용 (포지션 진입 결정인 경우)
            if decision_result["direction"] != "NO_POSITION":
                kelly_result = self._apply_kelly_formula(
                    decision_result, available_balance, current_price, daily_pnl
                )
                decision_result.update(kelly_result)
            
            # 최종 검증
            final_decision = self._validate_final_decision(decision_result, market_analysis)
            
            processing_time = time.time() - start_time
            log_chain("decision", "INFO", 
                     f"Decision: {final_decision['direction']} "
                     f"(conviction: {final_decision.get('conviction', 0):.2f}) "
                     f"in {processing_time:.2f}s")
            
            return {
                "success": True,
                "timestamp": datetime.now().isoformat(),
                "decision": final_decision,
                "market_analysis": market_analysis,
                "processing_time": processing_time
            }
            
        except Exception as e:
            log_chain("decision", "ERROR", f"Decision making failed: {e}")
            return self._error_result(str(e))
    
    def _collect_chain_results(self) -> Dict[str, Any]:
        """모든 체인 결과 수집"""
        try:
            return {
                # 뉴스 체인
                "news_sentiment": get_latest_news_sentiment(),  # 0.0-1.0
                "news_summary": self.db.get_latest_news_summary(),
                
                # 1시간 차트 체인
                "trend_1h": get_1h_trend(),  # "bullish", "bearish", "sideways"
                "support_resistance_1h": get_1h_support_resistance(),
                "market_1h_summary": self.db.get_latest_trend_summary("1h"),
                
                # 4시간 차트 체인
                "trend_4h": get_4h_trend(),  # "strong_bullish", "bullish", etc.
                "key_levels_4h": get_4h_key_levels(),
                "swing_opportunity": get_swing_opportunity(),
                "market_4h_summary": self.db.get_latest_trend_summary("4h"),
                
                # 성과 체인
                "current_performance": get_current_performance(),
                "best_direction": get_best_direction(),  # "LONG", "SHORT", "BALANCED"
                "confidence_by_condition": get_confidence_by_market_condition(),
                "performance_summary": self.db.get_latest_performance_summary()
            }
        except Exception as e:
            log_chain("decision", "WARNING", f"Chain result collection partial failure: {e}")
            return {}
    
    def _prepare_market_analysis(self, current_price: float, available_balance: float, 
                                daily_pnl: float, chain_results: Dict[str, Any]) -> Dict[str, Any]:
        """시장 분석 데이터 준비"""
        # 뉴스 요약
        news_data = chain_results.get("news_summary")
        if news_data:
            news_summary = f"""
Sentiment: {news_data['summary'].get('sentiment', 'neutral')} (score: {news_data['sentiment_score']:.2f})
Articles: {news_data['articles_count']}
Summary: {news_data['summary'].get('summary', 'No summary')}
Trading Relevance: {news_data['summary'].get('trading_relevance', 0.5):.2f}
"""
        else:
            news_summary = "News sentiment: 0.50 (neutral) - No recent news analysis"
        
        # 1시간 기술 분석
        market_1h_data = chain_results.get("market_1h_summary")
        if market_1h_data:
            trend_data = market_1h_data['trend']
            support_resistance = chain_results.get("support_resistance_1h", {})
            market_1h_summary = f"""
Trend: {trend_data.get('trend_direction', 'sideways')} (strength: {trend_data.get('trend_strength', 0.5):.2f})
Momentum: {trend_data.get('momentum', 'neutral')}
Support Levels: {support_resistance.get('support', [])}
Resistance Levels: {support_resistance.get('resistance', [])}
Short-term Bias: {trend_data.get('short_term_bias', 'neutral')}
Confidence: {market_1h_data['confidence']:.2f}
"""
        else:
            market_1h_summary = "1H Analysis: sideways trend, neutral momentum"
        
        # 4시간 구조 분석
        market_4h_data = chain_results.get("market_4h_summary")
        if market_4h_data:
            trend_data = market_4h_data['trend']
            key_levels = chain_results.get("key_levels_4h", {})
            swing_opp = chain_results.get("swing_opportunity", {})
            market_4h_summary = f"""
Primary Trend: {trend_data.get('primary_trend', 'neutral')}
Market Structure: {trend_data.get('market_structure', 'consolidation')}
Weekly Bias: {trend_data.get('weekly_bias', 'neutral')}
Critical Support: {key_levels.get('critical_support', 0)}
Critical Resistance: {key_levels.get('critical_resistance', 0)}
Swing Opportunity: {swing_opp.get('direction', 'none')}
Risk Assessment: {trend_data.get('risk_assessment', 'medium')}
Confidence: {market_4h_data['confidence']:.2f}
"""
        else:
            market_4h_summary = "4H Analysis: neutral trend, consolidation structure"
        
        # 성과 컨텍스트
        perf_data = chain_results.get("current_performance", {})
        best_dir = chain_results.get("best_direction", "BALANCED")
        confidence_conditions = chain_results.get("confidence_by_condition", {})
        performance_summary = f"""
Historical Win Rate: {perf_data.get('win_rate', 0):.1%}
Average Return: {perf_data.get('avg_return', 0):.2f}%
Total Trades: {perf_data.get('total_trades', 0)}
Best Performing Direction: {best_dir}
Confidence in Trending Markets: {confidence_conditions.get('trending_markets', 0.5):.2f}
Confidence in Range-bound Markets: {confidence_conditions.get('range_bound_markets', 0.5):.2f}
High Volatility Performance: {confidence_conditions.get('high_volatility', 0.5):.2f}
"""
        
        return {
            "current_price": current_price,
            "available_balance": available_balance,
            "daily_pnl": daily_pnl,
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "news_summary": news_summary,
            "market_1h_summary": market_1h_summary,
            "market_4h_summary": market_4h_summary,
            "performance_summary": performance_summary,
            "chain_results": chain_results
        }
    
    def _make_decision(self, market_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """AI 의사결정 실행"""
        try:
            # 현재 포지션 상태
            current_position = "None"
            
            # AI 분석 요청
            messages = self.decision_prompt.format_messages(
                current_price=f"{market_analysis['current_price']:,.2f}",
                current_time=market_analysis['current_time'],
                news_summary=market_analysis['news_summary'],
                market_1h_summary=market_analysis['market_1h_summary'],
                market_4h_summary=market_analysis['market_4h_summary'],
                performance_summary=market_analysis['performance_summary'],
                available_balance=f"{market_analysis['available_balance']:,.2f}",
                current_position=current_position,
                daily_pnl=f"{market_analysis['daily_pnl']:,.2f}"
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
            
            decision_result = json.loads(response_text)
            
            # 결과 검증
            decision_result = self._validate_decision_result(decision_result)
            
            return decision_result
            
        except json.JSONDecodeError as e:
            log_chain("decision", "ERROR", f"Failed to parse AI decision: {e}")
            return self._fallback_decision(market_analysis)
        except Exception as e:
            log_chain("decision", "ERROR", f"AI decision failed: {e}")
            return self._fallback_decision(market_analysis)
    
    def _apply_kelly_formula(self, decision_result: Dict[str, Any], 
                           available_balance: float, current_price: float, 
                           daily_pnl: float) -> Dict[str, Any]:
        """켈리 공식 적용"""
        try:
            if not Config.USE_KELLY_CRITERION:
                # 켈리 공식 미사용시 고정값 사용
                return {
                    "position_sizing": {
                        "method": "fixed",
                        "position_fraction": 0.1,
                        "investment_amount": min(available_balance * 0.1, available_balance * 0.5),
                        "leverage": decision_result["risk_parameters"]["recommended_leverage"]
                    }
                }
            
            conviction = decision_result["conviction"]
            sl_pct = decision_result["risk_parameters"]["stop_loss_percentage"]
            tp_pct = decision_result["risk_parameters"]["take_profit_percentage"]
            max_leverage = decision_result["risk_parameters"]["recommended_leverage"]
            
            # 켈리 포지션 계산
            kelly_result = calculate_kelly_position(
                conviction=conviction,
                sl_percent=sl_pct,
                tp_percent=tp_pct,
                available_balance=available_balance,
                current_price=current_price,
                daily_pnl=daily_pnl,
                max_leverage=max_leverage
            )
            
            if kelly_result["success"]:
                return {
                    "position_sizing": {
                        "method": "kelly",
                        "position_fraction": kelly_result["position_fraction"],
                        "investment_amount": kelly_result["investment_amount"],
                        "btc_amount": kelly_result["btc_amount"],
                        "leverage": kelly_result["leverage"],
                        "kelly_details": kelly_result.get("kelly_details", {}),
                        "risk_metrics": kelly_result.get("risk_metrics", {})
                    }
                }
            else:
                # 켈리 계산 실패시 NO_POSITION으로 변경
                decision_result["direction"] = "NO_POSITION"
                decision_result["reasoning"] += f" Kelly calculation failed: {kelly_result.get('reason', 'unknown')}"
                return {"position_sizing": {"method": "none"}}
                
        except Exception as e:
            log_chain("decision", "ERROR", f"Kelly formula application failed: {e}")
            decision_result["direction"] = "NO_POSITION"
            decision_result["reasoning"] += f" Position sizing error: {str(e)}"
            return {"position_sizing": {"method": "error"}}
    
    def _validate_decision_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """의사결정 결과 검증"""
        # 기본값 설정
        defaults = {
            "direction": "NO_POSITION",
            "conviction": 0.5,
            "reasoning": "Default decision due to missing data",
            "confidence_factors": {
                "technical_alignment": 0.5,
                "news_sentiment": 0.5,
                "market_structure": 0.5,
                "risk_reward": 0.5
            },
            "risk_parameters": {
                "stop_loss_percentage": Config.RISK_SETTINGS["default_sl_percent"],
                "take_profit_percentage": Config.RISK_SETTINGS["default_tp_percent"],
                "max_position_size": Config.KELLY_SETTINGS["max_position_size"],
                "recommended_leverage": 3
            },
            "market_conditions": {
                "volatility_assessment": "medium",
                "trend_strength": 0.5,
                "timeframe_alignment": "neutral"
            },
            "expected_outcome": {
                "probability_of_success": 0.5,
                "risk_reward_ratio": 2.0,
                "expected_return": 3.0
            }
        }
        
        # 기본값으로 채우기
        for key, default_value in defaults.items():
            if key not in result:
                result[key] = default_value
            elif isinstance(default_value, dict):
                for sub_key, sub_default in default_value.items():
                    if sub_key not in result[key]:
                        result[key][sub_key] = sub_default
        
        # 값 범위 검증
        result["conviction"] = max(0.0, min(1.0, result["conviction"]))
        
        # 신뢰도 요소 검증
        for key in result["confidence_factors"]:
            result["confidence_factors"][key] = max(0.0, min(1.0, result["confidence_factors"][key]))
        
        # 리스크 파라미터 검증
        risk_params = result["risk_parameters"]
        risk_params["stop_loss_percentage"] = max(0.005, min(0.2, risk_params["stop_loss_percentage"]))
        risk_params["take_profit_percentage"] = max(0.01, min(0.5, risk_params["take_profit_percentage"]))
        risk_params["recommended_leverage"] = max(1, min(20, risk_params["recommended_leverage"]))
        
        # 방향 검증
        valid_directions = ["LONG", "SHORT", "NO_POSITION"]
        if result["direction"] not in valid_directions:
            result["direction"] = "NO_POSITION"
        
        # 확신도 기반 NO_POSITION 전환
        if result["conviction"] < Config.KELLY_SETTINGS["min_conviction"]:
            result["direction"] = "NO_POSITION"
            result["reasoning"] += f" Conviction {result['conviction']:.2f} below minimum {Config.KELLY_SETTINGS['min_conviction']:.2f}"
        
        return result
    
    def _validate_final_decision(self, decision: Dict[str, Any], market_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """최종 의사결정 검증"""
        # 추가 안전 검사
        chain_results = market_analysis.get("chain_results", {})
        
        # 1. 타임프레임 충돌 체크
        trend_1h = chain_results.get("trend_1h", "sideways")
        trend_4h = chain_results.get("trend_4h", "neutral")
        
        is_conflicted = (
            (trend_1h == "bullish" and trend_4h in ["bearish", "strong_bearish"]) or
            (trend_1h == "bearish" and trend_4h in ["bullish", "strong_bullish"])
        )
        
        if is_conflicted and decision["direction"] != "NO_POSITION":
            decision["direction"] = "NO_POSITION"
            decision["reasoning"] += " Timeframe conflict detected - 1H and 4H trends oppose"
        
        # 2. 뉴스 임팩트 체크
        news_sentiment = chain_results.get("news_sentiment", 0.5)
        if decision["direction"] == "LONG" and news_sentiment < 0.3:
            decision["conviction"] *= 0.8  # 확신도 하향 조정
            decision["reasoning"] += " Bearish news sentiment reduces conviction"
        elif decision["direction"] == "SHORT" and news_sentiment > 0.7:
            decision["conviction"] *= 0.8
            decision["reasoning"] += " Bullish news sentiment reduces conviction"
        
        # 3. 성과 패턴 반영
        best_direction = chain_results.get("best_direction", "BALANCED")
        if best_direction != "BALANCED" and decision["direction"] != "NO_POSITION":
            if decision["direction"] == best_direction:
                decision["conviction"] *= 1.1  # 확신도 상향 조정
                decision["reasoning"] += f" Historical best direction ({best_direction}) alignment"
            else:
                decision["conviction"] *= 0.9  # 확신도 하향 조정
                decision["reasoning"] += f" Against historical best direction ({best_direction})"
        
        # 4. 최종 확신도 재검증
        decision["conviction"] = max(0.0, min(1.0, decision["conviction"]))
        if decision["conviction"] < Config.KELLY_SETTINGS["min_conviction"]:
            decision["direction"] = "NO_POSITION"
            decision["reasoning"] += f" Final conviction check failed: {decision['conviction']:.2f}"
        
        return decision
    
    def _fallback_decision(self, market_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """AI 결정 실패시 폴백 결정"""
        chain_results = market_analysis.get("chain_results", {})
        
        # 간단한 규칙 기반 결정
        trend_1h = chain_results.get("trend_1h", "sideways")
        trend_4h = chain_results.get("trend_4h", "neutral")
        news_sentiment = chain_results.get("news_sentiment", 0.5)
        
        # 보수적 접근
        if trend_1h == "bullish" and trend_4h in ["bullish", "strong_bullish"] and news_sentiment > 0.6:
            direction = "LONG"
            conviction = 0.6
        elif trend_1h == "bearish" and trend_4h in ["bearish", "strong_bearish"] and news_sentiment < 0.4:
            direction = "SHORT"
            conviction = 0.6
        else:
            direction = "NO_POSITION"
            conviction = 0.3
        
        return {
            "direction": direction,
            "conviction": conviction,
            "reasoning": f"Fallback decision: {trend_1h} 1H, {trend_4h} 4H, news {news_sentiment:.2f}",
            "confidence_factors": {
                "technical_alignment": 0.5,
                "news_sentiment": news_sentiment,
                "market_structure": 0.5,
                "risk_reward": 0.5
            },
            "risk_parameters": {
                "stop_loss_percentage": 0.03,
                "take_profit_percentage": 0.06,
                "max_position_size": 0.2,
                "recommended_leverage": 3
            },
            "market_conditions": {
                "volatility_assessment": "medium",
                "trend_strength": 0.5,
                "timeframe_alignment": "neutral"
            },
            "expected_outcome": {
                "probability_of_success": conviction,
                "risk_reward_ratio": 2.0,
                "expected_return": 3.0
            }
        }
    
    def _no_position_result(self, reason: str, additional_info: Dict[str, Any] = None) -> Dict[str, Any]:
        """포지션 없음 결과 반환"""
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "decision": {
                "direction": "NO_POSITION",
                "conviction": 0.0,
                "reasoning": reason,
                "additional_info": additional_info or {}
            }
        }
    
    def _error_result(self, error_msg: str) -> Dict[str, Any]:
        """에러 결과 반환"""
        return {
            "success": False,
            "timestamp": datetime.now().isoformat(),
            "error": error_msg,
            "decision": {
                "direction": "NO_POSITION",
                "conviction": 0.0,
                "reasoning": f"Error occurred: {error_msg}"
            }
        }


# 편의 함수들
def make_trading_decision(current_price: float, available_balance: float,
                         current_position: Optional[Dict[str, Any]] = None,
                         daily_pnl: float = 0.0) -> Dict[str, Any]:
    """트레이딩 의사결정 편의 함수"""
    chain = DecisionChain()
    return chain.run(current_price, available_balance, current_position, daily_pnl)


def get_quick_decision_summary(current_price: float, available_balance: float) -> str:
    """빠른 의사결정 요약"""
    result = make_trading_decision(current_price, available_balance)
    
    if result["success"]:
        decision = result["decision"]
        direction = decision["direction"]
        conviction = decision.get("conviction", 0)
        
        if direction == "NO_POSITION":
            return f"NO_POSITION - {decision['reasoning'][:100]}..."
        else:
            sizing = decision.get("position_sizing", {})
            amount = sizing.get("investment_amount", 0)
            leverage = sizing.get("leverage", 1)
            return f"{direction} - Conviction: {conviction:.2f}, Amount: ${amount:,.0f}, Leverage: {leverage}x"
    else:
        return f"ERROR - {result.get('error', 'Unknown error')}"


def print_decision_summary(current_price: float, available_balance: float) -> None:
    """의사결정 요약 출력"""
    result = make_trading_decision(current_price, available_balance)
    
    if result["success"]:
        decision = result["decision"]
        print(f"\n🧠 Trading Decision Summary")
        print(f"Direction: {decision['direction']}")
        print(f"Conviction: {decision.get('conviction', 0):.2f}")
        print(f"Reasoning: {decision['reasoning'][:200]}...")
        
        if decision["direction"] != "NO_POSITION":
            sizing = decision.get("position_sizing", {})
            if sizing.get("method") != "none":
                print(f"\n💰 Position Sizing:")
                print(f"Investment: ${sizing.get('investment_amount', 0):,.2f}")
                print(f"Leverage: {sizing.get('leverage', 1)}x")
                print(f"Method: {sizing.get('method', 'unknown')}")
        
        risk_params = decision.get("risk_parameters", {})
        print(f"\n🛡️ Risk Parameters:")
        print(f"Stop Loss: {risk_params.get('stop_loss_percentage', 0)*100:.1f}%")
        print(f"Take Profit: {risk_params.get('take_profit_percentage', 0)*100:.1f}%")
        
    else:
        print(f"\n🧠 Decision Error: {result.get('error', 'Unknown error')}")