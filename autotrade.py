"""
AI 비트코인 트레이딩 봇 - 메모리 누수 방지 개선
- 정리 로직 강화
- 재시도 로직 적용
- 리소스 관리 개선
"""
import time
import ccxt
import signal
import sys
import gc
from datetime import datetime
from typing import Optional, Dict, Any

# 프로젝트 모듈 임포트
from config import Config
from data.market_fetcher import MarketFetcher
from database.recorder import DatabaseRecorder
from trading.base_executor import BaseExecutor
from trading.real_executor import RealExecutor
from trading.test_executor import TestExecutor

# 새로운 체인 시스템 임포트
from scheduler import get_scheduler, start_scheduler, stop_scheduler, on_trade_completed
from chains.decision_chain import make_trading_decision
from utils.db import get_chain_db, log_chain, close_db_connections
from utils.retry_utils import retry_on_market_data_error, retry_on_llm_error, safe_api_call
from llm_factory import clear_llm_cache, get_llm_cache_stats


class TradingBot:
    """LangChain 기반 AI 트레이딩 봇 - 메모리 관리 개선"""
    
    def __init__(self):
        """초기화"""
        # 설정 출력
        Config.print_config_summary()
        
        # 종료 핸들러 등록
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # 상태 변수
        self.is_running = False
        self.last_decision_time = 0
        self.position_check_count = 0
        self.cleanup_counter = 0  # 주기적 정리용 카운터
        
        # 기존 컴포넌트 초기화
        self.recorder = DatabaseRecorder(Config.get_db_file())
        self.chain_db = get_chain_db()
        
        # 거래소 및 실행기 초기화
        self.exchange = None
        self.market_fetcher = None
        self.executor = None
        self._setup_trading_components()
        
        # 스케줄러 초기화
        self.scheduler = get_scheduler()
        
        print(f"\n" + "="*70)
        print("       🤖 AI 비트코인 트레이딩 봇 - LangChain 시스템")
        print("="*70)
        print(f"🕐 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"⚙️  모드: {Config.get_trading_mode_display()}")
        print(f"🧠 AI 시스템: 멀티 모델 체인 아키텍처")
        print(f"📊 켈리 공식: {'✅ 활성화' if Config.USE_KELLY_CRITERION else '❌ 비활성화'}")
        print()
        print("📋 시스템 구성요소:")
        print("  🔄 백그라운드 스케줄러: 체인 실행 관리")
        print("  🧠 의사결정 체인: 실시간 트레이딩 결정") 
        print("  📰 뉴스 체인: 감성 분석 (2시간 주기)")
        print("  📈 시장 체인: 기술적 분석 (1시간/4시간 주기)")
        print("  📊 성과 체인: 트레이딩 피드백 (1시간 주기)")
        print("="*70 + "\n")
    
    def _setup_trading_components(self) -> None:
        """거래 관련 컴포넌트 설정"""
        if Config.is_real_trading():
            # 실거래 모드
            self.exchange = ccxt.binance({
                'apiKey': Config.BINANCE_API_KEY,
                'secret': Config.BINANCE_SECRET_KEY,
                **Config.BINANCE_CONFIG
            })
            self.market_fetcher = MarketFetcher(self.exchange, Config.SERP_API_KEY)
            self.executor = RealExecutor(self.exchange)
            print("🔴 실거래 컴포넌트 초기화 완료")
        else:
            # 시뮬레이션 모드
            self.exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True
                }
            })
            self.market_fetcher = MarketFetcher(self.exchange, Config.SERP_API_KEY)
            self.executor = TestExecutor(Config.INITIAL_TEST_BALANCE)
            print("🟡 테스트 거래 컴포넌트 초기화 완료")
    
    def run(self) -> None:
            """메인 트레이딩 루프 - 강력한 초기화 정책"""
            try:
                # 스케줄러 시작 및 초기화 대기 (강력한 정책)
                print("🔄 백그라운드 체인 스케줄러 시작 중...")
                print("🛡️ 안전 정책: 모든 체인이 성공해야 거래 시작")
                print("⚡ 필수 체인 데이터 수집 대기 중...")
                
                # 초기화 성공 필수
                init_success = start_scheduler(wait_for_init=True, timeout=600)  # 10분 대기
                
                if not init_success:
                    print("💥 치명적 에러: 필수 체인 초기화 실패")
                    print("🛡️ 안전을 위해 거래를 시작하지 않습니다")
                    print("🔧 로그를 확인하고 문제를 해결한 후 다시 시도하세요")
                    
                    # 초기화 상태 출력
                    from scheduler import get_initialization_status
                    init_status = get_initialization_status()
                    print(f"\n📊 초기화 결과: {init_status['success_count']}/{init_status['total_count']} 체인")
                    
                    for chain_name, result in init_status['results'].items():
                        status = "✅" if result.get('success') else "❌"
                        error = result.get('error', '')
                        print(f"   {status} {chain_name}: {error}")
                    
                    # 시스템 종료
                    self._cleanup()
                    return
                
                # === 모든 체인 성공 - 거래 시작 ===
                print("✅ 모든 필수 체인 초기화 성공! 🎉")
                print("🚀 AI 트레이딩 시스템 완전 가동 시작")
                
                # 초기화 상태 출력
                from scheduler import get_initialization_status, print_scheduler_status
                init_status = get_initialization_status()
                print(f"📊 초기화 결과: {init_status['success_count']}/{init_status['total_count']} 체인 성공")
                
                # 간단한 상태 요약
                print_scheduler_status()
                
                # 메인 루프 시작
                self.is_running = True
                print("🚀 메인 트레이딩 루프 시작...")
                print("⏰ 의사결정 간격: 포지션 있음: 5초 | 포지션 없음: 60초\n")
                
                while self.is_running:
                    try:
                        self._main_loop_iteration()
                        
                        # 주기적 정리 (100회마다)
                        self.cleanup_counter += 1
                        if self.cleanup_counter >= 100:
                            self._periodic_cleanup()
                            self.cleanup_counter = 0
                            
                    except KeyboardInterrupt:
                        print("\n🛑 종료 신호 수신...")
                        break
                    except Exception as e:
                        log_chain("main_loop", "ERROR", f"메인 루프 에러: {e}")
                        print(f"❌ 루프 에러: {e}")
                        time.sleep(10)  # 에러 발생시 10초 대기
                        continue
                    
            except Exception as e:
                print(f"💥 메인 루프 치명적 에러: {e}")
                log_chain("main_loop", "CRITICAL", f"치명적 에러: {e}")
            
            finally:
                self._cleanup()
    
    def _main_loop_iteration(self) -> None:
        """메인 루프 단일 반복"""
        current_time = time.time()
        
        # 현재가 조회 (재시도 로직 적용)
        current_price = self._fetch_current_price_safe()
        if not current_price:
            print("❌ 현재가 조회 실패. 재시도 중...")
            time.sleep(5)
            return
        
        # 시뮬레이션 모드에서 현재가 업데이트
        if Config.is_test_trading():
            self.executor.update_market_price(current_price)
        
        # 현재 포지션 확인
        position_status = self.executor.check_position_status()
        
        if position_status['is_open']:
            # 포지션 있음: 빠른 모니터링
            self._handle_open_position(position_status, current_price)
            sleep_time = Config.POSITION_CHECK_INTERVAL
        else:
            # 포지션 없음: 트레이딩 결정
            self._handle_no_position(current_price, current_time)
            sleep_time = Config.get_schedule_interval("decision")
        
        # 대기
        time.sleep(sleep_time)
    
    @retry_on_market_data_error(max_retries=2)
    def _fetch_current_price_safe(self) -> Optional[float]:
        """안전한 현재가 조회 (재시도 포함)"""
        return self.market_fetcher.fetch_current_price()
    
    def _handle_open_position(self, position_status: Dict[str, Any], current_price: float) -> None:
        """오픈 포지션 모니터링"""
        self.position_check_count += 1
        
        side = position_status['side']
        amount = position_status['amount']
        unrealized_pnl = position_status.get('unrealized_pnl', 0)
        
        # 로그 출력 (매 12회마다, 즉 1분마다)
        if self.position_check_count % 12 == 0:
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] 📊 포지션: {side.upper()} {amount:.3f} BTC | "
                  f"가격: ${current_price:,.2f} | 손익: ${unrealized_pnl:+,.2f}")
        
        # 시뮬레이션 모드에서 SL/TP 트리거 확인
        if Config.is_test_trading():
            self._check_sl_tp_triggers(current_price)
    
    def _check_sl_tp_triggers(self, current_price: float) -> None:
        """SL/TP 트리거 확인 (시뮬레이션 전용)"""
        try:
            current_trade = self.recorder.get_latest_open_trade()
            if not current_trade:
                return
            
            sl_price = current_trade['sl_price']
            tp_price = current_trade['tp_price']
            
            trigger = self.executor.check_sl_tp_triggers(current_price, sl_price, tp_price)
            
            if trigger:
                print(f"\n🎯 {trigger.upper()} 트리거 발동! 가격: ${current_price:,.2f}")
                close_result = self.executor.close_position(reason=trigger)
                
                if close_result['success']:
                    self._handle_position_closure(current_trade['id'], close_result)
                    self.position_check_count = 0  # 카운터 리셋
                    
        except Exception as e:
            log_chain("sl_tp_check", "ERROR", f"SL/TP 체크 실패: {e}")
    
    def _handle_no_position(self, current_price: float, current_time: float) -> None:
        """포지션 없을 때 트레이딩 결정"""
        # 결정 간격 체크 (중복 방지)
        if current_time - self.last_decision_time < 50:  # 50초 이내 중복 방지
            return
        
        self.last_decision_time = current_time
        
        # 이전 포지션 정리 확인
        self._cleanup_previous_position()
        
        # 가용 잔액 조회
        if Config.is_real_trading():
            available_balance = self.market_fetcher.get_account_balance()
        else:
            available_balance = self.executor.get_account_balance()
        
        # 일일 손익 계산 (간단한 방법)
        daily_pnl = self._calculate_daily_pnl()
        
        print(f"\n🧠 가격 ${current_price:,.2f}에서 트레이딩 결정 중")
        print(f"💰 사용가능 잔액: ${available_balance:,.2f}")
        if daily_pnl != 0:
            print(f"📈 일일 손익: ${daily_pnl:+,.2f}")
        
        # Decision Chain을 통한 트레이딩 결정 (재시도 적용)
        decision_result = self._make_trading_decision_safe(
            current_price, available_balance, None, daily_pnl
        )
        
        if decision_result and decision_result["success"]:
            self._process_trading_decision(decision_result, current_price, available_balance)
        else:
            error_msg = decision_result.get('error', '알 수 없는 에러') if decision_result else 'Decision 실패'
            print(f"❌ 의사결정 실패: {error_msg}")
            log_chain("decision", "ERROR", f"의사결정 실패: {error_msg}")
    
    @retry_on_llm_error(max_retries=2)
    def _make_trading_decision_safe(self, current_price: float, available_balance: float,
                                   current_position: Optional[Dict[str, Any]], daily_pnl: float) -> Dict[str, Any]:
        """안전한 트레이딩 의사결정 (재시도 포함)"""
        return make_trading_decision(current_price, available_balance, current_position, daily_pnl)
    
    def _process_trading_decision(self, decision_result: Dict[str, Any], 
                                 current_price: float, available_balance: float) -> None:
        """트레이딩 결정 처리"""
        decision = decision_result["decision"]
        direction = decision["direction"]
        conviction = decision.get("conviction", 0)
        reasoning = decision["reasoning"]
        
        print(f"🎯 결정: {direction} (확신도: {conviction:.2f})")
        print(f"💭 이유: {reasoning[:150]}...")
        
        if direction == "NO_POSITION":
            print("⏸️  포지션 진입 안함. 다음 기회 대기 중...")
            return
        
        # 포지션 진입
        try:
            self._enter_position(decision, current_price)
        except Exception as e:
            print(f"❌ 포지션 진입 실패: {e}")
            log_chain("position_entry", "ERROR", f"포지션 진입 실패: {e}")
    
    def _enter_position(self, decision: Dict[str, Any], current_price: float) -> None:
        """포지션 진입 실행"""
        direction = decision["direction"]
        risk_params = decision["risk_parameters"]
        position_sizing = decision.get("position_sizing", {})
        
        # 포지션 사이징 정보
        investment_amount = position_sizing.get("investment_amount", Config.MIN_INVESTMENT_AMOUNT)
        leverage = position_sizing.get("leverage", 3)
        
        print(f"💰 투자금액: ${investment_amount:,.2f} | 레버리지: {leverage}x")
        
        # 실행기를 통한 포지션 진입
        trading_decision = {
            'direction': direction,
            'recommended_leverage': leverage,
            'stop_loss_percentage': risk_params['stop_loss_percentage'],
            'take_profit_percentage': risk_params['take_profit_percentage']
        }
        
        try:
            position_result = self.executor.open_position(
                trading_decision, investment_amount, current_price
            )
            
            # 거래 기록 저장
            self._save_trade_record(position_result, decision, position_sizing)
            
            # 결과 출력
            self.executor.print_position_opened(position_result)
            print(f"📝 거래 기록 데이터베이스 저장 완료")
            
        except Exception as e:
            print(f"❌ 포지션 실행 실패: {e}")
            raise
    
    def _save_trade_record(self, position_result: Dict[str, Any], 
                          decision: Dict[str, Any], position_sizing: Dict[str, Any]) -> None:
        """거래 기록 저장"""
        try:
            trade_data = {
                'action': position_result['action'],
                'entry_price': position_result['entry_price'],
                'amount': position_result['amount'],
                'leverage': position_result['leverage'],
                'sl_price': position_result['sl_price'],
                'tp_price': position_result['tp_price'],
                'sl_percentage': position_result['sl_percentage'],
                'tp_percentage': position_result['tp_percentage'],
                'position_size_percentage': position_sizing.get('position_fraction', 0.1),
                'investment_amount': position_sizing.get('investment_amount', 0)
            }
            
            trade_id = self.recorder.save_trade(trade_data)
            self.executor.set_current_trade_id(trade_id)
            
            # AI 분석 결과도 저장
            analysis_data = {
                'current_price': position_result['entry_price'],
                'direction': decision['direction'],
                'recommended_position_size': position_sizing.get('position_fraction', 0.1),
                'recommended_leverage': position_result['leverage'],
                'stop_loss_percentage': position_result['sl_percentage'],
                'take_profit_percentage': position_result['tp_percentage'],
                'reasoning': decision['reasoning']
            }
            
            analysis_id = self.recorder.save_ai_analysis(analysis_data, trade_id)
            print(f"📋 분석 ID: {analysis_id}, 거래 ID: {trade_id}")
            
        except Exception as e:
            log_chain("trade_record", "ERROR", f"거래 기록 저장 실패: {e}")
            print(f"⚠️  경고: 거래 기록 저장 실패: {e}")
    
    def _handle_position_closure(self, trade_id: int, close_result: Dict[str, Any]) -> None:
        """포지션 종료 처리"""
        try:
            # 데이터베이스 업데이트
            self.recorder.update_trade_status(
                trade_id,
                'CLOSED',
                exit_price=close_result.get('exit_price'),
                exit_timestamp=datetime.now().isoformat(),
                profit_loss=close_result.get('profit_loss'),
                profit_loss_percentage=close_result.get('profit_loss_percentage')
            )
            
            # 결과 출력
            self.executor.print_position_closed(close_result)
            
            # 성과 분석 갱신 트리거
            on_trade_completed()
            
            # 거래 요약 출력
            self.recorder.print_trade_summary(days=7)
            
        except Exception as e:
            log_chain("position_closure", "ERROR", f"포지션 종료 처리 실패: {e}")
    
    def _cleanup_previous_position(self) -> None:
        """이전 포지션 정리 확인"""
        try:
            current_trade = self.recorder.get_latest_open_trade()
            if current_trade:
                # 포지션은 없지만 DB에 OPEN 상태가 남아있는 경우
                current_price = self._fetch_current_price_safe()
                close_result = {
                    'success': True,
                    'exit_price': current_price,
                    'profit_loss': 0,
                    'profit_loss_percentage': 0
                }
                self._handle_position_closure(current_trade['id'], close_result)
                print("✅ 이전 포지션 정리 완료")
        except Exception as e:
            log_chain("cleanup", "WARNING", f"포지션 정리 경고: {e}")
    
    def _calculate_daily_pnl(self) -> float:
        """일일 손익 계산 (간단한 방법)"""
        try:
            summary = self.recorder.get_trade_summary(days=1)
            if summary:
                return summary['total_profit_loss']
            return 0.0
        except Exception:
            return 0.0
    
    def _periodic_cleanup(self) -> None:
        """주기적 정리 작업 (메모리 누수 방지)"""
        try:
            print("\n🧹 주기적 정리 작업 수행 중...")
            
            # 1. 가비지 컬렉션
            collected = gc.collect()
            if collected > 0:
                print(f"   🗑️  가비지 컬렉션: {collected}개 객체 정리")
            
            # 2. 만료된 캐시 정리
            try:
                cleaned = self.chain_db.cleanup_expired_cache()
                if cleaned > 0:
                    print(f"   📦 만료된 캐시: {cleaned}개 정리")
            except Exception as e:
                print(f"   ⚠️  캐시 정리 경고: {e}")
            
            # 3. LLM 캐시 상태 확인
            try:
                cache_stats = get_llm_cache_stats()
                print(f"   🧠 LLM 캐시: {cache_stats['cache_size']}/{cache_stats['max_cache_size']}")
                
                # 캐시가 가득 찬 경우 일부 정리
                if cache_stats['cache_size'] >= cache_stats['max_cache_size']:
                    print("   🔄 LLM 캐시 일부 정리...")
                    # 전체 정리는 하지 않고 자연스럽게 LRU로 관리되도록 함
            except Exception as e:
                print(f"   ⚠️  LLM 캐시 확인 경고: {e}")
            
            print("   ✅ 주기적 정리 완료")
            
        except Exception as e:
            print(f"   ❌ 정리 작업 에러: {e}")
            log_chain("cleanup", "ERROR", f"주기적 정리 실패: {e}")
    
    def _signal_handler(self, signum, frame) -> None:
        """시그널 핸들러 (Ctrl+C 등)"""
        print(f"\n🛑 시그널 {signum} 수신")
        self.is_running = False
    
    def _cleanup(self) -> None:
        """정리 작업"""
        print("\n🧹 정리 작업 수행 중...")
        
        try:
            # 스케줄러 중지
            print("🔄 백그라운드 스케줄러 중지 중...")
            stop_scheduler()
            
            # 시뮬레이션 모드에서 최종 요약
            if Config.is_test_trading():
                print("\n📊 최종 성과 요약:")
                self.executor.print_account_summary()
            
            # 최종 거래 요약
            print("\n📈 최근 거래 요약:")
            self.recorder.print_trade_summary(days=7)
            
            # 리소스 정리
            try:
                # LLM 캐시 정리 (선택적)
                cache_stats = get_llm_cache_stats()
                if cache_stats['cache_size'] > 5:  # 5개 이상일 때만 정리
                    print("🧠 LLM 캐시 정리 중...")
                    clear_llm_cache()
                
                # 데이터베이스 연결 정리
                print("🗄️  데이터베이스 연결 정리 중...")
                close_db_connections()
                
                # 최종 가비지 컬렉션
                collected = gc.collect()
                if collected > 0:
                    print(f"🗑️  최종 정리: {collected}개 객체 해제")
                
            except Exception as e:
                print(f"⚠️  리소스 정리 경고: {e}")
            
        except Exception as e:
            print(f"⚠️  정리 작업 경고: {e}")
        
        print("✅ 봇 종료 완료")


def main():
    """메인 함수"""
    print("🚀 AI 비트코인 트레이딩 봇 초기화 중...")
    
    try:
        bot = TradingBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n👋 정상 종료 완료")
    except Exception as e:
        print(f"\n💥 치명적 에러: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 최종 정리 (안전장치)
        try:
            close_db_connections()
            clear_llm_cache()
            gc.collect()
        except:
            pass


if __name__ == "__main__":
    main()