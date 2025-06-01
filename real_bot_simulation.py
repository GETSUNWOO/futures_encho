#!/usr/bin/env python3
"""
실제 트레이딩 봇 Gemini API 호출 시뮬레이션
- 실제 봇과 동일한 프롬프트 크기 및 구조
- 60초 간격으로 연속 호출
- 429 에러 재현 및 분석
- 실제 시장 데이터와 유사한 크기의 데이터 생성

사용법: python real_bot_simulation.py
"""

import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
import random

# 패키지 설치 확인
try:
    from dotenv import load_dotenv
    import google.generativeai as genai
    import pandas as pd
except ImportError as e:
    print(f"❌ 필수 패키지가 설치되지 않았습니다: {e}")
    print("다음 명령어로 설치하세요:")
    print("pip install python-dotenv google-generativeai pandas")
    sys.exit(1)

# 환경변수 로드
load_dotenv()

class RealBotSimulator:
    """실제 트레이딩 봇의 Gemini API 호출 시뮬레이션"""
    
    def __init__(self):
        """초기화"""
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            print("❌ GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
            sys.exit(1)
        
        # API 설정 (실제 봇과 동일)
        genai.configure(api_key=self.api_key)
        self.model_name = 'gemini-2.0-flash-lite'  # 실제 봇과 동일
        self.model = genai.GenerativeModel(self.model_name)
        
        # 시뮬레이션 상태
        self.simulation_count = 0
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.errors = []
        self.request_logs = []
        
        print("🤖 실제 트레이딩 봇 API 시뮬레이션 시작")
        print(f"   모델: {self.model_name}")
        print(f"   API Key: ...{self.api_key[-8:]}")
    
    def generate_realistic_timeframe_data(self, timeframe, limit):
        """실제와 같은 타임프레임 데이터 생성"""
        base_price = 103865.20
        data = []
        
        for i in range(limit):
            # 실제 변동성을 모방한 가격 생성
            price_change = random.uniform(-0.02, 0.02)  # ±2% 변동
            current_price = base_price * (1 + price_change)
            
            # 고가/저가 생성
            high_change = random.uniform(0, 0.005)
            low_change = random.uniform(-0.005, 0)
            
            candle = {
                "timestamp": (datetime.now() - timedelta(minutes=15*i)).isoformat(),
                "open": round(current_price * random.uniform(0.998, 1.002), 2),
                "high": round(current_price * (1 + high_change), 2),
                "low": round(current_price * (1 + low_change), 2),
                "close": round(current_price, 2),
                "volume": round(random.uniform(50, 200), 3)
            }
            data.append(candle)
        
        return data
    
    def generate_realistic_news_data(self, count=10):
        """실제와 같은 뉴스 데이터 생성"""
        news_templates = [
            "Bitcoin Surges to New All-Time High as Institutional Adoption Accelerates",
            "Major US Bank Announces Bitcoin Treasury Holdings Worth $1.2 Billion",
            "Federal Reserve Chair Comments on Cryptocurrency Regulation Framework",
            "Tesla Reports Additional Bitcoin Purchases in Q4 Financial Statement",
            "JPMorgan Launches Bitcoin Trading Services for Institutional Clients",
            "MicroStrategy Increases Bitcoin Holdings by Additional 2,000 BTC",
            "El Salvador Announces Plans for Bitcoin Mining Facility Expansion",
            "Ethereum Foundation Discusses Impact of Bitcoin ETF Approvals",
            "Goldman Sachs Initiates Coverage on Bitcoin with Buy Rating",
            "BlackRock CEO Bullish on Bitcoin's Long-term Institutional Demand"
        ]
        
        news_data = []
        for i in range(count):
            news_item = {
                "title": random.choice(news_templates),
                "date": f"{random.randint(1, 12)} hours ago"
            }
            news_data.append(news_item)
        
        return news_data
    
    def generate_realistic_historical_data(self, limit=10):
        """실제와 같은 과거 거래 데이터 생성"""
        historical_data = []
        
        for i in range(limit):
            action = random.choice(['long', 'short'])
            entry_price = random.uniform(95000, 105000)
            exit_price = entry_price * random.uniform(0.97, 1.03)
            amount = round(random.uniform(0.001, 0.1), 3)
            
            profit_loss = (exit_price - entry_price) * amount if action == 'long' else (entry_price - exit_price) * amount
            profit_loss_percentage = (profit_loss / (entry_price * amount)) * 100
            
            trade = {
                "trade_id": i + 1,
                "trade_timestamp": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
                "action": action,
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "amount": amount,
                "leverage": random.randint(1, 10),
                "sl_price": round(entry_price * (0.98 if action == 'long' else 1.02), 2),
                "tp_price": round(entry_price * (1.02 if action == 'long' else 0.98), 2),
                "sl_percentage": round(random.uniform(0.01, 0.03), 3),
                "tp_percentage": round(random.uniform(0.01, 0.03), 3),
                "position_size_percentage": round(random.uniform(0.1, 0.3), 2),
                "status": "CLOSED",
                "profit_loss": round(profit_loss, 2),
                "profit_loss_percentage": round(profit_loss_percentage, 2),
                "analysis_id": i + 1,
                "reasoning": "Market showed strong momentum with positive technical indicators.",
                "direction": action.upper(),
                "recommended_leverage": random.randint(1, 10),
                "recommended_position_size": round(random.uniform(0.1, 0.3), 2),
                "stop_loss_percentage": round(random.uniform(0.01, 0.03), 3),
                "take_profit_percentage": round(random.uniform(0.01, 0.03), 3)
            }
            historical_data.append(trade)
        
        return historical_data
    
    def generate_realistic_performance_metrics(self):
        """실제와 같은 성과 메트릭스 생성"""
        total_trades = random.randint(20, 50)
        winning_trades = int(total_trades * random.uniform(0.4, 0.7))
        losing_trades = total_trades - winning_trades
        
        return {
            "overall": {
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "total_profit_loss": round(random.uniform(-500, 1500), 2),
                "avg_profit_loss_percentage": round(random.uniform(-1, 3), 2),
                "max_profit_percentage": round(random.uniform(5, 15), 2),
                "max_loss_percentage": round(random.uniform(-8, -2), 2),
                "avg_win_percentage": round(random.uniform(2, 6), 2),
                "avg_loss_percentage": round(random.uniform(-4, -1), 2),
                "win_rate": round((winning_trades / total_trades) * 100, 1)
            },
            "directional": {
                "long": {
                    "total_trades": int(total_trades * 0.6),
                    "winning_trades": int(winning_trades * 0.6),
                    "losing_trades": int(losing_trades * 0.6),
                    "total_profit_loss": round(random.uniform(0, 800), 2),
                    "avg_profit_loss_percentage": round(random.uniform(1, 4), 2),
                    "win_rate": round(random.uniform(50, 75), 1)
                },
                "short": {
                    "total_trades": int(total_trades * 0.4),
                    "winning_trades": int(winning_trades * 0.4),
                    "losing_trades": int(losing_trades * 0.4),
                    "total_profit_loss": round(random.uniform(-200, 400), 2),
                    "avg_profit_loss_percentage": round(random.uniform(-1, 2), 2),
                    "win_rate": round(random.uniform(40, 65), 1)
                }
            }
        }
    
    def create_real_bot_prompt(self):
        """실제 봇과 동일한 프롬프트 생성"""
        
        # 실제 봇의 시스템 프롬프트 (동일)
        system_prompt = """
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

For LONG or SHORT positions:
{
  "direction": "LONG" or "SHORT",
  "recommended_position_size": [decimal between 0.1-1.0, e.g., 0.25 for 25%],
  "recommended_leverage": [integer between 1-20],
  "stop_loss_percentage": [percentage as decimal, e.g., 0.005 for 0.5%],
  "take_profit_percentage": [percentage as decimal, e.g., 0.015 for 1.5%],
  "reasoning": "Your detailed explanation for all recommendations"
}

For NO_POSITION (when market conditions are unclear or risky):
{
  "direction": "NO_POSITION",
  "recommended_position_size": 0.0,
  "recommended_leverage": 1,
  "stop_loss_percentage": 0.005,
  "take_profit_percentage": 0.015,
  "reasoning": "Your detailed explanation for why no position is recommended"
}

IMPORTANT: 
- Return ONLY the raw JSON object without any markdown formatting or additional text.
- For NO_POSITION, always set recommended_position_size to 0.0
- For LONG/SHORT, recommended_position_size must be between 0.1 and 1.0
"""
        
        # 실제 봇과 동일한 시장 데이터 구조 생성
        market_analysis = {
            "timestamp": datetime.now().isoformat(),
            "current_price": 103865.20,
            "timeframes": {
                "15m": self.generate_realistic_timeframe_data("15m", 96),  # 실제 봇과 동일한 개수
                "1h": self.generate_realistic_timeframe_data("1h", 48),
                "4h": self.generate_realistic_timeframe_data("4h", 30)
            },
            "recent_news": self.generate_realistic_news_data(10),
            "historical_trading_data": self.generate_realistic_historical_data(10),
            "performance_metrics": self.generate_realistic_performance_metrics()
        }
        
        # 실제 봇과 동일한 프롬프트 구성
        full_prompt = f"{system_prompt}\n\nMarket Data Analysis:\n{json.dumps(market_analysis, indent=2, default=str)}"
        
        return full_prompt, market_analysis
    
    def estimate_tokens(self, text):
        """토큰 수 추정"""
        # 더 정확한 토큰 추정 (영문 기준)
        words = len(text.split())
        chars = len(text)
        # OpenAI 토큰 기준으로 추정 (1토큰 ≈ 4문자 또는 0.75단어)
        token_estimate = max(chars // 4, int(words / 0.75))
        return token_estimate
    
    def single_simulation_request(self):
        """단일 시뮬레이션 요청 (실제 봇과 동일)"""
        self.simulation_count += 1
        self.total_requests += 1
        
        print(f"\n🤖 시뮬레이션 요청 #{self.simulation_count}")
        print("-" * 50)
        
        # 실제 봇과 동일한 프롬프트 생성
        full_prompt, market_data = self.create_real_bot_prompt()
        
        # 토큰 사용량 분석 (실제 봇과 동일한 방식)
        estimated_tokens = self.estimate_tokens(full_prompt)
        print(f"📊 추정 입력 토큰: {estimated_tokens:,}")
        print(f"📝 프롬프트 길이: {len(full_prompt):,} 문자")
        print(f"🔢 타임프레임 데이터 개수: 15m({len(market_data['timeframes']['15m'])}), 1h({len(market_data['timeframes']['1h'])}), 4h({len(market_data['timeframes']['4h'])})")
        print(f"📰 뉴스 개수: {len(market_data['recent_news'])}")
        print(f"📈 과거 거래 개수: {len(market_data['historical_trading_data'])}")
        
        start_time = time.time()
        
        try:
            print("🚀 Gemini API 호출 중...")
            response = self.model.generate_content(full_prompt)
            
            end_time = time.time()
            response_time = end_time - start_time
            
            # 응답 분석
            response_tokens = self.estimate_tokens(response.text)
            total_tokens = estimated_tokens + response_tokens
            
            # 성공 로그
            print(f"✅ 요청 성공!")
            print(f"⏱️  응답 시간: {response_time:.2f}초")
            print(f"📝 응답 길이: {len(response.text):,} 문자")
            print(f"🔢 추정 응답 토큰: {response_tokens:,}")
            print(f"🎯 총 토큰 사용량: {total_tokens:,}")
            
            # JSON 파싱 시도
            try:
                response_text = response.text.strip()
                if "```json" in response_text:
                    start_idx = response_text.find("```json") + 7
                    end_idx = response_text.find("```", start_idx)
                    if end_idx != -1:
                        response_text = response_text[start_idx:end_idx].strip()
                
                trading_decision = json.loads(response_text)
                print(f"🎯 AI 결정: {trading_decision['direction']} (크기: {trading_decision.get('recommended_position_size', 0)*100:.1f}%)")
                print(f"💡 이유: {trading_decision['reasoning'][:100]}...")
                
            except json.JSONDecodeError:
                print(f"⚠️  JSON 파싱 실패 - 응답 미리보기: {response.text[:200]}...")
            
            # 성공 기록
            self.successful_requests += 1
            log_entry = {
                'timestamp': datetime.now(),
                'simulation_number': self.simulation_count,
                'response_time': response_time,
                'estimated_input_tokens': estimated_tokens,
                'estimated_response_tokens': response_tokens,
                'estimated_total_tokens': total_tokens,
                'success': True,
                'error': None
            }
            self.request_logs.append(log_entry)
            
            return True
            
        except Exception as e:
            end_time = time.time()
            response_time = end_time - start_time
            
            # 실패 로그
            print(f"❌ 요청 실패!")
            print(f"⏱️  에러까지 시간: {response_time:.2f}초")
            print(f"🚨 에러 타입: {type(e).__name__}")
            print(f"📝 에러 메시지: {str(e)}")
            
            # 429 에러 상세 분석
            if '429' in str(e):
                print(f"\n🔍 429 에러 상세 분석:")
                error_str = str(e).lower()
                
                if 'quota' in error_str:
                    print("   📊 할당량(Quota) 초과")
                if 'requests per minute' in error_str:
                    print("   ⏰ 분당 요청 수(RPM) 제한")
                if 'tokens per minute' in error_str:
                    print("   🔢 분당 토큰 수(TPM) 제한")
                if 'generativelanguage.googleapis.com' in error_str:
                    print("   🌐 Google AI API 엔드포인트")
                if 'free tier' in error_str:
                    print("   🆓 무료 티어 제한")
                if 'tier 1' in error_str:
                    print("   🥈 Tier 1 제한")
                
                print(f"   📊 이 요청의 토큰 사용량: {estimated_tokens:,}")
                print(f"   📈 누적 토큰 사용량: {sum(log['estimated_total_tokens'] for log in self.request_logs):,}")
            
            # 실패 기록
            self.failed_requests += 1
            error_entry = {
                'timestamp': datetime.now(),
                'simulation_number': self.simulation_count,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'estimated_tokens': estimated_tokens,
                'response_time': response_time
            }
            self.errors.append(error_entry)
            
            log_entry = {
                'timestamp': datetime.now(),
                'simulation_number': self.simulation_count,
                'response_time': response_time,
                'estimated_input_tokens': estimated_tokens,
                'estimated_response_tokens': 0,
                'estimated_total_tokens': estimated_tokens,
                'success': False,
                'error': str(e)
            }
            self.request_logs.append(log_entry)
            
            return False
    
    def run_continuous_simulation(self, max_requests=10, interval=60):
        """연속 시뮬레이션 실행 (실제 봇과 동일한 60초 간격)"""
        print(f"\n🔄 연속 시뮬레이션 시작")
        print(f"   최대 요청 수: {max_requests}")
        print(f"   요청 간격: {interval}초")
        print(f"   예상 총 시간: {max_requests * interval // 60}분 {max_requests * interval % 60}초")
        print("="*60)
        
        start_time = datetime.now()
        
        for i in range(max_requests):
            print(f"\n⏰ 시뮬레이션 진행: {i+1}/{max_requests}")
            print(f"🕐 현재 시간: {datetime.now().strftime('%H:%M:%S')}")
            
            # 실제 봇과 동일한 요청 실행
            success = self.single_simulation_request()
            
            if not success:
                print(f"\n⚠️  에러 발생으로 시뮬레이션 중단할지 선택하세요.")
                choice = input("계속 하시겠습니까? (y/N): ").lower()
                if choice != 'y':
                    print("🛑 사용자가 시뮬레이션을 중단했습니다.")
                    break
            
            # 중간 결과 출력
            success_rate = (self.successful_requests / self.total_requests) * 100
            total_tokens = sum(log['estimated_total_tokens'] for log in self.request_logs)
            print(f"📊 중간 결과: 성공률 {success_rate:.1f}% ({self.successful_requests}/{self.total_requests}), 누적 토큰: {total_tokens:,}")
            
            # 마지막 요청이 아니면 대기
            if i < max_requests - 1:
                print(f"\n⏳ {interval}초 대기 중... (Ctrl+C로 중단 가능)")
                try:
                    time.sleep(interval)
                except KeyboardInterrupt:
                    print(f"\n🛑 사용자가 시뮬레이션을 중단했습니다.")
                    break
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        # 최종 결과 출력
        self.print_final_results(duration)
    
    def print_final_results(self, duration):
        """최종 결과 출력"""
        print(f"\n" + "="*60)
        print("🏁 시뮬레이션 완료 - 최종 결과")
        print("="*60)
        
        print(f"🕐 총 실행 시간: {duration}")
        print(f"🔢 총 요청 수: {self.total_requests}")
        print(f"✅ 성공한 요청: {self.successful_requests}")
        print(f"❌ 실패한 요청: {self.failed_requests}")
        print(f"📈 성공률: {(self.successful_requests / max(self.total_requests, 1)) * 100:.1f}%")
        
        if self.request_logs:
            # 토큰 사용량 분석
            total_tokens = sum(log['estimated_total_tokens'] for log in self.request_logs)
            avg_tokens = total_tokens / len(self.request_logs)
            max_tokens = max(log['estimated_total_tokens'] for log in self.request_logs)
            
            print(f"\n📊 토큰 사용량 분석:")
            print(f"   총 토큰 사용량: {total_tokens:,}")
            print(f"   평균 토큰/요청: {avg_tokens:,.0f}")
            print(f"   최대 토큰/요청: {max_tokens:,}")
            
            # 응답 시간 분석
            successful_logs = [log for log in self.request_logs if log['success']]
            if successful_logs:
                avg_response_time = sum(log['response_time'] for log in successful_logs) / len(successful_logs)
                max_response_time = max(log['response_time'] for log in successful_logs)
                print(f"\n⏱️  응답 시간 분석:")
                print(f"   평균 응답 시간: {avg_response_time:.2f}초")
                print(f"   최대 응답 시간: {max_response_time:.2f}초")
        
        # 에러 분석
        if self.errors:
            print(f"\n🚨 에러 분석:")
            print(f"   총 에러 수: {len(self.errors)}")
            
            # 429 에러 분석
            error_429_count = sum(1 for e in self.errors if '429' in str(e['error_message']))
            if error_429_count > 0:
                print(f"   🎯 429 Rate Limit 에러: {error_429_count}건")
                print(f"   📊 첫 429 에러 발생 시점: 요청 #{self.errors[0]['simulation_number']}")
                
                # 첫 429 에러까지의 토큰 사용량
                first_429_idx = next(i for i, e in enumerate(self.errors) if '429' in str(e['error_message']))
                tokens_until_429 = sum(log['estimated_total_tokens'] for log in self.request_logs[:first_429_idx+1])
                print(f"   🔢 429 에러까지 누적 토큰: {tokens_until_429:,}")
            
            # 에러 상세 목록
            print(f"\n📋 에러 상세:")
            for i, error in enumerate(self.errors[:5], 1):  # 최대 5개만 표시
                time_str = error['timestamp'].strftime('%H:%M:%S')
                print(f"   {i}. [{time_str}] 요청#{error['simulation_number']}: {error['error_type']}")
                print(f"      {error['error_message'][:120]}...")
        
        # 결론 및 권장사항
        print(f"\n🔍 결론:")
        if error_429_count > 0:
            print("   🎯 실제 봇과 동일한 429 Rate Limit 에러 재현 성공!")
            print("   💡 원인: 대용량 프롬프트(8000+ 토큰)의 연속 요청")
            print("   🛠️  해결책: 요청 간격 증가 또는 프롬프트 크기 축소 필요")
        else:
            print("   ✅ 429 에러 없이 모든 요청 성공")
            print("   💡 현재 API 제한 내에서 정상 작동 중")
        
        print(f"\n📈 실제 봇 적용 권장사항:")
        if self.successful_requests > 0:
            avg_tokens = sum(log['estimated_total_tokens'] for log in self.request_logs if log['success']) / self.successful_requests
            if error_429_count > 0:
                print(f"   ⏰ 요청 간격을 90-120초로 증가 권장")
                print(f"   📊 프롬프트 크기 최적화 검토 (현재 평균: {avg_tokens:,.0f} 토큰)")
            else:
                print(f"   ✅ 현재 60초 간격으로 안정적 운영 가능")
                print(f"   📊 평균 토큰 사용량: {avg_tokens:,.0f} (안전 수준)")


def main():
    """메인 시뮬레이션 실행"""
    print("🤖 실제 트레이딩 봇 Gemini API 시뮬레이션")
    print("="*60)
    print("이 시뮬레이션은 실제 봇과 동일한 조건으로 API를 호출합니다:")
    print("- 동일한 프롬프트 크기 (8000+ 토큰)")
    print("- 동일한 데이터 구조 (타임프레임, 뉴스, 과거 거래)")
    print("- 동일한 요청 간격 (60초)")
    print("- 동일한 모델 (gemini-2.0-flash-lite)")
    print("="*60)
    
    try:
        simulator = RealBotSimulator()
        
        # 시뮬레이션 옵션 선택
        print(f"\n📋 시뮬레이션 옵션:")
        print("1. 단일 요청 테스트 (1회)")
        print("2. 짧은 시뮬레이션 (3회, 60초 간격)")
        print("3. 표준 시뮬레이션 (5회, 60초 간격)")
        print("4. 긴 시뮬레이션 (10회, 60초 간격)")
        print("5. 커스텀 시뮬레이션")
        
        choice = input("\n선택하세요 (1-5): ").strip()
        
        if choice == '1':
            simulator.single_simulation_request()
            simulator.print_final_results(timedelta(seconds=0))
            
        elif choice == '2':
            simulator.run_continuous_simulation(max_requests=3, interval=60)
            
        elif choice == '3':
            simulator.run_continuous_simulation(max_requests=5, interval=60)
            
        elif choice == '4':
            simulator.run_continuous_simulation(max_requests=10, interval=60)
            
        elif choice == '5':
            try:
                max_requests = int(input("요청 횟수 (1-20): "))
                interval = int(input("요청 간격(초) (10-300): "))
                
                if 1 <= max_requests <= 20 and 10 <= interval <= 300:
                    simulator.run_continuous_simulation(max_requests=max_requests, interval=interval)
                else:
                    print("❌ 잘못된 값입니다.")
            except ValueError:
                print("❌ 숫자를 입력해주세요.")
        else:
            print("❌ 잘못된 선택입니다.")
        
    except KeyboardInterrupt:
        print("\n🛑 사용자가 시뮬레이션을 중단했습니다")
    except Exception as e:
        print(f"\n💥 시뮬레이션 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()