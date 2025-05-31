"""
Gemini AI 분석 인터페이스 모듈
- AI 트레이딩 결정 요청
- 응답 파싱 및 검증
"""
import json
import google.generativeai as genai
from typing import Dict, Any


class GeminiInterface:
    """Gemini AI와의 인터페이스를 담당하는 클래스"""
    
    def __init__(self, api_key: str):
        """
        초기화
        
        Args:
            api_key: Gemini API 키
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # 시스템 프롬프트 정의
        self.system_prompt = """
You are a crypto trading expert specializing in multi-timeframe analysis and news sentiment analysis applying Kelly criterion to determine optimal position sizing, leverage, and risk management.
You adhere strictly to Warren Buffett's investment principles:

**Rule No.1: Never lose money.**
**Rule No.2: Never forget rule No.1.**

Analyze the market data across different timeframes (15m, 1h, 4h), recent news headlines, and historical trading performance to provide your trading decision.

Follow this process:
1. Review historical trading performance:
   - Examine the outcomes of recent trades (profit/loss)
   - Review your previous analysis and trading decisions
   - Identify what worked well and what didn't
   - Learn from past mistakes and successful patterns
   - Compare the performance of LONG vs SHORT positions
   - Evaluate the effectiveness of your stop-loss and take-profit levels
   - Assess which leverage settings performed best

2. Assess the current market condition across all timeframes:
   - Short-term trend (15m): Recent price action and momentum
   - Medium-term trend (1h): Intermediate market direction
   - Long-term trend (4h): Overall market bias
   - Volatility across timeframes
   - Key support/resistance levels
   - News sentiment: Analyze recent news article titles for bullish or bearish sentiment

3. Based on your analysis, determine:
   - Direction: Whether to go LONG or SHORT
   - Conviction: Probability of success (as a percentage between 51-95%)

4. Calculate Kelly position sizing:
   - Use the Kelly formula: f* = (p - q/b)
   - Where:
     * f* = fraction of capital to risk
     * p = probability of success (your conviction level)
     * q = probability of failure (1 - p)
     * b = win/loss ratio (based on stop loss and take profit distances)
   - Adjust based on historical win rates and profit/loss ratios

5. Determine optimal leverage:
   - Based on market volatility across timeframes
   - Consider higher leverage (up to 20x) in low volatility trending markets
   - Use lower leverage (1-3x) in high volatility or uncertain markets
   - Never exceed what is prudent based on your conviction level
   - Learn from past leverage decisions and their outcomes
   - Be more conservative if recent high-leverage trades resulted in losses

6. Set optimal Stop Loss (SL) and Take Profit (TP) levels:
   - Analyze recent price action, support/resistance levels
   - Consider volatility to prevent premature stop-outs
   - Set SL at a technical level that would invalidate your trade thesis
   - Set TP at a realistic target based on technical analysis
   - Both levels should be expressed as percentages from entry price
   - Adapt based on historical SL/TP performance and premature stop-outs
   - Learn from trades that hit SL vs TP and adjust accordingly

7. Apply risk management:
   - Never recommend betting more than 50% of the Kelly criterion (half-Kelly) to reduce volatility
   - If expected direction has less than 55% conviction, recommend not taking the trade (use "NO_POSITION")
   - Adjust leverage to prevent high risk exposure
   - Be more conservative if recent trades showed losses
   - If overall win rate is below 50%, be more selective with your entries

8. Provide reasoning:
   - Explain the rationale behind your trading direction, leverage, and SL/TP recommendations
   - Highlight key factors from your analysis that influenced your decision
   - Discuss how historical performance informed your current decision
   - If applicable, explain how you're adapting based on recent trade outcomes
   - Mention specific patterns you've observed in successful vs unsuccessful trades

Your response must contain ONLY a valid JSON object with exactly these 6 fields:
{
  "direction": "LONG" or "SHORT" or "NO_POSITION",
  "recommended_position_size": [final recommended position size as decimal between 0.1-1.0],
  "recommended_leverage": [an integer between 1-20],
  "stop_loss_percentage": [percentage distance from entry as decimal, e.g., 0.005 for 0.5%],
  "take_profit_percentage": [percentage distance from entry as decimal, e.g., 0.005 for 0.5%],
  "reasoning": "Your detailed explanation for all recommendations"
}

IMPORTANT: Return ONLY the raw JSON object without any markdown formatting or additional text.
"""
    
    def get_trading_decision(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        시장 데이터를 바탕으로 AI 트레이딩 결정을 요청
        
        Args:
            market_data: 시장 분석 데이터
            
        Returns:
            AI 트레이딩 결정 결과
            
        Raises:
            ValueError: JSON 파싱 실패 시
            Exception: API 호출 실패 시
        """
        try:
            # 프롬프트 구성
            full_prompt = f"{self.system_prompt}\n\nMarket Data Analysis:\n{json.dumps(market_data, indent=2, default=str)}"
            
            # Gemini API 호출
            response = self.model.generate_content(full_prompt)
            response_text = response.text.strip()
            
            print(f"Raw Gemini response: {response_text[:200]}...")  # 처음 200자만 출력
            
            # JSON 응답 정리
            cleaned_response = self._clean_json_response(response_text)
            
            # JSON 파싱
            trading_decision = json.loads(cleaned_response)
            
            # 응답 검증
            self._validate_response(trading_decision)
            
            return trading_decision
            
        except json.JSONDecodeError as e:
            print(f"JSON 파싱 오류: {e}")
            print(f"Gemini 응답: {response_text}")
            raise ValueError(f"Invalid JSON response from Gemini: {e}")
        except Exception as e:
            print(f"Gemini API 호출 오류: {e}")
            raise
    
    def _clean_json_response(self, response_text: str) -> str:
        """
        Gemini 응답에서 JSON 부분만 추출
        
        Args:
            response_text: 원본 응답 텍스트
            
        Returns:
            정리된 JSON 문자열
        """
        # JSON 코드 블록 제거
        if "```json" in response_text:
            start_idx = response_text.find("```json") + 7
            end_idx = response_text.find("```", start_idx)
            if end_idx != -1:
                return response_text[start_idx:end_idx].strip()
        elif "```" in response_text:
            parts = response_text.split("```")
            if len(parts) >= 3:
                return parts[1].strip()
        
        return response_text
    
    def _validate_response(self, trading_decision: Dict[str, Any]) -> None:
        """
        AI 응답의 유효성 검증
        
        Args:
            trading_decision: AI 응답 데이터
            
        Raises:
            ValueError: 필수 필드 누락 또는 값이 유효하지 않을 때
        """
        required_fields = [
            'direction', 'recommended_position_size', 'recommended_leverage',
            'stop_loss_percentage', 'take_profit_percentage', 'reasoning'
        ]
        
        # 필수 필드 확인
        for field in required_fields:
            if field not in trading_decision:
                raise ValueError(f"Missing required field: {field}")
        
        # 값 범위 검증
        direction = trading_decision['direction']
        if direction not in ['LONG', 'SHORT', 'NO_POSITION']:
            raise ValueError(f"Invalid direction: {direction}")
        
        position_size = trading_decision['recommended_position_size']
        if not (0.1 <= position_size <= 1.0):
            raise ValueError(f"Position size out of range: {position_size}")
        
        leverage = trading_decision['recommended_leverage']
        if not (1 <= leverage <= 20):
            raise ValueError(f"Leverage out of range: {leverage}")
        
        sl_pct = trading_decision['stop_loss_percentage']
        tp_pct = trading_decision['take_profit_percentage']
        if not (0 < sl_pct < 1) or not (0 < tp_pct < 1):
            raise ValueError(f"Invalid SL/TP percentages: SL={sl_pct}, TP={tp_pct}")
    
    def print_decision(self, trading_decision: Dict[str, Any]) -> None:
        """
        트레이딩 결정 내용을 콘솔에 출력
        
        Args:
            trading_decision: AI 트레이딩 결정 결과
        """
        print(f"\n=== Gemini AI Trading Decision ===")
        print(f"Direction: {trading_decision['direction']}")
        print(f"Position Size: {trading_decision['recommended_position_size']*100:.1f}%")
        print(f"Leverage: {trading_decision['recommended_leverage']}x")
        print(f"Stop Loss: {trading_decision['stop_loss_percentage']*100:.2f}%")
        print(f"Take Profit: {trading_decision['take_profit_percentage']*100:.2f}%")
        print(f"Reasoning: {trading_decision['reasoning'][:100]}...")
        print("==================================")