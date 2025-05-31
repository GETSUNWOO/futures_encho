
"""
AI 비트코인 트레이딩 봇 V2 - 모듈화된 메인 루프
- 실거래/시뮬레이션 모드 지원
- Gemini AI 기반 트레이딩 결정
- 자동 포지션 관리 및 성과 추적
- 모드별 DB 분리 적용
"""
import time
import ccxt
import os
from datetime import datetime
from typing import Optional

# 모듈 임포트
from config import Config
from data.market_fetcher import MarketFetcher
from analysis.gemini_interface import GeminiInterface
from database.recorder import DatabaseRecorder
from trading.base_executor import BaseExecutor
from trading.real_executor import RealExecutor
from trading.test_executor import TestExecutor


class TradingBot:
    """AI 트레이딩 봇 메인 클래스"""
    
    def __init__(self):
        """초기화"""
        # 설정 출력
        Config.print_config_summary()

        # 안전장치용 상태 변수 추가
        self._last_action_time = 0
        self._position_processing = False

        # 로깅 시스템용 상태 변수
        self._position_log_count = 0
        self._max_position_logs = 3

        # 데이터베이스 초기화
        self.recorder = DatabaseRecorder(Config.get_db_file())
        
        # Gemini AI 초기화
        self.ai = GeminiInterface(Config.GEMINI_API_KEY)
        
        # 거래소 및 실행기 초기화
        self.exchange = None
        self.market_fetcher = None
        self.executor = None
        self._setup_trading_components()
        
        print(f"\n=== Bitcoin Trading Bot Started ===")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Mode: {Config.get_trading_mode_display()}")
        print(f"AI Model: {self.ai.get_model_name()}")
        print(f"Loop Intervals:")
        print(f"  - With position: 5s (fast monitoring)")
        print(f"  - No position: 60s (normal interval)")
        print("===================================\n")
        print("===================================\n")
    
    def _clear_screen_lines(self, num_lines: int):
        """화면에서 지정된 줄 수만큼 삭제"""
        for _ in range(num_lines):
            # 커서를 위로 이동하고 해당 줄 삭제
            print("\033[A\033[K", end="")

    def _setup_trading_components(self) -> None:
        """거래 관련 컴포넌트 설정"""
        if Config.is_real_trading():
            # 실거래 모드
            self.exchange = ccxt.binance({
                'apiKey': Config.BINANCE_API_KEY,
                'secret': Config.BINANCE_SECRET_KEY,
                **Config.BINANCE_CONFIG  # 여기에 'defaultType': 'future' 포함됨
            })
            self.market_fetcher = MarketFetcher(self.exchange, Config.SERP_API_KEY)
            self.executor = RealExecutor(self.exchange)

            print("🔴 Real trading mode - using FUTURES")

        else:
            # 시뮬레이션 모드 - 선물 설정으로 통일
            self.exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # 시뮬레이션도 선물로 설정!
                    'adjustForTimeDifference': True
                }
            })
            self.market_fetcher = MarketFetcher(self.exchange, Config.SERP_API_KEY)
            self.executor = TestExecutor(Config.INITIAL_TEST_BALANCE)

            print("🟡 Test mode - using FUTURES data (simulation)")
            print(f"📊 Market data will be fetched from futures market")
    
    def run(self) -> None:
        """메인 트레이딩 루프 - 포지션 유무에 따른 간격 조절"""
        loop_counter = 0
        
        try:
            while True:
                loop_counter += 1
                current_time = datetime.now().strftime('%H:%M:%S')
                current_price = self.market_fetcher.fetch_current_price()
                
                if not current_price:
                    print("❌ Failed to fetch current price. Retrying...")
                    time.sleep(5)
                    continue
                
                # 시뮬레이션 모드에서 현재가 업데이트
                if Config.is_test_trading():
                    self.executor.update_market_price(current_price)
                
                # 현재 포지션 확인
                position_status = self.executor.check_position_status()
                
                if position_status['is_open']:
                    # 포지션 있을 때: 빠른 모니터링 (5초)
                    self._handle_open_position(position_status, current_price)
                    sleep_time = 5
                else:
                    # 포지션 없을 때: 일반 간격 (60초) - 깔끔한 출력
                    print(f"\n[{current_time}] Current BTC Price: ${current_price:,.2f}")
                    self._handle_no_position(current_price)
                    sleep_time = 60
                    print(f"⏰ No position - next check in {sleep_time}s\n")
                
                # 대기
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Bot stopped by user")
            self._cleanup()
        except Exception as e:
            print(f"\n💥 Unexpected error: {e}")
            self._cleanup()
    
    def _handle_open_position(self, position_status: dict, current_price: float) -> None:
        """포지션이 있을 때 처리 - 깔끔한 로깅"""
        
        # 중복 처리 방지
        if self._position_processing:
            return
        
        # 시간 기반 중복 방지 (1초 이내 중복 차단)
        current_time = time.time()
        if current_time - self._last_action_time < 1.0:
            return
        
        self._position_processing = True
        self._last_action_time = current_time
        
        try:
            side = position_status['side']
            amount = position_status['amount']
            unrealized_pnl = position_status.get('unrealized_pnl', 0)
            
            # 로그 카운트 관리
            self._position_log_count += 1
            
            # 3개 초과시 이전 로그 삭제 (queue 방식)
            if self._position_log_count > self._max_position_logs:
                # 이전 3줄 삭제 (시간, 포지션 정보, 다음 체크 메시지)
                self._clear_screen_lines(3)
            
            # 현재 상태 출력
            current_time_str = datetime.now().strftime('%H:%M:%S')
            print(f"[{current_time_str}] Price: ${current_price:,.2f} | Position: {side.upper()} {amount} BTC | P/L: ${unrealized_pnl:+,.2f}")
            
            # 데이터베이스에서 현재 거래 정보 확인
            current_trade = self.recorder.get_latest_open_trade()
            if not current_trade:
                print("⚠️  Warning: Open position found but no trade record in database")
                return
            
            # 시뮬레이션 모드에서 SL/TP 트리거 확인
            if Config.is_test_trading():
                trigger = self.executor.check_sl_tp_triggers(
                    current_price, 
                    current_trade['sl_price'], 
                    current_trade['tp_price']
                )
                
                if trigger:
                    print(f"\n🎯 {trigger.upper()} triggered!")
                    close_result = self.executor.close_position(reason=trigger)
                    if close_result['success']:
                        self._update_trade_closure(current_trade['id'], close_result)
                        self.executor.print_position_closed(close_result)
                        self.recorder.print_trade_summary(days=7)
                        
                        # 포지션 종료시 로그 카운트 리셋
                        self._position_log_count = 0
                    return
            
            # 다음 체크 안내 (SL/TP 트리거되지 않은 경우에만)
            print("📊 Monitoring position - next check in 5s")
    
        finally:
            # 처리 완료 후 플래그 해제
            self._position_processing = False
    
    def _handle_no_position(self, current_price: float) -> None:
        """포지션이 없을 때 처리"""
        
        # 포지션 종료시 로그 카운트 리셋
        self._position_log_count = 0
        
        # 중복 호출 방지
        if hasattr(self, '_last_no_position_call'):
            time_diff = time.time() - self._last_no_position_call
            if time_diff < 1.0:
                return
        
        self._last_no_position_call = time.time()
        
        # 이전 거래가 종료되었는지 확인
        current_trade = self.recorder.get_latest_open_trade()
        if current_trade:
            close_result = {
                'success': True,
                'exit_price': current_price,
                'profit_loss': 0,
                'profit_loss_percentage': 0
            }
            self._update_trade_closure(current_trade['id'], close_result)
            print("✅ Previous position closed - updated database")
        
        # 미체결 주문 취소
        if Config.is_real_trading():
            self.market_fetcher.cancel_all_orders()
        
        print("🔍 No position. Analyzing market...")
        time.sleep(5)
        
        # 시장 분석 및 AI 결정
        trading_decision = self._get_ai_decision(current_price)
        
        if trading_decision['direction'] == 'NO_POSITION':
            print("🤖 AI recommends NO_POSITION - waiting...")
            return
        
        # 포지션 진입
        self._enter_position(trading_decision, current_price)
    
    def _get_ai_decision(self, current_price: float) -> dict:
        """AI 트레이딩 결정 획득"""
        print("Collecting market data...")
        
        # 시장 데이터 수집
        multi_tf_data = self.market_fetcher.fetch_multi_timeframe_data()
        recent_news = self.market_fetcher.fetch_bitcoin_news()
        historical_data = self.recorder.get_historical_trading_data(limit=10)
        performance_metrics = self.recorder.get_performance_metrics()
        
        # AI 분석용 데이터 구성
        market_analysis = {
            "timestamp": datetime.now().isoformat(),
            "current_price": current_price,
            "timeframes": {},
            "recent_news": recent_news,
            "historical_trading_data": historical_data,
            "performance_metrics": performance_metrics
        }
        
        # 타임프레임 데이터 변환
        for tf_name, df in multi_tf_data.items():
            if not df.empty:
                market_analysis["timeframes"][tf_name] = df.to_dict(orient="records")
        
        print("Requesting AI analysis...")
        
        # AI 분석 요청
        trading_decision = self.ai.get_trading_decision(market_analysis)
        self.ai.print_decision(trading_decision)
        
        # AI 분석 결과 저장
        analysis_data = {
            'current_price': current_price,
            'direction': trading_decision['direction'],
            'recommended_position_size': trading_decision['recommended_position_size'],
            'recommended_leverage': trading_decision['recommended_leverage'],
            'stop_loss_percentage': trading_decision['stop_loss_percentage'],
            'take_profit_percentage': trading_decision['take_profit_percentage'],
            'reasoning': trading_decision['reasoning']
        }
        analysis_id = self.recorder.save_ai_analysis(analysis_data)
        
        # 분석 ID를 결정에 추가 (나중에 거래와 연결용)
        trading_decision['_analysis_id'] = analysis_id
        
        return trading_decision
    
    def _enter_position(self, trading_decision: dict, current_price: float) -> None:
        """포지션 진입"""
        try:
            # 투자 금액 계산
            if Config.is_real_trading():
                available_balance = self.market_fetcher.get_account_balance()
            else:
                available_balance = self.executor.get_account_balance()
            
            position_size_pct = trading_decision['recommended_position_size']
            investment_amount = max(
                available_balance * position_size_pct,
                Config.MIN_INVESTMENT_AMOUNT
            )
            
            print(f"Investment amount: ${investment_amount:,.2f}")
            
            # 포지션 진입
            position_result = self.executor.open_position(
                trading_decision, investment_amount, current_price
            )
            
            # 거래 기록 저장
            trade_data = {
                'action': position_result['action'],
                'entry_price': position_result['entry_price'],
                'amount': position_result['amount'],
                'leverage': position_result['leverage'],
                'sl_price': position_result['sl_price'],
                'tp_price': position_result['tp_price'],
                'sl_percentage': position_result['sl_percentage'],
                'tp_percentage': position_result['tp_percentage'],
                'position_size_percentage': position_size_pct,
                'investment_amount': investment_amount
            }
            
            trade_id = self.recorder.save_trade(trade_data)
            self.executor.set_current_trade_id(trade_id)
            
            # AI 분석과 거래 연결
            analysis_id = trading_decision.get('_analysis_id')
            if analysis_id:
                self.recorder.link_analysis_to_trade(analysis_id, trade_id)
            
            # 결과 출력
            self.executor.print_position_opened(position_result)
            print(f"Reasoning: {trading_decision['reasoning'][:100]}...")
            
        except Exception as e:
            print(f"Error entering position: {e}")
    
    def _update_trade_closure(self, trade_id: int, close_result: dict) -> None:
        """거래 종료 정보 데이터베이스 업데이트"""
        if close_result['success']:
            self.recorder.update_trade_status(
                trade_id,
                'CLOSED',
                exit_price=close_result.get('exit_price'),
                exit_timestamp=datetime.now().isoformat(),
                profit_loss=close_result.get('profit_loss'),
                profit_loss_percentage=close_result.get('profit_loss_percentage')
            )
    
    def _cleanup(self) -> None:
        """정리 작업"""
        print("Performing cleanup...")
        
        # 시뮬레이션 모드에서 최종 요약 출력
        if Config.is_test_trading():
            self.executor.print_account_summary()
        
        # 거래 요약 출력
        self.recorder.print_trade_summary(days=7)
        
        print("Bot shutdown complete")


def main():
    """메인 함수"""
    bot = TradingBot()
    bot.run()


if __name__ == "__main__":
    main()