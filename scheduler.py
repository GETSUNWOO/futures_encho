"""
체인 실행 스케줄러
- APScheduler 기반 체인별 주기 관리
- 의존성 순서 고려한 실행
- 동적 스케줄 조정
- 에러 복구 및 재시도
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
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
    """체인 실행 스케줄러"""
    
    def __init__(self):
        """초기화"""
        self.scheduler = BackgroundScheduler(timezone='UTC')
        self.db = get_chain_db()
        self.is_running = False
        self.job_stats = {}
        self.lock = threading.Lock()
        
        # 체인 함수 맵핑
        self.chain_functions = {
            "news": run_news_analysis,
            "market_1h": run_1h_analysis,
            "market_4h": run_4h_analysis,
            "performance": run_performance_analysis
        }
        
        # 이벤트 리스너 등록
        self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        
        # 통계 초기화
        self._init_job_stats()
        
        log_chain("scheduler", "INFO", "Chain scheduler initialized")
    
    def start(self) -> None:
        """스케줄러 시작"""
        if self.is_running:
            log_chain("scheduler", "WARNING", "Scheduler already running")
            return
        
        try:
            # 체인별 스케줄 등록
            self._setup_chain_schedules()
            
            # 유지보수 작업 스케줄 등록
            self._setup_maintenance_schedules()
            
            # 스케줄러 시작
            self.scheduler.start()
            self.is_running = True
            
            log_chain("scheduler", "INFO", "Chain scheduler started successfully")
            self._print_schedule_summary()
            
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Failed to start scheduler: {e}")
            raise
    
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
            misfire_grace_time=300  # 5분 유예
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
            misfire_grace_time=600  # 10분 유예
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
        
        # 즉시 초기 실행 (30초 지연)
        self.scheduler.add_job(
            func=self._initial_chain_execution,
            trigger='date',
            run_date=datetime.now() + timedelta(seconds=30),
            id="initial_execution"
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
    
    def _run_chain_safe(self, chain_name: str, force_refresh: bool = False, **kwargs) -> None:
        """안전한 체인 실행 (에러 처리 포함)"""
        start_time = time.time()
        
        try:
            with self.lock:
                # 실행 전 통계 업데이트
                if chain_name not in self.job_stats:
                    self.job_stats[chain_name] = {"attempts": 0, "successes": 0, "failures": 0, "last_run": None, "last_duration": 0}
                
                self.job_stats[chain_name]["attempts"] += 1
                self.job_stats[chain_name]["last_run"] = datetime.now().isoformat()
            
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
                raise Exception(f"Chain execution failed: {result.get('reason', 'unknown')}")
            
            duration = time.time() - start_time
            
            with self.lock:
                self.job_stats[chain_name]["successes"] += 1
                self.job_stats[chain_name]["last_duration"] = duration
            
            log_chain("scheduler", "INFO", f"{chain_name} chain completed successfully in {duration:.2f}s")
            
        except Exception as e:
            duration = time.time() - start_time
            
            with self.lock:
                self.job_stats[chain_name]["failures"] += 1
                self.job_stats[chain_name]["last_duration"] = duration
            
            log_chain("scheduler", "ERROR", f"{chain_name} chain failed after {duration:.2f}s: {e}")
            
            # 재시도 로직 (간단한 방식)
            if "network" in str(e).lower() or "timeout" in str(e).lower():
                self._schedule_retry(chain_name, delay_minutes=5)
    
    def _initial_chain_execution(self) -> None:
        """초기 체인 실행 (의존성 순서 고려)"""
        try:
            log_chain("scheduler", "INFO", "Starting initial chain execution")
            
            # 1. 뉴스 체인 (독립적)
            self._run_chain_safe("news", force_refresh=True)
            time.sleep(2)
            
            # 2. 시장 분석 체인들 (병렬 가능)
            self._run_chain_safe("market_4h", force_refresh=True)
            time.sleep(1)
            self._run_chain_safe("market_1h", force_refresh=True)
            time.sleep(2)
            
            # 3. 성과 분석 (다른 체인들 완료 후)
            self._run_chain_safe("performance", force_refresh=True)
            
            log_chain("scheduler", "INFO", "Initial chain execution completed")
            
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Initial chain execution failed: {e}")
    
    def _schedule_retry(self, chain_name: str, delay_minutes: int = 5) -> None:
        """체인 재시도 스케줄링"""
        try:
            retry_time = datetime.now() + timedelta(minutes=delay_minutes)
            
            self.scheduler.add_job(
                func=self._run_chain_safe,
                args=[chain_name, True],  # force_refresh=True
                trigger='date',
                run_date=retry_time,
                id=f"{chain_name}_retry_{int(time.time())}",
                max_instances=1
            )
            
            log_chain("scheduler", "INFO", f"Scheduled {chain_name} retry in {delay_minutes} minutes")
            
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Failed to schedule retry for {chain_name}: {e}")
    
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
                
                # 체인별 성공률 계산
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
            else:
                # 성공적으로 완료된 경우는 개별 체인에서 로깅하므로 여기서는 제외
                pass
                
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
        print("\n" + "="*60)
        print("           📅 CHAIN SCHEDULER SUMMARY")
        print("="*60)
        
        for job in self.scheduler.get_jobs():
            if "chain" in job.id:
                chain_name = job.id.replace("_chain", "").replace("_", " ").title()
                next_run = job.next_run_time.strftime("%H:%M:%S") if job.next_run_time else "N/A"
                
                # 인터벌 정보 추출
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
                
                print(f"{chain_name:15} | Every {interval_str:8} | Next: {next_run}")
        
        print("="*60 + "\n")
    
    # 외부 인터페이스 메서드들
    
    def trigger_chain(self, chain_name: str, force_refresh: bool = True) -> bool:
        """체인 수동 실행 트리거"""
        try:
            if chain_name not in self.chain_functions:
                log_chain("scheduler", "ERROR", f"Unknown chain: {chain_name}")
                return False
            
            # 비동기 실행을 위해 스케줄러에 즉시 실행 작업 추가
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
        """체인별 상태 정보 반환"""
        with self.lock:
            status = {}
            for chain_name, stats in self.job_stats.items():
                # 다음 실행 시간 조회
                job = self.scheduler.get_job(f"{chain_name}_chain")
                next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
                
                status[chain_name] = {
                    **stats,
                    "next_run": next_run,
                    "success_rate": (stats["successes"] / stats["attempts"] * 100) if stats["attempts"] > 0 else 0
                }
            
            return {
                "scheduler_running": self.is_running,
                "total_jobs": len(self.scheduler.get_jobs()),
                "chain_status": status
            }
    
    def update_schedule_interval(self, chain_name: str, new_interval_seconds: int) -> bool:
        """체인 실행 간격 동적 변경"""
        try:
            job_id = f"{chain_name}_chain"
            job = self.scheduler.get_job(job_id)
            
            if not job:
                log_chain("scheduler", "ERROR", f"Job not found: {job_id}")
                return False
            
            # 기존 작업 제거
            self.scheduler.remove_job(job_id)
            
            # 새 간격으로 작업 재등록
            self.scheduler.add_job(
                func=self._run_chain_safe,
                args=[chain_name],
                trigger=IntervalTrigger(seconds=new_interval_seconds),
                id=job_id,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300
            )
            
            log_chain("scheduler", "INFO", f"Updated {chain_name} interval to {new_interval_seconds}s")
            return True
            
        except Exception as e:
            log_chain("scheduler", "ERROR", f"Failed to update schedule for {chain_name}: {e}")
            return False


# 전역 스케줄러 인스턴스
_scheduler_instance = None

def get_scheduler() -> ChainScheduler:
    """스케줄러 싱글톤 인스턴스 반환"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = ChainScheduler()
    return _scheduler_instance


# 편의 함수들
def start_scheduler() -> None:
    """스케줄러 시작"""
    scheduler = get_scheduler()
    scheduler.start()


def stop_scheduler() -> None:
    """스케줄러 중지"""
    scheduler = get_scheduler()
    scheduler.stop()


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
    """스케줄러 상태 출력"""
    status = get_scheduler_status()
    
    print(f"\n📅 Scheduler Status: {'🟢 Running' if status['scheduler_running'] else '🔴 Stopped'}")
    print(f"Total Jobs: {status['total_jobs']}")
    
    print(f"\n📊 Chain Performance:")
    for chain_name, chain_status in status['chain_status'].items():
        success_rate = chain_status['success_rate']
        attempts = chain_status['attempts']
        last_run = chain_status['last_run']
        next_run = chain_status['next_run']
        
        status_icon = "✅" if success_rate >= 90 else "⚠️" if success_rate >= 70 else "❌"
        
        print(f"  {status_icon} {chain_name.title():12} | "
              f"Success: {success_rate:5.1f}% ({attempts:3d} attempts) | "
              f"Next: {next_run[-8:] if next_run else 'N/A':8}")


if __name__ == "__main__":
    # 스케줄러 테스트 실행
    try:
        print("Starting Chain Scheduler...")
        start_scheduler()
        
        # 상태 출력
        import time
        time.sleep(2)
        print_scheduler_status()
        
        print("\nScheduler running. Press Ctrl+C to stop.")
        while True:
            time.sleep(60)
            
    except KeyboardInterrupt:
        print("\nStopping scheduler...")
        stop_scheduler()
        print("Scheduler stopped.")