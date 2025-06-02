"""
체인 실행 스케줄러 - 초기화 로직 개선
- 봇 시작시 모든 체인 즉시 실행
- 병렬 처리로 초기화 시간 단축
- 의존성 순서 고려한 실행
"""
import time
import threading
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from config import Config
from utils.db import get_chain_db, log_chain, cleanup_cache
from chains.news_chain import run_news_analysis
from chains.market_chain_1h import run_1h_analysis
from chains.market_chain_4h import run_4h_analysis
from chains.performance_chain import run_performance_analysis, trigger_performance_update_on_trade_completion


class ChainScheduler:
    """체인 실행 스케줄러 - 초기화 개선"""
    
    def __init__(self):
        """초기화"""
        self.scheduler = BackgroundScheduler(timezone='UTC')
        self.db = get_chain_db()
        self.is_running = False
        self.job_stats = {}
        self.lock = threading.Lock()
        
        # 초기화 상태 추적
        self.initialization_complete = False
        self.initialization_results = {}
        
        # 체인 함수 맵핑
        self.chain_functions = {
            "news": run_news_analysis,
            "market_1h": run_1h_analysis,
            "market_4h": run_4h_analysis,
            "performance": run_performance_analysis
        }
        
        # 체인 실행 우선순위 (의존성 순서)
        self.chain_priority = {
            "news": 1,        # 독립적, 가장 먼저
            "market_4h": 2,   # 독립적, 구조 분석
            "market_1h": 3,   # 독립적, 단기 분석
            "performance": 4  # 다른 체인 완료 후
        }
        
        # 이벤트 리스너 등록
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        
        # 통계 초기화
        self._init_job_stats()
        
        log_chain("scheduler", "INFO", "Chain scheduler initialized")
    
    def start(self) -> None:
        """스케줄러 시작 - 강력한 초기화 정책"""
        if self.is_running:
            log_chain("scheduler", "WARNING", "Scheduler already running")
            return
        
        try:
            print("🔄 체인 스케줄러 초기화 중...")
            print("🛡️ 강력한 정책: 모든 체인이 성공해야 거래 시작")
            
            # 1. 즉시 모든 체인 실행 (병렬) - 강력한 정책
            print("⚡ 필수 체인 데이터 수집 중...")
            self._run_initial_chains()
            
            # 2. 정기 스케줄 등록
            self._setup_chain_schedules()
            
            # 3. 유지보수 작업 스케줄 등록
            self._setup_maintenance_schedules()
            
            # 4. 스케줄러 시작
            self.scheduler.start()
            self.is_running = True
            
            log_chain("scheduler", "INFO", "Chain scheduler started successfully")
            self._print_schedule_summary()
            
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Failed to start scheduler: {e}")
            raise
    
    def _run_initial_chains(self) -> None:
        """초기 체인 실행 - 체인별 개별 재시도 방식"""
        print("🚀 필수 체인 초기화 시작 (체인별 개별 재시도)...")
        start_time = time.time()
        
        # 필수 체인 목록과 실행 순서
        chain_sequence = [
            {"name": "news", "description": "뉴스 분석"},
            {"name": "market_4h", "description": "4시간 시장 분석"},  
            {"name": "market_1h", "description": "1시간 시장 분석"},
            {"name": "performance", "description": "성과 분석"}
        ]
        
        failed_chains = []
        
        try:
            # 각 체인을 순차적으로 실행 (개별 재시도)
            for chain_info in chain_sequence:
                chain_name = chain_info["name"]
                description = chain_info["description"]
                
                print(f"   📊 {description} 초기화 중...")
                
                success = self._initialize_single_chain(chain_name)
                
                if success:
                    print(f"      ✅ {chain_name}: 성공")
                else:
                    print(f"      ❌ {chain_name}: 최종 실패")
                    failed_chains.append(chain_name)
            
            # 모든 체인 성공 검증
            if failed_chains:
                raise Exception(f"필수 체인 실패: {', '.join(failed_chains)}")
            
            # === 성공: 모든 체인 완료 ===
            self.initialization_complete = True
            total_time = time.time() - start_time
            
            print(f"✅ 모든 필수 체인 초기화 성공! ({total_time:.1f}초)")
            print(f"   성공: 4/4 체인 (뉴스, 1H분석, 4H분석, 성과분석)")
            
            log_chain("scheduler", "INFO", f"All required chains initialized successfully in {total_time:.1f}s")
            
        except Exception as e:
            print(f"💥 필수 체인 초기화 실패: {e}")
            log_chain("scheduler", "CRITICAL", f"Required chain initialization failed: {e}")
            raise Exception("필수 체인 초기화 실패 - 안전을 위해 시스템 종료")
    
    def _initialize_single_chain(self, chain_name: str, max_retries: int = 3) -> bool:
        """
        단일 체인 초기화 (개별 재시도)
        
        Args:
            chain_name: 체인 이름
            max_retries: 최대 재시도 횟수
            
        Returns:
            성공 여부
        """
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # 재시도 시 대기 시간 (지수 백오프)
                    wait_time = min(2 ** attempt, 10)  # 2초, 4초, 10초
                    print(f"      🔄 {chain_name} 재시도 {attempt + 1}/{max_retries} ({wait_time}초 후)")
                    time.sleep(wait_time)
                
                # 체인 실행
                result = self._run_chain_safe(chain_name, force_refresh=True)
                
                if result.get("success", False):
                    self.initialization_results[chain_name] = result
                    return True
                else:
                    error_msg = result.get("error", "unknown")
                    print(f"      ⚠️  {chain_name} 시도 {attempt + 1} 실패: {error_msg}")
                    
                    # 마지막 시도가 아니면 계속
                    if attempt < max_retries - 1:
                        continue
                    else:
                        # 마지막 시도 실패
                        self.initialization_results[chain_name] = result
                        return False
                        
            except Exception as e:
                print(f"      💥 {chain_name} 시도 {attempt + 1} 예외: {str(e)[:50]}...")
                
                if attempt < max_retries - 1:
                    continue
                else:
                    # 마지막 시도 실패
                    self.initialization_results[chain_name] = {"success": False, "error": str(e)}
                    return False
        
        return False
    
    def _run_chains_parallel(self, chain_names: List[str], max_workers: int = 3) -> None:
        """체인들을 병렬로 실행 - 엄격한 성공 요구"""
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 모든 체인 제출
            future_to_chain = {
                executor.submit(self._run_chain_safe, chain_name, True): chain_name 
                for chain_name in chain_names
            }
            
            # 결과 수집 - 타임아웃 연장
            timeout_seconds = 300  # 5분 타임아웃
            
            try:
                for future in concurrent.futures.as_completed(future_to_chain, timeout=timeout_seconds):
                    chain_name = future_to_chain[future]
                    
                    try:
                        result = future.result()
                        self.initialization_results[chain_name] = result
                        
                        success = result.get("success", False)
                        source = result.get("source", "unknown")
                        
                        if success:
                            print(f"      ✅ {chain_name}: {source}")
                        else:
                            error_msg = result.get("error", "unknown error")
                            print(f"      ❌ {chain_name}: {error_msg}")
                            
                    except Exception as e:
                        print(f"      💥 {chain_name}: 실행 중 예외 - {str(e)[:50]}...")
                        self.initialization_results[chain_name] = {"success": False, "error": str(e)}
                        
            except concurrent.futures.TimeoutError:
                print(f"      ⏰ 타임아웃 ({timeout_seconds}초) - 일부 체인이 완료되지 않음")
                
                # 완료되지 않은 체인들 처리
                for future, chain_name in future_to_chain.items():
                    if not future.done():
                        future.cancel()
                        self.initialization_results[chain_name] = {
                            "success": False, 
                            "error": f"Timeout after {timeout_seconds} seconds"
                        }
                        print(f"      ⏰ {chain_name}: 타임아웃으로 취소됨")
    
    def _setup_chain_schedules(self) -> None:
        """체인별 스케줄 설정"""
        # 뉴스 체인 - 2시간마다
        self.scheduler.add_job(
            func=self._run_chain_safe,
            args=["news"],
            trigger=IntervalTrigger(seconds=Config.get_schedule_interval("news")),
            id="news_chain",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        
        # 1시간 시장 분석 - 1시간마다
        self.scheduler.add_job(
            func=self._run_chain_safe,
            args=["market_1h"],
            trigger=IntervalTrigger(seconds=Config.get_schedule_interval("market_1h")),
            id="market_1h_chain",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
        
        # 4시간 시장 분석 - 4시간마다
        self.scheduler.add_job(
            func=self._run_chain_safe,
            args=["market_4h"],
            trigger=IntervalTrigger(seconds=Config.get_schedule_interval("market_4h")),
            id="market_4h_chain",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=600
        )
        
        # 성과 분석 - 1시간마다
        self.scheduler.add_job(
            func=self._run_chain_safe,
            args=["performance"],
            trigger=IntervalTrigger(seconds=Config.get_schedule_interval("performance")),
            id="performance_chain",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300
        )
    
    def _setup_maintenance_schedules(self) -> None:
        """유지보수 작업 스케줄 설정"""
        # 캐시 정리 - 매일 자정
        self.scheduler.add_job(
            func=self._cleanup_expired_cache,
            trigger=CronTrigger(hour=0, minute=0),
            id="cache_cleanup",
            max_instances=1
        )
        
        # 통계 리셋 - 매주 월요일 자정
        self.scheduler.add_job(
            func=self._reset_job_stats,
            trigger=CronTrigger(day_of_week=0, hour=0, minute=0),
            id="stats_reset",
            max_instances=1
        )
        
        # 스케줄러 상태 로깅 - 매시간
        self.scheduler.add_job(
            func=self._log_scheduler_status,
            trigger=IntervalTrigger(hours=1),
            id="status_logging",
            max_instances=1
        )
    
    def _run_chain_safe(self, chain_name: str, force_refresh: bool = False, **kwargs) -> Dict[str, Any]:
        """안전한 체인 실행 (에러 처리 포함) - 통계 수정"""
        start_time = time.time()
        
        try:
            with self.lock:
                # 통계 초기화 (초기화 중에도 실행)
                if chain_name not in self.job_stats:
                    self.job_stats[chain_name] = {
                        "attempts": 0, "successes": 0, "failures": 0, 
                        "last_run": None, "last_duration": 0
                    }
                
                # 시도 횟수 증가 (초기화 중에도 카운트)
                self.job_stats[chain_name]["attempts"] += 1
                self.job_stats[chain_name]["last_run"] = datetime.now().isoformat()
            
            # 초기화 중에는 상세 로그 제한
            if not self.initialization_complete:
                # 초기화 중에는 간단한 로그만
                pass
            else:
                log_chain("scheduler", "INFO", f"Executing {chain_name} chain")
            
            # 체인 함수 실행
            chain_func = self.chain_functions.get(chain_name)
            if not chain_func:
                raise ValueError(f"Unknown chain: {chain_name}")
            
            # 체인별 특별 인자 처리
            if chain_name == "performance":
                result = chain_func(force_refresh=force_refresh, **kwargs)
            else:
                result = chain_func(force_refresh=force_refresh)
            
            # 결과 검증
            if not result.get("success", False):
                error_reason = result.get("reason", result.get("error", "unknown"))
                raise Exception(f"Chain execution failed: {error_reason}")
            
            duration = time.time() - start_time
            
            # 성공 통계 업데이트 (초기화 중에도 실행)
            with self.lock:
                self.job_stats[chain_name]["successes"] += 1
                self.job_stats[chain_name]["last_duration"] = duration
            
            if not self.initialization_complete:
                # 초기화 중에는 간단한 로그만
                pass
            else:
                log_chain("scheduler", "INFO", f"{chain_name} chain completed successfully in {duration:.2f}s")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # 실패 통계 업데이트 (초기화 중에도 실행)
            with self.lock:
                self.job_stats[chain_name]["failures"] += 1
                self.job_stats[chain_name]["last_duration"] = duration
            
            if not self.initialization_complete:
                # 초기화 중에는 간단한 로그만
                pass
            else:
                log_chain("scheduler", "ERROR", f"{chain_name} chain failed after {duration:.2f}s: {e}")
                
                # 초기화 완료 후에만 재시도 스케줄링
                if ("network" in str(e).lower() or "timeout" in str(e).lower()):
                    self._schedule_retry(chain_name, delay_minutes=5)
            
            return {"success": False, "error": str(e), "source": "error"}
    
    def _schedule_retry(self, chain_name: str, delay_minutes: int = 5) -> None:
        """체인 재시도 스케줄링"""
        try:
            retry_time = datetime.now() + timedelta(minutes=delay_minutes)
            
            self.scheduler.add_job(
                func=self._run_chain_safe,
                args=[chain_name, True],
                trigger='date',
                run_date=retry_time,
                id=f"{chain_name}_retry_{int(time.time())}",
                max_instances=1
            )
            
            log_chain("scheduler", "INFO", f"Scheduled {chain_name} retry in {delay_minutes} minutes")
            
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Failed to schedule retry for {chain_name}: {e}")
    
    def wait_for_initialization(self, timeout: int = 600) -> bool:
        """
        초기화 완료까지 대기 - 강력한 정책
        
        Args:
            timeout: 최대 대기 시간 (초)
            
        Returns:
            초기화 성공 여부 (모든 체인 성공시에만 True)
        """
        start_time = time.time()
        
        while not self.initialization_complete:
            if time.time() - start_time > timeout:
                log_chain("scheduler", "CRITICAL", f"Initialization timeout after {timeout}s")
                return False
            
            time.sleep(1)
        
        # 모든 체인이 성공했는지 엄격하게 확인
        required_chains = ["news", "market_1h", "market_4h", "performance"]
        
        for chain_name in required_chains:
            result = self.initialization_results.get(chain_name, {})
            if not result.get("success", False):
                log_chain("scheduler", "ERROR", f"Required chain {chain_name} failed: {result.get('error', 'unknown')}")
                return False
        
        log_chain("scheduler", "INFO", "All required chains initialized successfully")
        return True
    
    def get_initialization_status(self) -> Dict[str, Any]:
        """초기화 상태 반환"""
        return {
            "complete": self.initialization_complete,
            "results": self.initialization_results.copy(),
            "success_count": sum(1 for r in self.initialization_results.values() if r.get("success", False)),
            "total_count": len(self.initialization_results)
        }
    
    # 기존 메서드들 (변경 없음)
    def stop(self) -> None:
        """스케줄러 중지"""
        if not self.is_running:
            return
        
        try:
            self.scheduler.shutdown(wait=True)
            self.is_running = False
            log_chain("scheduler", "INFO", "Chain scheduler stopped")
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Error stopping scheduler: {e}")
    
    def _cleanup_expired_cache(self) -> None:
        """만료된 캐시 정리"""
        try:
            deleted_count = cleanup_cache()
            log_chain("scheduler", "INFO", f"Cache cleanup completed: {deleted_count} expired records removed")
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Cache cleanup failed: {e}")
    
    def _reset_job_stats(self) -> None:
        """작업 통계 리셋"""
        try:
            with self.lock:
                for chain_name in self.job_stats:
                    self.job_stats[chain_name].update({
                        "attempts": 0,
                        "successes": 0,
                        "failures": 0
                    })
            log_chain("scheduler", "INFO", "Job statistics reset")
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Stats reset failed: {e}")
    
    def _log_scheduler_status(self) -> None:
        """스케줄러 상태 로깅"""
        try:
            with self.lock:
                total_jobs = len(self.scheduler.get_jobs())
                running_jobs = len([job for job in self.scheduler.get_jobs() if job.next_run_time])
                
                status_summary = []
                for chain_name, stats in self.job_stats.items():
                    attempts = stats["attempts"]
                    successes = stats["successes"]
                    success_rate = (successes / attempts * 100) if attempts > 0 else 0
                    status_summary.append(f"{chain_name}: {success_rate:.1f}% ({successes}/{attempts})")
                
                log_chain("scheduler", "INFO", 
                         f"Scheduler status - Jobs: {running_jobs}/{total_jobs}, "
                         f"Chain success rates: {', '.join(status_summary)}")
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Status logging failed: {e}")
    
    def _job_listener(self, event) -> None:
        """작업 이벤트 리스너"""
        try:
            job_id = event.job_id
            
            if event.exception:
                log_chain("scheduler", "WARNING", f"Job {job_id} failed: {event.exception}")
                
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Job listener error: {e}")
    
    def _init_job_stats(self) -> None:
        """작업 통계 초기화"""
        for chain_name in self.chain_functions.keys():
            self.job_stats[chain_name] = {
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "last_run": None,
                "last_duration": 0
            }
    
    def _print_schedule_summary(self) -> None:
        """스케줄 요약 출력"""
        init_status = self.get_initialization_status()
        
        print("\n" + "="*60)
        print("           📅 CHAIN SCHEDULER SUMMARY")
        print("="*60)
        print(f"초기화: {init_status['success_count']}/{init_status['total_count']} 체인 성공")
        
        for job in self.scheduler.get_jobs():
            if "chain" in job.id:
                chain_name = job.id.replace("_chain", "").replace("_", " ").title()
                
                # 다음 실행 시간 처리 개선
                if job.next_run_time:
                    try:
                        # UTC에서 로컬 시간으로 변환
                        next_run_local = job.next_run_time.replace(tzinfo=None)
                        next_run_str = next_run_local.strftime("%H:%M:%S")
                    except:
                        next_run_str = "N/A"
                else:
                    next_run_str = "N/A"
                
                if hasattr(job.trigger, 'interval'):
                    interval = job.trigger.interval
                    if interval.total_seconds() >= 3600:
                        interval_str = f"{int(interval.total_seconds()/3600)}h"
                    elif interval.total_seconds() >= 60:
                        interval_str = f"{int(interval.total_seconds()/60)}m"
                    else:
                        interval_str = f"{int(interval.total_seconds())}s"
                else:
                    interval_str = "Custom"
                
                print(f"{chain_name:15} | Every {interval_str:8} | Next: {next_run_str}")
        
        print("="*60 + "\n")
    
    # 외부 인터페이스 메서드들 (기존과 동일)
    def trigger_chain(self, chain_name: str, force_refresh: bool = True) -> bool:
        """체인 수동 실행 트리거"""
        try:
            if chain_name not in self.chain_functions:
                log_chain("scheduler", "ERROR", f"Unknown chain: {chain_name}")
                return False
            
            self.scheduler.add_job(
                func=self._run_chain_safe,
                args=[chain_name, force_refresh],
                trigger='date',
                run_date=datetime.now() + timedelta(seconds=1),
                id=f"{chain_name}_manual_{int(time.time())}",
                max_instances=1
            )
            
            log_chain("scheduler", "INFO", f"Manual trigger scheduled for {chain_name}")
            return True
            
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Failed to trigger {chain_name}: {e}")
            return False
    
    def trigger_performance_on_trade_completion(self) -> bool:
        """트레이드 완료시 성과 분석 트리거"""
        try:
            return self.trigger_chain("performance", force_refresh=True)
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Failed to trigger performance update: {e}")
            return False
    
    def get_chain_status(self) -> Dict[str, Any]:
        """체인별 상태 정보 반환 - 시간 표시 수정"""
        with self.lock:
            status = {}
            for chain_name, stats in self.job_stats.items():
                job = self.scheduler.get_job(f"{chain_name}_chain")
                
                # 다음 실행 시간 처리 개선
                if job and job.next_run_time:
                    try:
                        # UTC에서 로컬 시간으로 변환
                        next_run_local = job.next_run_time.replace(tzinfo=None)
                        next_run_str = next_run_local.strftime("%H:%M:%S")
                    except:
                        next_run_str = "N/A"
                else:
                    next_run_str = "N/A"
                
                status[chain_name] = {
                    **stats,
                    "next_run": next_run_str,  # 시간만 표시
                    "success_rate": (stats["successes"] / stats["attempts"] * 100) if stats["attempts"] > 0 else 0
                }
            
            return {
                "scheduler_running": self.is_running,
                "initialization_complete": self.initialization_complete,
                "total_jobs": len(self.scheduler.get_jobs()),
                "chain_status": status
            }


# 전역 스케줄러 인스턴스
_scheduler_instance = None

def get_scheduler() -> ChainScheduler:
    """스케줄러 싱글톤 인스턴스 반환"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ChainScheduler()
    return _scheduler_instance


# 편의 함수들
def start_scheduler(wait_for_init: bool = True, timeout: int = 180) -> bool:
    """
    스케줄러 시작 - 깔끔한 출력
    
    Args:
        wait_for_init: 초기화 완료까지 대기 여부
        timeout: 최대 대기 시간 (초)
        
    Returns:
        초기화 성공 여부
    """
    scheduler = get_scheduler()
    scheduler.start()
    
    if wait_for_init:
        return scheduler.wait_for_initialization(timeout)
    
    return True


def stop_scheduler() -> None:
    """스케줄러 중지"""
    scheduler = get_scheduler()
    scheduler.stop()


def wait_for_chains_ready(timeout: int = 180) -> bool:
    """체인 초기화 완료까지 대기"""
    scheduler = get_scheduler()
    return scheduler.wait_for_initialization(timeout)


def get_initialization_status() -> Dict[str, Any]:
    """초기화 상태 조회"""
    scheduler = get_scheduler()
    return scheduler.get_initialization_status()


def trigger_chain_manual(chain_name: str) -> bool:
    """체인 수동 실행"""
    scheduler = get_scheduler()
    return scheduler.trigger_chain(chain_name, force_refresh=True)


def on_trade_completed() -> bool:
    """트레이드 완료시 호출"""
    scheduler = get_scheduler()
    return scheduler.trigger_performance_on_trade_completion()


def get_scheduler_status() -> Dict[str, Any]:
    """스케줄러 상태 조회"""
    scheduler = get_scheduler()
    return scheduler.get_chain_status()


def print_scheduler_status() -> None:
    """스케줄러 상태 출력 - 깔끔하게 정리"""
    status = get_scheduler_status()
    init_status = get_initialization_status()
    
    init_icon = "✅" if init_status["complete"] else "🔄"
    scheduler_icon = "🟢" if status['scheduler_running'] else "🔴"
    
    print(f"\n📅 시스템 상태:")
    print(f"   {scheduler_icon} 스케줄러: {'실행 중' if status['scheduler_running'] else '중지됨'}")
    print(f"   {init_icon} 초기화: {init_status['success_count']}/{init_status['total_count']} 체인 성공")
    print(f"   🔧 총 작업: {status['total_jobs']}개")
    
    print(f"\n📊 체인 성과:")
    for chain_name, chain_status in status['chain_status'].items():
        success_rate = chain_status['success_rate']
        attempts = chain_status['attempts']
        next_run = chain_status['next_run']
        
        # 성공률에 따른 아이콘
        if attempts == 0:
            status_icon = "⚪"  # 아직 실행 안됨
        elif success_rate >= 90:
            status_icon = "✅"
        elif success_rate >= 70:
            status_icon = "⚠️"
        else:
            status_icon = "❌"
        
        # 체인 이름 정리
        display_name = chain_name.replace('_', ' ').title()
        
        print(f"   {status_icon} {display_name:12} | "
              f"성공률: {success_rate:5.1f}% ({attempts:2d}회) | "
              f"다음: {next_run}")


if __name__ == "__main__":
    # 스케줄러 테스트 실행
    try:
        print("Starting Chain Scheduler...")
        success = start_scheduler(wait_for_init=True, timeout=180)
        
        if success:
            print("✅ All chains initialized successfully!")
        else:
            print("⚠️ Some chains failed to initialize, but continuing...")
        
        print_scheduler_status()
        
        print("\nScheduler running. Press Ctrl+C to stop.")
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\nStopping scheduler...")
        stop_scheduler()
        print("Scheduler stopped.")