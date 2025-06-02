"""
LLM Factory 모듈 - 인스턴스 캐싱 추가
- 동일한 설정의 LLM 재사용으로 메모리 절약
- 캐시 크기 제한으로 메모리 누수 방지
"""
import os
import threading
import hashlib
from typing import Dict, Any, Optional
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI


class LLMFactory:
    """AI 모델 생성 및 관리 팩토리 클래스 - 캐싱 기능 추가"""
    
    # 지원되는 모델 정의
    SUPPORTED_MODELS = {
        # OpenAI 모델들
        "gpt-4o": {"provider": "openai", "model_name": "gpt-4o"},
        "gpt-4o-mini": {"provider": "openai", "model_name": "gpt-4o-mini"},
        "gpt-4-turbo": {"provider": "openai", "model_name": "gpt-4-turbo"},
        
        # Anthropic 모델들
        "claude-3-5-sonnet": {"provider": "anthropic", "model_name": "claude-3-5-sonnet-20241022"},
        "claude-3-5-haiku": {"provider": "anthropic", "model_name": "claude-3-5-haiku-20241022"},
        "claude-3-opus": {"provider": "anthropic", "model_name": "claude-3-opus-20240229"},
        
        # Google 모델들
        "gemini-2.0-flash": {"provider": "google", "model_name": "gemini-2.0-flash-exp"},
        "gemini-1.5-pro": {"provider": "google", "model_name": "gemini-1.5-pro"},
        "gemini-1.5-flash": {"provider": "google", "model_name": "gemini-1.5-flash"}
    }
    
    # 기본 설정값
    DEFAULT_SETTINGS = {
        "temperature": 0.1,
        "max_tokens": 2000,
        "timeout": 30
    }
    
    # LLM 인스턴스 캐시
    _llm_cache: Dict[str, Any] = {}
    _cache_lock = threading.Lock()
    _max_cache_size = 10  # 최대 캐시 크기
    
    @classmethod
    def _generate_cache_key(cls, model_key: str, **kwargs) -> str:
        """캐시 키 생성"""
        # 설정값들을 정렬된 문자열로 변환
        settings_str = "&".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        cache_input = f"{model_key}|{settings_str}"
        return hashlib.md5(cache_input.encode()).hexdigest()[:12]
    
    @classmethod
    def _manage_cache_size(cls):
        """캐시 크기 관리 (LRU 방식)"""
        if len(cls._llm_cache) > cls._max_cache_size:
            # 가장 오래된 항목 제거 (간단한 구현)
            oldest_key = next(iter(cls._llm_cache))
            del cls._llm_cache[oldest_key]
            print(f"LLM cache evicted: {oldest_key}")
    
    @classmethod
    def create_llm(cls, model_key: str, **kwargs) -> Any:
        """
        지정된 모델키로 LLM 인스턴스 생성 (캐싱 적용)
        
        Args:
            model_key: 모델 식별키 (예: "gpt-4o", "claude-3-5-sonnet")
            **kwargs: 추가 모델 설정 (temperature, max_tokens 등)
            
        Returns:
            LangChain LLM 인스턴스
            
        Raises:
            ValueError: 지원되지 않는 모델이거나 API 키가 없는 경우
        """
        if model_key not in cls.SUPPORTED_MODELS:
            raise ValueError(f"Unsupported model: {model_key}. "
                           f"Supported models: {list(cls.SUPPORTED_MODELS.keys())}")
        
        # 기본 설정과 사용자 설정 병합
        settings = {**cls.DEFAULT_SETTINGS, **kwargs}
        
        # 캐시 키 생성
        cache_key = cls._generate_cache_key(model_key, **settings)
        
        # 캐시에서 검색
        with cls._cache_lock:
            if cache_key in cls._llm_cache:
                print(f"🔄 LLM cache hit: {model_key}")
                return cls._llm_cache[cache_key]
            
            # 캐시에 없으면 새로 생성
            print(f"🆕 Creating new LLM instance: {model_key}")
            llm_instance = cls._create_new_llm(model_key, settings)
            
            # 캐시에 저장
            cls._llm_cache[cache_key] = llm_instance
            cls._manage_cache_size()
            
            return llm_instance
    
    @classmethod
    def _create_new_llm(cls, model_key: str, settings: Dict[str, Any]) -> Any:
        """새 LLM 인스턴스 생성 (캐시 미적용)"""
        model_info = cls.SUPPORTED_MODELS[model_key]
        provider = model_info["provider"]
        model_name = model_info["model_name"]
        
        # 프로바이더별 LLM 생성
        if provider == "openai":
            return cls._create_openai_llm(model_name, settings)
        elif provider == "anthropic":
            return cls._create_anthropic_llm(model_name, settings)
        elif provider == "google":
            return cls._create_google_llm(model_name, settings)
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    @classmethod
    def _create_openai_llm(cls, model_name: str, settings: Dict[str, Any]) -> ChatOpenAI:
        """OpenAI LLM 생성"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            temperature=settings["temperature"],
            max_tokens=settings["max_tokens"],
            timeout=settings["timeout"]
        )
    
    @classmethod
    def _create_anthropic_llm(cls, model_name: str, settings: Dict[str, Any]) -> ChatAnthropic:
        """Anthropic LLM 생성"""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        
        return ChatAnthropic(
            model=model_name,
            api_key=api_key,
            temperature=settings["temperature"],
            max_tokens=settings["max_tokens"],
            timeout=settings["timeout"]
        )
    
    @classmethod
    def _create_google_llm(cls, model_name: str, settings: Dict[str, Any]) -> ChatGoogleGenerativeAI:
        """Google LLM 생성"""
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY or GEMINI_API_KEY environment variable is required")
        
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=settings["temperature"],
            max_output_tokens=settings["max_tokens"],
            timeout=settings["timeout"]
        )
    
    @classmethod
    def get_supported_models(cls) -> list:
        """지원되는 모든 모델 키 반환"""
        return list(cls.SUPPORTED_MODELS.keys())
    
    @classmethod
    def get_cache_stats(cls) -> Dict[str, Any]:
        """캐시 통계 반환"""
        with cls._cache_lock:
            return {
                "cache_size": len(cls._llm_cache),
                "max_cache_size": cls._max_cache_size,
                "cached_models": list(cls._llm_cache.keys())
            }
    
    @classmethod
    def clear_cache(cls) -> None:
        """캐시 전체 정리"""
        with cls._cache_lock:
            cleared_count = len(cls._llm_cache)
            cls._llm_cache.clear()
            print(f"LLM cache cleared: {cleared_count} instances removed")
    
    @classmethod
    def get_model_info(cls, model_key: str) -> Dict[str, str]:
        """특정 모델의 상세 정보 반환"""
        if model_key not in cls.SUPPORTED_MODELS:
            raise ValueError(f"Unknown model: {model_key}")
        
        model_info = cls.SUPPORTED_MODELS[model_key].copy()
        
        # 프로바이더별 추가 정보
        provider = model_info["provider"]
        if provider == "openai":
            model_info.update({
                "display_name": f"OpenAI {model_key.upper()}",
                "context_window": "128k" if "gpt-4" in model_key else "32k",
                "cost_tier": "premium" if "gpt-4o" in model_key else "standard"
            })
        elif provider == "anthropic":
            model_info.update({
                "display_name": f"Anthropic {model_key.replace('-', ' ').title()}",
                "context_window": "200k",
                "cost_tier": "premium" if "opus" in model_key else "standard"
            })
        elif provider == "google":
            model_info.update({
                "display_name": f"Google {model_key.replace('-', ' ').title()}",
                "context_window": "1M" if "2.0" in model_key else "2M",
                "cost_tier": "budget" if "flash" in model_key else "standard"
            })
        
        return model_info
    
    @classmethod
    def validate_api_keys(cls) -> Dict[str, bool]:
        """모든 프로바이더의 API 키 존재 여부 확인"""
        return {
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "google": bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))
        }
    
    @classmethod
    def print_available_models(cls) -> None:
        """사용 가능한 모델들을 깔끔하게 출력"""
        api_status = cls.validate_api_keys()
        cache_stats = cls.get_cache_stats()
        
        print("\n" + "="*60)
        print("           🤖 AVAILABLE AI MODELS")
        print("="*60)
        print(f"Cache: {cache_stats['cache_size']}/{cache_stats['max_cache_size']} instances")
        
        by_provider = {}
        for model_key, info in cls.SUPPORTED_MODELS.items():
            provider = info["provider"]
            if provider not in by_provider:
                by_provider[provider] = []
            by_provider[provider].append(model_key)
        
        for provider, models in by_provider.items():
            status = "✅" if api_status[provider] else "❌"
            provider_name = provider.title()
            print(f"\n{status} {provider_name}:")
            
            for model in models:
                model_info = cls.get_model_info(model)
                cost_icon = {"budget": "💰", "standard": "💳", "premium": "💎"}.get(
                    model_info.get("cost_tier", "standard"), "💳"
                )
                # 캐시된 모델 표시
                cached = "🔄" if any(model in key for key in cache_stats['cached_models']) else "  "
                print(f"   {cost_icon} {cached} {model}")
        
        print("\n" + "="*60)
        if not all(api_status.values()):
            print("❗ Missing API keys:")
            for provider, available in api_status.items():
                if not available:
                    key_name = {"openai": "OPENAI_API_KEY", 
                              "anthropic": "ANTHROPIC_API_KEY",
                              "google": "GOOGLE_API_KEY or GEMINI_API_KEY"}[provider]
                    print(f"   - {key_name}")
        print()


# 편의 함수들
def create_llm(model_key: str, **kwargs):
    """LLM 생성 편의 함수"""
    return LLMFactory.create_llm(model_key, **kwargs)


def get_available_models():
    """사용 가능한 모델 목록 반환 편의 함수"""
    return LLMFactory.get_supported_models()


def print_models():
    """모델 목록 출력 편의 함수"""
    LLMFactory.print_available_models()


def clear_llm_cache():
    """LLM 캐시 정리 편의 함수"""
    LLMFactory.clear_cache()


def get_llm_cache_stats():
    """LLM 캐시 통계 편의 함수"""
    return LLMFactory.get_cache_stats()


# 테스트 함수
def test_model(model_key: str, test_prompt: str = "Hello, how are you?") -> bool:
    """
    특정 모델을 테스트
    
    Args:
        model_key: 테스트할 모델
        test_prompt: 테스트 프롬프트
        
    Returns:
        테스트 성공 여부
    """
    try:
        llm = create_llm(model_key)
        response = llm.invoke(test_prompt)
        print(f"✅ {model_key}: {response.content[:50]}...")
        return True
    except Exception as e:
        print(f"❌ {model_key}: {str(e)[:50]}...")
        return False


if __name__ == "__main__":
    # 사용 예시 및 테스트
    print_models()
    
    # 간단한 연결 테스트 (API 키가 있는 경우에만)
    api_status = LLMFactory.validate_api_keys()
    if any(api_status.values()):
        print("\n🧪 Testing available models...")
        for model_key in LLMFactory.get_supported_models():
            provider = LLMFactory.SUPPORTED_MODELS[model_key]["provider"]
            if api_status[provider]:
                test_model(model_key)