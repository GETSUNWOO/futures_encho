"""
설정 관리 모듈 - LangChain 체인 시스템 확장
- 환경 변수 로드
- 거래 모드 설정 (실거래/시뮬레이션)
- 체인별 AI 모델 설정
- 켈리 공식 및 리스크 관리 설정
- 실행 주기 및 스케줄링 설정
"""
import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional

# 환경 변수 로드
load_dotenv()


class Config:
    """애플리케이션 설정 관리 - LangChain 체인 시스템 지원"""
    
    # =============================================================================
    # 기존 거래 설정 (호환성 유지)
    # =============================================================================
    TRADING_MODE = os.getenv("TRADING_MODE", "TEST").upper()
    SYMBOL = "BTC/USDT"
    MIN_INVESTMENT_AMOUNT = float(os.getenv("MIN_INVESTMENT_AMOUNT", "100"))
    INITIAL_TEST_BALANCE = float(os.getenv("INITIAL_TEST_BALANCE", "10000"))
    
    # API 키 설정
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
    SERP_API_KEY = os.getenv("SERP_API_KEY")
    
    # Binance 기본 설정
    BINANCE_CONFIG = {
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True
        }
    }
    
    # 기존 Gemini 키 (하위 호환성)
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    
    # =============================================================================
    # 새로운 LLM 설정
    # =============================================================================
    
    # AI 모델 API 키들
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    # 체인별 모델 설정
    CHAIN_MODELS = {
        "decision": os.getenv("DECISION_MODEL", "gemini-1.5-flash"),
        "news": os.getenv("NEWS_MODEL", "gemini-1.5-flash"),
        "market_1h": os.getenv("MARKET_1H_MODEL", "gemini-1.5-flash"),
        "market_4h": os.getenv("MARKET_4H_MODEL", "gemini-1.5-flash"),
        "performance": os.getenv("PERFORMANCE_MODEL", "gemini-1.5-flash")
    }
    
    # 체인별 모델 설정 (온도, 토큰 등)
    CHAIN_SETTINGS = {
        "decision": {
            "temperature": float(os.getenv("DECISION_TEMP", "0.1")),
            "max_tokens": int(os.getenv("DECISION_TOKENS", "1500"))
        },
        "news": {
            "temperature": float(os.getenv("NEWS_TEMP", "0.3")),
            "max_tokens": int(os.getenv("NEWS_TOKENS", "2000"))
        },
        "market_1h": {
            "temperature": float(os.getenv("MARKET_1H_TEMP", "0.2")),
            "max_tokens": int(os.getenv("MARKET_1H_TOKENS", "1200"))
        },
        "market_4h": {
            "temperature": float(os.getenv("MARKET_4H_TEMP", "0.2")),
            "max_tokens": int(os.getenv("MARKET_4H_TOKENS", "1200"))
        },
        "performance": {
            "temperature": float(os.getenv("PERFORMANCE_TEMP", "0.1")),
            "max_tokens": int(os.getenv("PERFORMANCE_TOKENS", "1000"))
        }
    }
    
    # =============================================================================
    # 스케줄링 설정
    # =============================================================================
    
    SCHEDULE_INTERVALS = {
        "decision": int(os.getenv("DECISION_INTERVAL", "60")),  # 60초 (1분)
        "news": int(os.getenv("NEWS_INTERVAL", "7200")),       # 7200초 (2시간)
        "market_1h": int(os.getenv("MARKET_1H_INTERVAL", "3600")),  # 3600초 (1시간)
        "market_4h": int(os.getenv("MARKET_4H_INTERVAL", "14400")), # 14400초 (4시간)
        "performance": int(os.getenv("PERFORMANCE_INTERVAL", "3600")) # 3600초 (1시간)
    }
    
    # 포지션 체크 간격
    POSITION_CHECK_INTERVAL = int(os.getenv("POSITION_CHECK_INTERVAL", "5"))
    
    # =============================================================================
    # 켈리 공식 및 리스크 관리
    # =============================================================================
    
    # 켈리 공식 사용 여부
    USE_KELLY_CRITERION = os.getenv("USE_KELLY", "true").lower() == "true"
    
    # 켈리 공식 설정
    KELLY_SETTINGS = {
        "max_position_size": float(os.getenv("MAX_POSITION_SIZE", "0.5")),  # 최대 50%
        "kelly_fraction": float(os.getenv("KELLY_FRACTION", "0.25")),      # 1/4 켈리
        "min_conviction": float(os.getenv("MIN_CONVICTION", "0.55")),      # 최소 확신도 55%
        "max_leverage": int(os.getenv("MAX_LEVERAGE", "10"))               # 최대 레버리지
    }
    
    # 리스크 관리
    RISK_SETTINGS = {
        "default_sl_percent": float(os.getenv("DEFAULT_SL", "0.03")),      # 기본 SL 3%
        "default_tp_percent": float(os.getenv("DEFAULT_TP", "0.06")),      # 기본 TP 6%
        "max_drawdown_limit": float(os.getenv("MAX_DRAWDOWN", "0.2")),     # 최대 드로다운 20%
        "daily_loss_limit": float(os.getenv("DAILY_LOSS_LIMIT", "0.05"))   # 일일 손실 한도 5%
    }
    
    # =============================================================================
    # 데이터베이스 설정
    # =============================================================================
    
    @classmethod
    def get_db_file(cls) -> str:
        """거래 모드에 따른 DB 파일명 반환"""
        base_name = os.getenv("DB_FILE_BASE", "bitcoin_trading")
        suffix = "_REAL" if cls.is_real_trading() else "_TEST"
        return f"{base_name}{suffix}.db"
    
    # =============================================================================
    # 검증 및 유틸리티 메서드
    # =============================================================================
    
    @classmethod
    def validate_config(cls) -> None:
        """필수 설정값 검증"""
        errors = []
        
        # 기본 거래 API 키 검증
        if cls.is_real_trading():
            if not cls.BINANCE_API_KEY:
                errors.append("BINANCE_API_KEY is required for REAL trading")
            if not cls.BINANCE_SECRET_KEY:
                errors.append("BINANCE_SECRET_KEY is required for REAL trading")
        
        # AI 모델 API 키 검증 (최소 하나는 필요)
        ai_keys = [cls.OPENAI_API_KEY, cls.ANTHROPIC_API_KEY, cls.GOOGLE_API_KEY]
        if not any(ai_keys):
            errors.append("At least one AI API key is required (OpenAI, Anthropic, or Google)")
        
        # 켈리 설정 검증
        kelly = cls.KELLY_SETTINGS
        if not (0 < kelly["max_position_size"] <= 1):
            errors.append("MAX_POSITION_SIZE must be between 0 and 1")
        if not (0 < kelly["min_conviction"] < 1):
            errors.append("MIN_CONVICTION must be between 0 and 1")
        
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"- {error}" for error in errors))
    
    @classmethod
    def is_real_trading(cls) -> bool:
        """실거래 모드 여부 확인"""
        return cls.TRADING_MODE == "REAL"
    
    @classmethod
    def is_test_trading(cls) -> bool:
        """시뮬레이션 모드 여부 확인"""
        return cls.TRADING_MODE == "TEST"
    
    @classmethod
    def get_trading_mode_display(cls) -> str:
        """트레이딩 모드 표시용 문자열 반환"""
        if cls.is_real_trading():
            return "🔴 REAL TRADING"
        else:
            return "🟡 TEST TRADING"
    
    @classmethod
    def get_chain_model(cls, chain_name: str) -> str:
        """특정 체인의 모델 반환"""
        return cls.CHAIN_MODELS.get(chain_name, "gpt-4o-mini")
    
    @classmethod
    def get_chain_settings(cls, chain_name: str) -> Dict[str, Any]:
        """특정 체인의 설정 반환"""
        return cls.CHAIN_SETTINGS.get(chain_name, {
            "temperature": 0.1,
            "max_tokens": 1000
        })
    
    @classmethod
    def get_schedule_interval(cls, chain_name: str) -> int:
        """특정 체인의 실행 간격 반환 (초)"""
        return cls.SCHEDULE_INTERVALS.get(chain_name, 3600)
    
    @classmethod
    def print_config_summary(cls) -> None:
        """설정 요약 정보 출력"""
        print("\n" + "="*70)
        print("                🤖 AI TRADING SYSTEM CONFIG")
        print("="*70)
        
        # 거래 모드
        mode_icon = "🔴" if cls.is_real_trading() else "🟡"
        print(f"Trading Mode: {mode_icon} {cls.TRADING_MODE}")
        print(f"Database: {cls.get_db_file()}")
        
        # 켈리 공식 설정
        kelly_status = "✅ Enabled" if cls.USE_KELLY_CRITERION else "❌ Disabled"
        print(f"Kelly Criterion: {kelly_status}")
        if cls.USE_KELLY_CRITERION:
            print(f"  Max Position: {cls.KELLY_SETTINGS['max_position_size']*100:.0f}%")
            print(f"  Kelly Fraction: {cls.KELLY_SETTINGS['kelly_fraction']}")
            print(f"  Min Conviction: {cls.KELLY_SETTINGS['min_conviction']*100:.0f}%")
        
        # AI 모델 설정
        print(f"\n🧠 AI Models:")
        for chain, model in cls.CHAIN_MODELS.items():
            interval = cls.get_schedule_interval(chain)
            if interval >= 3600:
                interval_str = f"{interval//3600}h"
            elif interval >= 60:
                interval_str = f"{interval//60}m"
            else:
                interval_str = f"{interval}s"
            print(f"  {chain.capitalize()}: {model} (every {interval_str})")
        
        # API 키 상태
        print(f"\n🔑 API Keys:")
        keys_status = {
            "Binance": "✅" if cls.BINANCE_API_KEY else "❌",
            "OpenAI": "✅" if cls.OPENAI_API_KEY else "❌",
            "Anthropic": "✅" if cls.ANTHROPIC_API_KEY else "❌",
            "Google": "✅" if cls.GOOGLE_API_KEY else "❌",
            "SERP": "✅" if cls.SERP_API_KEY else "❌ (Optional)"
        }
        for service, status in keys_status.items():
            print(f"  {service}: {status}")
        
        print("="*70 + "\n")
    
    @classmethod
    def get_env_template(cls) -> str:
        """.env 파일 템플릿 반환"""
        return """# Trading Mode
TRADING_MODE=TEST

# Binance API (for real trading)
BINANCE_API_KEY=your_binance_api_key
BINANCE_SECRET_KEY=your_binance_secret_key

# AI Model API Keys
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
GOOGLE_API_KEY=your_google_api_key
GEMINI_API_KEY=your_gemini_api_key  # Alternative to GOOGLE_API_KEY

# News API (Optional)
SERP_API_KEY=your_serp_api_key

# Chain Models (Optional - defaults will be used)
DECISION_MODEL=gpt-4o
NEWS_MODEL=gemini-1.5-flash
MARKET_1H_MODEL=claude-3-5-haiku
MARKET_4H_MODEL=claude-3-5-sonnet
PERFORMANCE_MODEL=gemini-1.5-flash

# Kelly Criterion Settings
USE_KELLY=true
MAX_POSITION_SIZE=0.5
KELLY_FRACTION=0.25
MIN_CONVICTION=0.55
MAX_LEVERAGE=10

# Risk Management
DEFAULT_SL=0.03
DEFAULT_TP=0.06
MAX_DRAWDOWN=0.2
DAILY_LOSS_LIMIT=0.05

# Trading Settings
MIN_INVESTMENT_AMOUNT=100
INITIAL_TEST_BALANCE=10000

# Schedule Intervals (seconds)
DECISION_INTERVAL=60
NEWS_INTERVAL=7200
MARKET_1H_INTERVAL=3600
MARKET_4H_INTERVAL=14400
PERFORMANCE_INTERVAL=3600
POSITION_CHECK_INTERVAL=5
"""


# 설정 검증 및 초기화
try:
    Config.validate_config()
    print("✅ Configuration validated successfully")
except ValueError as e:
    print(f"❌ Configuration Error: {e}")
    print("\nExample .env file:")
    print(Config.get_env_template())


# 편의를 위한 전역 변수들 (기존 코드 호환성)
TRADING_MODE = Config.TRADING_MODE
IS_REAL_TRADING = Config.is_real_trading()
IS_TEST_TRADING = Config.is_test_trading()
SYMBOL = Config.SYMBOL
MIN_INVESTMENT_AMOUNT = Config.MIN_INVESTMENT_AMOUNT
USE_KELLY_CRITERION = Config.USE_KELLY_CRITERION