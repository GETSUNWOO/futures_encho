"""
설정 관리 모듈
- 환경 변수 로드
- 거래 모드 설정 (실거래/시뮬레이션)
- API 키 및 기본 설정값 관리
"""
import os
from dotenv import load_dotenv
from typing import Optional

# 환경 변수 로드
load_dotenv()


class Config:
    """애플리케이션 설정 관리"""
    
    # 거래 모드 설정
    TRADING_MODE = os.getenv("TRADING_MODE", "TEST").upper()  # REAL 또는 TEST
    
    # API 키 설정
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
    BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    SERP_API_KEY = os.getenv("SERP_API_KEY")  # 선택사항
    
    # 데이터베이스 설정
    DB_FILE = os.getenv("DB_FILE", "bitcoin_trading.db")
    
    # 거래 설정
    SYMBOL = "BTC/USDT"
    MIN_INVESTMENT_AMOUNT = float(os.getenv("MIN_INVESTMENT_AMOUNT", "100"))  # 최소 투자 금액
    INITIAL_TEST_BALANCE = float(os.getenv("INITIAL_TEST_BALANCE", "10000"))  # 시뮬레이션 초기 잔액
    
    # 루프 설정
    MAIN_LOOP_INTERVAL = int(os.getenv("MAIN_LOOP_INTERVAL", "60"))  # 메인 루프 간격 (초)
    POSITION_CHECK_INTERVAL = int(os.getenv("POSITION_CHECK_INTERVAL", "5"))  # 포지션 체크 간격 (초)
    
    # 바이낸스 거래소 설정
    BINANCE_CONFIG = {
        'enableRateLimit': True,
        'options': {
            'defaultType': 'future',
            'adjustForTimeDifference': True
        }
    }
    
    @classmethod
    def validate_config(cls) -> None:
        """
        필수 설정값 검증
        
        Raises:
            ValueError: 필수 설정값이 누락된 경우
        """
        errors = []
        
        # Gemini API 키는 필수
        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is required")
        
        # 실거래 모드일 때 Binance API 키 필수
        if cls.TRADING_MODE == "REAL":
            if not cls.BINANCE_API_KEY:
                errors.append("BINANCE_API_KEY is required for REAL trading mode")
            if not cls.BINANCE_SECRET_KEY:
                errors.append("BINANCE_SECRET_KEY is required for REAL trading mode")
        
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"- {error}" for error in errors))
    
    @classmethod
    def is_real_trading(cls) -> bool:
        """
        실거래 모드 여부 확인
        
        Returns:
            실거래 모드인지 여부
        """
        return cls.TRADING_MODE == "REAL"
    
    @classmethod
    def is_test_trading(cls) -> bool:
        """
        시뮬레이션 모드 여부 확인
        
        Returns:
            시뮬레이션 모드인지 여부
        """
        return cls.TRADING_MODE == "TEST"
    
    @classmethod
    def get_trading_mode_display(cls) -> str:
        """
        거래 모드 표시용 문자열 반환
        
        Returns:
            거래 모드 문자열
        """
        return "🔴 REAL TRADING" if cls.is_real_trading() else "🟡 TEST MODE"
    
    @classmethod
    def print_config_summary(cls) -> None:
        """설정 요약 정보 출력"""
        print("\n=== Configuration Summary ===")
        print(f"Trading Mode: {cls.get_trading_mode_display()}")
        print(f"Symbol: {cls.SYMBOL}")
        print(f"Database: {cls.DB_FILE}")
        print(f"Min Investment: ${cls.MIN_INVESTMENT_AMOUNT:,.2f}")
        
        if cls.is_test_trading():
            print(f"Test Balance: ${cls.INITIAL_TEST_BALANCE:,.2f}")
        
        print(f"Main Loop Interval: {cls.MAIN_LOOP_INTERVAL}s")
        print(f"Position Check Interval: {cls.POSITION_CHECK_INTERVAL}s")
        
        # API 키 상태 표시 (보안상 일부만)
        print(f"Gemini API: {'✓' if cls.GEMINI_API_KEY else '✗'}")
        print(f"Binance API: {'✓' if cls.BINANCE_API_KEY else '✗'}")
        print(f"SERP API: {'✓' if cls.SERP_API_KEY else '✗ (Optional)'}")
        print("============================\n")
    
    @classmethod
    def get_env_template(cls) -> str:
        """
        .env 파일 템플릿 반환
        
        Returns:
            .env 파일 템플릿 문자열
        """
        return """# Trading Mode: REAL or TEST
TRADING_MODE=TEST

# API Keys
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET_KEY=your_binance_secret_key_here
GEMINI_API_KEY=your_gemini_api_key_here
SERP_API_KEY=your_serp_api_key_here

# Database
DB_FILE=bitcoin_trading.db

# Trading Settings
MIN_INVESTMENT_AMOUNT=100
INITIAL_TEST_BALANCE=10000

# Loop Settings
MAIN_LOOP_INTERVAL=60
POSITION_CHECK_INTERVAL=5
"""


# 설정 검증 실행
try:
    Config.validate_config()
except ValueError as e:
    print(f"Configuration Error: {e}")
    print("\nPlease check your .env file. Here's a template:")
    print(Config.get_env_template())
    exit(1)


# 편의를 위한 전역 변수들
TRADING_MODE = Config.TRADING_MODE
IS_REAL_TRADING = Config.is_real_trading()
IS_TEST_TRADING = Config.is_test_trading()
SYMBOL = Config.SYMBOL
MIN_INVESTMENT_AMOUNT = Config.MIN_INVESTMENT_AMOUNT
MAIN_LOOP_INTERVAL = Config.MAIN_LOOP_INTERVAL