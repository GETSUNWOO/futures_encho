"""
에러 재시도 유틸리티
- 네트워크 에러, API 에러 등에 대한 재시도 로직
- 지수 백오프로 안정성 확보
"""
import time
import random
from typing import Callable, Any, List, Type, Union
from functools import wraps


class RetryableError(Exception):
    """재시도 가능한 에러 기본 클래스"""
    pass


class NetworkError(RetryableError):
    """네트워크 관련 에러"""
    pass


class APIError(RetryableError):
    """API 관련 에러"""
    pass


class TemporaryError(RetryableError):
    """일시적 에러"""
    pass


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_multiplier: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Union[Type[Exception], List[Type[Exception]]] = None
):
    """
    지수 백오프를 사용한 재시도 데코레이터
    
    Args:
        max_retries: 최대 재시도 횟수
        base_delay: 기본 지연 시간 (초)
        max_delay: 최대 지연 시간 (초)
        backoff_multiplier: 백오프 배수
        jitter: 랜덤 지터 추가 여부
        retryable_exceptions: 재시도할 예외 타입들
    """
    if retryable_exceptions is None:
        retryable_exceptions = [
            ConnectionError, TimeoutError, OSError,
            # HTTP 관련 에러들
            Exception  # 일시적으로 모든 Exception 포함
        ]
    
    if not isinstance(retryable_exceptions, list):
        retryable_exceptions = [retryable_exceptions]
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if attempt > 0:
                        print(f"✅ {func.__name__} succeeded on attempt {attempt + 1}")
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    # 재시도 가능한 에러인지 확인
                    if not any(isinstance(e, exc_type) for exc_type in retryable_exceptions):
                        print(f"❌ {func.__name__} failed with non-retryable error: {e}")
                        raise
                    
                    # 마지막 시도였다면 예외 발생
                    if attempt == max_retries:
                        print(f"❌ {func.__name__} failed after {max_retries + 1} attempts: {e}")
                        raise
                    
                    # 지연 시간 계산
                    delay = min(base_delay * (backoff_multiplier ** attempt), max_delay)
                    
                    # 지터 추가
                    if jitter:
                        delay = delay * (0.5 + random.random() * 0.5)
                    
                    print(f"⚠️ {func.__name__} attempt {attempt + 1} failed: {e}")
                    print(f"🔄 Retrying in {delay:.1f} seconds...")
                    time.sleep(delay)
            
            # 이 지점에 도달할 일은 없지만 안전을 위해
            raise last_exception
        
        return wrapper
    return decorator


def simple_retry(max_retries: int = 2, delay: float = 1.0):
    """
    간단한 재시도 데코레이터 (빠른 복구용)
    
    Args:
        max_retries: 최대 재시도 횟수
        delay: 고정 지연 시간
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries:
                        raise
                    print(f"⚠️ {func.__name__} retry {attempt + 1}/{max_retries}: {e}")
                    time.sleep(delay)
            return None
        return wrapper
    return decorator


class RetryHandler:
    """재시도 핸들러 클래스 (더 세밀한 제어용)"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.attempt_count = 0
        self.last_error = None
    
    def reset(self):
        """재시도 상태 초기화"""
        self.attempt_count = 0
        self.last_error = None
    
    def should_retry(self, error: Exception) -> bool:
        """재시도 여부 판단"""
        if self.attempt_count >= self.max_retries:
            return False
        
        # 특정 에러 타입들은 재시도하지 않음
        non_retryable_errors = [
            ValueError, TypeError, KeyError, AttributeError
        ]
        
        if any(isinstance(error, err_type) for err_type in non_retryable_errors):
            return False
        
        return True
    
    def get_delay(self) -> float:
        """다음 재시도까지의 지연 시간 계산"""
        delay = self.base_delay * (2 ** self.attempt_count)
        return min(delay, 30.0)  # 최대 30초
    
    def record_attempt(self, error: Exception):
        """재시도 시도 기록"""
        self.attempt_count += 1
        self.last_error = error
    
    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """함수를 재시도와 함께 실행"""
        self.reset()
        
        while True:
            try:
                result = func(*args, **kwargs)
                if self.attempt_count > 0:
                    print(f"✅ Function succeeded after {self.attempt_count} retries")
                return result
                
            except Exception as e:
                if not self.should_retry(e):
                    raise
                
                self.record_attempt(e)
                delay = self.get_delay()
                
                print(f"🔄 Retry {self.attempt_count}/{self.max_retries} after {delay:.1f}s: {e}")
                time.sleep(delay)


# 편의 함수들
def safe_api_call(func: Callable, *args, **kwargs) -> Any:
    """API 호출을 안전하게 실행 (재시도 포함)"""
    retry_handler = RetryHandler(max_retries=3, base_delay=2.0)
    return retry_handler.execute_with_retry(func, *args, **kwargs)


def safe_network_call(func: Callable, *args, **kwargs) -> Any:
    """네트워크 호출을 안전하게 실행 (재시도 포함)"""
    @retry_with_backoff(
        max_retries=2,
        base_delay=1.0,
        retryable_exceptions=[ConnectionError, TimeoutError, OSError]
    )
    def wrapped_func():
        return func(*args, **kwargs)
    
    return wrapped_func()


# 특화된 데코레이터들
def retry_on_llm_error(max_retries: int = 2):
    """LLM API 에러시 재시도"""
    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=2.0,
        max_delay=10.0,
        retryable_exceptions=[
            ConnectionError, TimeoutError, OSError,
            # OpenAI, Anthropic 등의 특정 에러들은 여기에 추가
        ]
    )


def retry_on_market_data_error(max_retries: int = 2):
    """시장 데이터 수집 에러시 재시도"""
    return retry_with_backoff(
        max_retries=max_retries,
        base_delay=1.0,
        max_delay=5.0,
        retryable_exceptions=[ConnectionError, TimeoutError]
    )


def retry_on_db_error(max_retries: int = 1):
    """데이터베이스 에러시 재시도"""
    return simple_retry(max_retries=max_retries, delay=0.5)