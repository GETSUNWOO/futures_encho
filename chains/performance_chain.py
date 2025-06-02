"""
성과 분석 체인
- 과거 트레이딩 성과 분석
- 패턴 학습 및 개선점 도출
- AI 의사결정 피드백 루프
- 결과 캐싱 (2시간 주기 또는 트레이드 종료시)
"""
import json
import time
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from langchain.prompts import ChatPromptTemplate

from config import Config
from llm_factory import create_llm
from utils.db import get_chain_db, log_chain


class PerformanceChain:
    """성과 분석 체인"""
    
    def __init__(self):
        """초기화"""
        self.db = get_chain_db()
        self.model_name = Config.get_chain_model("performance")
        self.settings = Config.get_chain_settings("performance")
        
        # LLM 생성
        try:
            self.llm = create_llm(self.model_name, **self.settings)
            log_chain("performance", "INFO", f"Initialized with model: {self.model_name}")
        except Exception as e:
            log_chain("performance", "ERROR", f"Failed to initialize LLM: {e}")
            raise
        
        # 분석 프롬프트
        self.analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert trading performance analyst specializing in cryptocurrency trading systems.

Analyze the provided trading performance data to identify patterns, strengths, weaknesses, and actionable insights for improving future trading decisions.

Focus on:
1. Overall performance metrics and trends
2. Winning vs losing trade patterns
3. Direction bias effectiveness (LONG vs SHORT)
4. Risk management effectiveness
5. Market condition adaptability
6. AI decision accuracy patterns
7. Areas for improvement

Your analysis should provide:
- Performance summary with key metrics
- Pattern identification in successful/failed trades
- Risk management assessment
- Recommendations for strategy improvements
- Confidence levels for different market conditions

Respond in JSON format:
{
  "performance_summary": {
    "total_trades": number,
    "win_rate": 0.0-1.0,
    "avg_return_per_trade": percentage,
    "total_return": percentage,
    "max_drawdown": percentage,
    "sharpe_ratio": number,
    "profit_factor": number
  },
  "pattern_analysis": {
    "best_performing_direction": "LONG/SHORT/BALANCED",
    "optimal_market_conditions": ["condition1", "condition2"],
    "common_winning_patterns": ["pattern1", "pattern2"],
    "common_losing_patterns": ["pattern1", "pattern2"]
  },
  "risk_management": {
    "sl_effectiveness": 0.0-1.0,
    "tp_effectiveness": 0.0-1.0,
    "position_sizing_accuracy": 0.0-1.0,
    "avg_risk_reward_ratio": number
  },
  "ai_decision_quality": {
    "conviction_accuracy": 0.0-1.0,
    "market_timing": 0.0-1.0,
    "direction_accuracy": 0.0-1.0,
    "confidence_calibration": 0.0-1.0
  },
  "market_adaptation": {
    "bull_market_performance": 0.0-1.0,
    "bear_market_performance": 0.0-1.0,
    "sideways_market_performance": 0.0-1.0,
    "volatility_adaptation": 0.0-1.0
  },
  "improvement_recommendations": [
    "recommendation1",
    "recommendation2",
    "recommendation3"
  ],
  "confidence_by_condition": {
    "trending_markets": 0.0-1.0,
    "range_bound_markets": 0.0-1.0,
    "high_volatility": 0.0-1.0,
    "low_volatility": 0.0-1.0
  },
  "key_insights": [
    "insight1",
    "insight2",
    "insight3"
  ],
  "overall_assessment": "excellent/good/average/poor",
  "confidence": 0.0-1.0,
  "summary": "3-4 sentence summary of performance analysis and main recommendations"
}

Base your analysis on actual performance data patterns, not generic advice."""),
            ("human", "Analyze this trading performance data:\n\nOverall Metrics:\n{overall_metrics}\n\nTrade Details:\n{trade_details}\n\nAI Decision History:\n{ai_decisions}\n\nMarket Context:\n{market_context}")
        ])
    
    def run(self, force_refresh: bool = False, trade_completed: bool = False) -> Dict[str, Any]:
        """
        성과 분석 실행
        
        Args:
            force_refresh: 캐시 무시하고 강제 갱신
            trade_completed: 트레이드 완료로 인한 갱신
            
        Returns:
            성과 분석 결과
        """
        start_time = time.time()
        
        try:
            # 캐시된 결과 확인 (트레이드 완료가 아닌 경우)
            if not force_refresh and not trade_completed:
                cached_result = self.db.get_latest_performance_summary()
                if cached_result:
                    log_chain("performance", "INFO", "Using cached performance analysis")
                    return {
                        "success": True,
                        "source": "cache",
                        "timestamp": cached_result["timestamp"],
                        "data": cached_result["summary"],
                        "total_trades": cached_result["total_trades"],
                        "win_rate": cached_result["win_rate"],
                        "avg_return": cached_result["avg_return"]
                    }
            
            # 성과 데이터 수집
            log_chain("performance", "INFO", "Collecting trading performance data")
            performance_data = self._collect_performance_data()
            
            if not performance_data["has_trades"]:
                log_chain("performance", "INFO", "No trades available for analysis")
                return self._empty_result("No trading history available")
            
            # AI 분석
            log_chain("performance", "INFO", f"Analyzing {performance_data['total_trades']} trades")
            analysis_result = self._analyze_performance(performance_data)
            
            # 결과 저장
            summary_data = {
                "total_trades": performance_data["total_trades"],
                "win_rate": performance_data["overall_metrics"]["win_rate"],
                "avg_return": performance_data["overall_metrics"]["avg_return_per_trade"],
                "analysis": analysis_result
            }
            
            self.db.save_performance_summary(summary_data)
            
            processing_time = time.time() - start_time
            log_chain("performance", "INFO", f"Performance analysis completed in {processing_time:.2f}s")
            
            return {
                "success": True,
                "source": "fresh",
                "timestamp": datetime.now().isoformat(),
                "data": analysis_result,
                "total_trades": performance_data["total_trades"],
                "win_rate": performance_data["overall_metrics"]["win_rate"],
                "avg_return": performance_data["overall_metrics"]["avg_return_per_trade"],
                "processing_time": processing_time
            }
            
        except Exception as e:
            log_chain("performance", "ERROR", f"Performance analysis failed: {e}")
            return self._error_result(str(e))
    
    def _collect_performance_data(self) -> Dict[str, Any]:
        """성과 데이터 수집"""
        try:
            # 기존 database/recorder.py 활용
            from database.recorder import DatabaseRecorder
            recorder = DatabaseRecorder(Config.get_db_file())
            
            # 최근 30일간의 트레이드 데이터
            historical_data = recorder.get_historical_trading_data(limit=50)
            performance_metrics = recorder.get_performance_metrics()
            
            if not historical_data:
                return {"has_trades": False, "total_trades": 0}
            
            # 트레이드 세부 정보 분석
            trade_analysis = self._analyze_trade_details(historical_data)
            
            # AI 결정 히스토리 분석
            ai_decisions = self._analyze_ai_decisions(historical_data)
            
            # 시장 컨텍스트 분석
            market_context = self._analyze_market_context(historical_data)
            
            # 전체 메트릭스 계산
            overall_metrics = self._calculate_overall_metrics(historical_data, performance_metrics)
            
            return {
                "has_trades": True,
                "total_trades": len(historical_data),
                "overall_metrics": overall_metrics,
                "trade_details": trade_analysis,
                "ai_decisions": ai_decisions,
                "market_context": market_context,
                "raw_trades": historical_data
            }
            
        except Exception as e:
            log_chain("performance", "ERROR", f"Performance data collection failed: {e}")
            return {"has_trades": False, "total_trades": 0, "error": str(e)}
    
    def _analyze_trade_details(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """트레이드 세부 분석"""
        if not trades:
            return {}
        
        winning_trades = [t for t in trades if t.get('profit_loss', 0) > 0]
        losing_trades = [t for t in trades if t.get('profit_loss', 0) < 0]
        
        long_trades = [t for t in trades if t.get('action') == 'long']
        short_trades = [t for t in trades if t.get('action') == 'short']
        
        long_wins = [t for t in long_trades if t.get('profit_loss', 0) > 0]
        short_wins = [t for t in short_trades if t.get('profit_loss', 0) > 0]
        
        return {
            "total_trades": len(trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "long_trades": len(long_trades),
            "short_trades": len(short_trades),
            "long_win_rate": len(long_wins) / len(long_trades) if long_trades else 0,
            "short_win_rate": len(short_wins) / len(short_trades) if short_trades else 0,
            "avg_winning_trade": sum(t.get('profit_loss', 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0,
            "avg_losing_trade": sum(t.get('profit_loss', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0,
            "largest_win": max(t.get('profit_loss', 0) for t in trades) if trades else 0,
            "largest_loss": min(t.get('profit_loss', 0) for t in trades) if trades else 0,
            "avg_leverage": sum(t.get('leverage', 1) for t in trades) / len(trades) if trades else 1
        }
    
    def _analyze_ai_decisions(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """AI 결정 분석"""
        if not trades:
            return {}
        
        # AI 분석 결과가 있는 트레이드들
        trades_with_ai = [t for t in trades if t.get('reasoning')]
        
        if not trades_with_ai:
            return {"has_ai_data": False}
        
        # 확신도별 성과 (reasoning에서 패턴 추출 - 간단한 방법)
        high_conviction_trades = []
        medium_conviction_trades = []
        low_conviction_trades = []
        
        for trade in trades_with_ai:
            reasoning = trade.get('reasoning', '').lower()
            if any(word in reasoning for word in ['strong', 'confident', 'clear']):
                high_conviction_trades.append(trade)
            elif any(word in reasoning for word in ['weak', 'uncertain', 'mixed']):
                low_conviction_trades.append(trade)
            else:
                medium_conviction_trades.append(trade)
        
        def calc_win_rate(trade_list):
            if not trade_list:
                return 0
            wins = sum(1 for t in trade_list if t.get('profit_loss', 0) > 0)
            return wins / len(trade_list)
        
        return {
            "has_ai_data": True,
            "total_ai_trades": len(trades_with_ai),
            "high_conviction_count": len(high_conviction_trades),
            "medium_conviction_count": len(medium_conviction_trades),
            "low_conviction_count": len(low_conviction_trades),
            "high_conviction_win_rate": calc_win_rate(high_conviction_trades),
            "medium_conviction_win_rate": calc_win_rate(medium_conviction_trades),
            "low_conviction_win_rate": calc_win_rate(low_conviction_trades),
            "ai_direction_accuracy": calc_win_rate(trades_with_ai)
        }
    
    def _analyze_market_context(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """시장 컨텍스트 분석"""
        if not trades:
            return {}
        
        # 시간대별 성과 (간단한 분류)
        recent_trades = []
        older_trades = []
        cutoff_date = datetime.now() - timedelta(days=7)
        
        for trade in trades:
            try:
                trade_date = datetime.fromisoformat(trade.get('trade_timestamp', ''))
                if trade_date > cutoff_date:
                    recent_trades.append(trade)
                else:
                    older_trades.append(trade)
            except:
                older_trades.append(trade)  # 파싱 실패시 오래된 것으로 분류
        
        def calc_performance(trade_list):
            if not trade_list:
                return {"win_rate": 0, "avg_return": 0}
            wins = sum(1 for t in trade_list if t.get('profit_loss', 0) > 0)
            avg_return = sum(t.get('profit_loss_percentage', 0) for t in trade_list) / len(trade_list)
            return {"win_rate": wins / len(trade_list), "avg_return": avg_return}
        
        return {
            "recent_trades_count": len(recent_trades),
            "older_trades_count": len(older_trades),
            "recent_performance": calc_performance(recent_trades),
            "older_performance": calc_performance(older_trades),
            "performance_trend": "improving" if calc_performance(recent_trades)["win_rate"] > calc_performance(older_trades)["win_rate"] else "declining"
        }
    
    def _calculate_overall_metrics(self, trades: List[Dict[str, Any]], performance_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """전체 메트릭스 계산"""
        if not trades:
            return {}
        
        closed_trades = [t for t in trades if t.get('profit_loss') is not None]
        
        if not closed_trades:
            return {}
        
        total_return = sum(t.get('profit_loss', 0) for t in closed_trades)
        total_return_pct = sum(t.get('profit_loss_percentage', 0) for t in closed_trades)
        wins = sum(1 for t in closed_trades if t.get('profit_loss', 0) > 0)
        win_rate = wins / len(closed_trades)
        
        # 샤프 비율 (간단한 계산)
        returns = [t.get('profit_loss_percentage', 0) for t in closed_trades]
        avg_return = sum(returns) / len(returns) if returns else 0
        return_std = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if len(returns) > 1 else 0
        sharpe_ratio = avg_return / return_std if return_std > 0 else 0
        
        # 프로핏 팩터
        total_wins = sum(t.get('profit_loss', 0) for t in closed_trades if t.get('profit_loss', 0) > 0)
        total_losses = abs(sum(t.get('profit_loss', 0) for t in closed_trades if t.get('profit_loss', 0) < 0))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # 최대 드로다운 (간단한 계산)
        cumulative_returns = []
        cumulative = 0
        for trade in closed_trades:
            cumulative += trade.get('profit_loss_percentage', 0)
            cumulative_returns.append(cumulative)
        
        max_drawdown = 0
        peak = cumulative_returns[0] if cumulative_returns else 0
        for return_val in cumulative_returns:
            if return_val > peak:
                peak = return_val
            drawdown = (peak - return_val) / 100  # 백분율로 변환
            max_drawdown = max(max_drawdown, drawdown)
        
        return {
            "total_trades": len(closed_trades),
            "win_rate": win_rate,
            "avg_return_per_trade": avg_return,
            "total_return": total_return_pct,
            "max_drawdown": max_drawdown * 100,  # 백분율로 표시
            "sharpe_ratio": sharpe_ratio,
            "profit_factor": profit_factor,
            "total_profit_usd": total_return
        }
    
    def _analyze_performance(self, performance_data: Dict[str, Any]) -> Dict[str, Any]:
        """AI를 통한 성과 분석"""
        try:
            # 데이터를 텍스트로 변환
            overall_text = f"""
Total Trades: {performance_data['overall_metrics']['total_trades']}
Win Rate: {performance_data['overall_metrics']['win_rate']:.2%}
Average Return per Trade: {performance_data['overall_metrics']['avg_return_per_trade']:.2f}%
Total Return: {performance_data['overall_metrics']['total_return']:.2f}%
Max Drawdown: {performance_data['overall_metrics']['max_drawdown']:.2f}%
Sharpe Ratio: {performance_data['overall_metrics']['sharpe_ratio']:.2f}
Profit Factor: {performance_data['overall_metrics']['profit_factor']:.2f}
Total Profit: ${performance_data['overall_metrics']['total_profit_usd']:.2f}
"""
            
            trade_details_text = f"""
Long Trades: {performance_data['trade_details']['long_trades']} (Win Rate: {performance_data['trade_details']['long_win_rate']:.2%})
Short Trades: {performance_data['trade_details']['short_trades']} (Win Rate: {performance_data['trade_details']['short_win_rate']:.2%})
Average Winning Trade: ${performance_data['trade_details']['avg_winning_trade']:.2f}
Average Losing Trade: ${performance_data['trade_details']['avg_losing_trade']:.2f}
Largest Win: ${performance_data['trade_details']['largest_win']:.2f}
Largest Loss: ${performance_data['trade_details']['largest_loss']:.2f}
Average Leverage: {performance_data['trade_details']['avg_leverage']:.1f}x
"""
            
            ai_decisions_text = ""
            if performance_data['ai_decisions'].get('has_ai_data'):
                ai_decisions_text = f"""
High Conviction Trades: {performance_data['ai_decisions']['high_conviction_count']} (Win Rate: {performance_data['ai_decisions']['high_conviction_win_rate']:.2%})
Medium Conviction Trades: {performance_data['ai_decisions']['medium_conviction_count']} (Win Rate: {performance_data['ai_decisions']['medium_conviction_win_rate']:.2%})
Low Conviction Trades: {performance_data['ai_decisions']['low_conviction_count']} (Win Rate: {performance_data['ai_decisions']['low_conviction_win_rate']:.2%})
Overall AI Direction Accuracy: {performance_data['ai_decisions']['ai_direction_accuracy']:.2%}
"""
            else:
                ai_decisions_text = "No AI decision data available for analysis."
            
            market_context_text = f"""
Recent Trades (7 days): {performance_data['market_context']['recent_trades_count']} (Win Rate: {performance_data['market_context']['recent_performance']['win_rate']:.2%})
Older Trades: {performance_data['market_context']['older_trades_count']} (Win Rate: {performance_data['market_context']['older_performance']['win_rate']:.2%})
Performance Trend: {performance_data['market_context']['performance_trend']}
Recent Average Return: {performance_data['market_context']['recent_performance']['avg_return']:.2f}%
Historical Average Return: {performance_data['market_context']['older_performance']['avg_return']:.2f}%
"""
            
            # AI 분석 요청
            messages = self.analysis_prompt.format_messages(
                overall_metrics=overall_text,
                trade_details=trade_details_text,
                ai_decisions=ai_decisions_text,
                market_context=market_context_text
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
            analysis_result = self._validate_analysis_result(analysis_result, performance_data)
            
            log_chain("performance", "INFO", f"Performance analysis: {analysis_result['overall_assessment']} ({analysis_result['confidence']:.2f})")
            return analysis_result
            
        except json.JSONDecodeError as e:
            log_chain("performance", "ERROR", f"Failed to parse AI response: {e}")
            return self._fallback_analysis(performance_data)
        except Exception as e:
            log_chain("performance", "ERROR", f"Performance analysis failed: {e}")
            return self._fallback_analysis(performance_data)
    
    def _validate_analysis_result(self, result: Dict[str, Any], performance_data: Dict[str, Any]) -> Dict[str, Any]:
        """분석 결과 검증 및 기본값 설정"""
        # 기본값 설정
        defaults = {
            "performance_summary": performance_data.get('overall_metrics', {}),
            "pattern_analysis": {
                "best_performing_direction": "BALANCED",
                "optimal_market_conditions": ["trending"],
                "common_winning_patterns": ["trend_following"],
                "common_losing_patterns": ["counter_trend"]
            },
            "risk_management": {
                "sl_effectiveness": 0.5,
                "tp_effectiveness": 0.5,
                "position_sizing_accuracy": 0.5,
                "avg_risk_reward_ratio": 1.0
            },
            "ai_decision_quality": {
                "conviction_accuracy": 0.5,
                "market_timing": 0.5,
                "direction_accuracy": 0.5,
                "confidence_calibration": 0.5
            },
            "market_adaptation": {
                "bull_market_performance": 0.5,
                "bear_market_performance": 0.5,
                "sideways_market_performance": 0.5,
                "volatility_adaptation": 0.5
            },
            "improvement_recommendations": ["Insufficient data for specific recommendations"],
            "confidence_by_condition": {
                "trending_markets": 0.5,
                "range_bound_markets": 0.5,
                "high_volatility": 0.5,
                "low_volatility": 0.5
            },
            "key_insights": ["More trading data needed for detailed analysis"],
            "overall_assessment": "average",
            "confidence": 0.5,
            "summary": "Performance analysis completed with limited historical data"
        }
        
        # 기본값으로 채우기
        for key, default_value in defaults.items():
            if key not in result:
                result[key] = default_value
        
        # 값 범위 검증 (0.0-1.0 범위)
        for section in ["risk_management", "ai_decision_quality", "market_adaptation", "confidence_by_condition"]:
            if section in result and isinstance(result[section], dict):
                for key, value in result[section].items():
                    if isinstance(value, (int, float)):
                        result[section][key] = max(0.0, min(1.0, value))
        
        result["confidence"] = max(0.0, min(1.0, result.get("confidence", 0.5)))
        
        # 유효한 enum 값 검증
        valid_assessments = ["excellent", "good", "average", "poor"]
        if result.get("overall_assessment") not in valid_assessments:
            result["overall_assessment"] = "average"
        
        return result
    
    def _fallback_analysis(self, performance_data: Dict[str, Any]) -> Dict[str, Any]:
        """AI 분석 실패시 폴백 분석"""
        metrics = performance_data.get('overall_metrics', {})
        trade_details = performance_data.get('trade_details', {})
        
        win_rate = metrics.get('win_rate', 0)
        profit_factor = metrics.get('profit_factor', 1)
        total_return = metrics.get('total_return', 0)
        
        # 간단한 성과 평가
        if win_rate > 0.6 and profit_factor > 1.5 and total_return > 10:
            assessment = "good"
            confidence = 0.7
        elif win_rate > 0.5 and profit_factor > 1.2:
            assessment = "average"
            confidence = 0.5
        else:
            assessment = "poor"
            confidence = 0.4
        
        # 방향 편향 분석
        long_trades = trade_details.get('long_trades', 0)
        short_trades = trade_details.get('short_trades', 0)
        long_win_rate = trade_details.get('long_win_rate', 0)
        short_win_rate = trade_details.get('short_win_rate', 0)
        
        if long_win_rate > short_win_rate + 0.1:
            best_direction = "LONG"
        elif short_win_rate > long_win_rate + 0.1:
            best_direction = "SHORT"
        else:
            best_direction = "BALANCED"
        
        return {
            "performance_summary": metrics,
            "pattern_analysis": {
                "best_performing_direction": best_direction,
                "optimal_market_conditions": ["trending_markets"],
                "common_winning_patterns": ["trend_following"],
                "common_losing_patterns": ["poor_timing"]
            },
            "risk_management": {
                "sl_effectiveness": 0.5,
                "tp_effectiveness": 0.5,
                "position_sizing_accuracy": 0.5,
                "avg_risk_reward_ratio": profit_factor
            },
            "ai_decision_quality": {
                "conviction_accuracy": win_rate,
                "market_timing": 0.5,
                "direction_accuracy": win_rate,
                "confidence_calibration": 0.5
            },
            "market_adaptation": {
                "bull_market_performance": 0.5,
                "bear_market_performance": 0.5,
                "sideways_market_performance": 0.5,
                "volatility_adaptation": 0.5
            },
            "improvement_recommendations": [
                f"Focus on {best_direction} trades if directional bias exists",
                "Improve risk management if profit factor < 1.5",
                "Increase sample size for better analysis"
            ],
            "confidence_by_condition": {
                "trending_markets": win_rate,
                "range_bound_markets": 0.4,
                "high_volatility": 0.4,
                "low_volatility": 0.5
            },
            "key_insights": [
                f"Win rate: {win_rate:.1%}",
                f"Profit factor: {profit_factor:.2f}",
                f"Best direction: {best_direction}"
            ],
            "overall_assessment": assessment,
            "confidence": confidence,
            "summary": f"Fallback analysis shows {assessment} performance with {win_rate:.1%} win rate and {profit_factor:.2f} profit factor"
        }
    
    def _empty_result(self, reason: str) -> Dict[str, Any]:
        """빈 결과 반환"""
        return {
            "success": False,
            "source": "empty",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "overall_assessment": "insufficient_data",
                "summary": "No trading history available for analysis"
            },
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0
        }
    
    def _error_result(self, error_msg: str) -> Dict[str, Any]:
        """에러 결과 반환"""
        return {
            "success": False,
            "source": "error",
            "error": error_msg,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "overall_assessment": "error",
                "summary": "Error occurred during performance analysis"
            },
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0
        }


# 편의 함수들
def run_performance_analysis(force_refresh: bool = False, trade_completed: bool = False) -> Dict[str, Any]:
    """성과 분석 실행 편의 함수"""
    chain = PerformanceChain()
    return chain.run(force_refresh, trade_completed)


def get_current_performance() -> Dict[str, float]:
    """현재 성과 요약 반환"""
    db = get_chain_db()
    perf_summary = db.get_latest_performance_summary()
    
    if perf_summary:
        return {
            "win_rate": perf_summary["win_rate"],
            "avg_return": perf_summary["avg_return"],
            "total_trades": perf_summary["total_trades"]
        }
    return {"win_rate": 0.0, "avg_return": 0.0, "total_trades": 0}


def get_best_direction() -> str:
    """최적 방향 편향 반환"""
    db = get_chain_db()
    perf_summary = db.get_latest_performance_summary()
    
    if perf_summary:
        analysis = perf_summary["summary"].get("analysis", {})
        pattern_analysis = analysis.get("pattern_analysis", {})
        return pattern_analysis.get("best_performing_direction", "BALANCED")
    return "BALANCED"


def get_improvement_recommendations() -> List[str]:
    """개선 권장사항 반환"""
    db = get_chain_db()
    perf_summary = db.get_latest_performance_summary()
    
    if perf_summary:
        analysis = perf_summary["summary"].get("analysis", {})
        return analysis.get("improvement_recommendations", [])
    return ["No recommendations available - insufficient data"]


def get_confidence_by_market_condition() -> Dict[str, float]:
    """시장 상황별 신뢰도 반환"""
    db = get_chain_db()
    perf_summary = db.get_latest_performance_summary()
    
    if perf_summary:
        analysis = perf_summary["summary"].get("analysis", {})
        return analysis.get("confidence_by_condition", {})
    return {
        "trending_markets": 0.5,
        "range_bound_markets": 0.5,
        "high_volatility": 0.5,
        "low_volatility": 0.5
    }


def print_performance_summary() -> None:
    """성과 분석 요약 출력"""
    db = get_chain_db()
    perf_summary = db.get_latest_performance_summary()
    
    if perf_summary:
        summary = perf_summary["summary"]
        analysis = summary.get("analysis", {})
        
        print(f"\n📊 Performance Analysis Summary")
        print(f"Total Trades: {perf_summary['total_trades']}")
        print(f"Win Rate: {perf_summary['win_rate']:.1%}")
        print(f"Avg Return: {perf_summary['avg_return']:.2f}%")
        print(f"Overall Assessment: {analysis.get('overall_assessment', 'unknown')}")
        print(f"Best Direction: {analysis.get('pattern_analysis', {}).get('best_performing_direction', 'unknown')}")
        
        # 개선 권장사항
        recommendations = analysis.get('improvement_recommendations', [])
        if recommendations:
            print(f"\n🎯 Key Recommendations:")
            for i, rec in enumerate(recommendations[:3], 1):
                print(f"  {i}. {rec}")
        
        # 핵심 인사이트
        insights = analysis.get('key_insights', [])
        if insights:
            print(f"\n💡 Key Insights:")
            for insight in insights[:3]:
                print(f"  • {insight}")
                
        print(f"\nSummary: {analysis.get('summary', 'No summary available')}")
    else:
        print("\n📊 No recent performance analysis available")


def trigger_performance_update_on_trade_completion():
    """트레이드 완료시 성과 분석 갱신 트리거"""
    try:
        result = run_performance_analysis(trade_completed=True)
        if result["success"]:
            log_chain("performance", "INFO", "Performance analysis updated after trade completion")
            return True
        else:
            log_chain("performance", "WARNING", f"Performance update failed: {result.get('reason', 'unknown')}")
            return False
    except Exception as e:
        log_chain("performance", "ERROR", f"Performance update trigger failed: {e}")
        return False