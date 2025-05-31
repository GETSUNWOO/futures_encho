"""
트레이딩 실행기 기본 인터페이스
- 실거래와 시뮬레이션의 공통 인터페이스 정의
- 추상 기본 클래스로 구현
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime


class BaseExecutor(ABC):
    """트레이딩 실행기의 기본 인터페이스"""
    
    def __init__(self):
        """기본 초기화"""
        self.symbol = "BTC/USDT"
        self.current_trade_id: Optional[int] = None
    
    @abstractmethod
    def set_leverage(self, leverage: int) -> bool:
        """
        레버리지 설정
        
        Args:
            leverage: 설정할 레버리지 배수
            
        Returns:
            성공 여부
        """
        pass
    
    @abstractmethod
    def create_market_order(self, side: str, amount: float) -> Dict[str, Any]:
        """
        시장가 주문 생성
        
        Args:
            side: 'long' 또는 'short'
            amount: 주문 수량 (BTC)
            
        Returns:
            주문 결과 정보
        """
        pass
    
    @abstractmethod
    def create_stop_loss_order(self, side: str, amount: float, stop_price: float) -> Dict[str, Any]:
        """
        스탑로스 주문 생성
        
        Args:
            side: 'long' 또는 'short' (청산 방향)
            amount: 주문 수량
            stop_price: 스탑 가격
            
        Returns:
            주문 결과 정보
        """
        pass
    
    @abstractmethod
    def create_take_profit_order(self, side: str, amount: float, stop_price: float) -> Dict[str, Any]:
        """
        테이크프로핏 주문 생성
        
        Args:
            side: 'long' 또는 'short' (청산 방향)
            amount: 주문 수량
            stop_price: 스탑 가격
            
        Returns:
            주문 결과 정보
        """
        pass
    
    @abstractmethod
    def check_position_status(self) -> Dict[str, Any]:
        """
        현재 포지션 상태 확인
        
        Returns:
            포지션 정보 (side, amount, entry_price 등)
        """
        pass
    
    @abstractmethod
    def close_position(self, reason: str = "manual") -> Dict[str, Any]:
        """
        현재 포지션 강제 종료
        
        Args:
            reason: 종료 사유
            
        Returns:
            종료 결과 정보
        """
        pass
    
    def open_position(self, trading_decision: Dict[str, Any], investment_amount: float, 
                     current_price: float) -> Dict[str, Any]:
        """
        포지션 진입 (공통 로직)
        
        Args:
            trading_decision: AI 트레이딩 결정
            investment_amount: 투자 금액
            current_price: 현재 가격
            
        Returns:
            포지션 진입 결과
        """
        action = trading_decision['direction'].lower()
        leverage = trading_decision['recommended_leverage']
        sl_pct = trading_decision['stop_loss_percentage']
        tp_pct = trading_decision['take_profit_percentage']
        
        # 주문 수량 계산
        amount = self._calculate_order_amount(investment_amount, current_price)
        
        # 레버리지 설정
        if not self.set_leverage(leverage):
            raise Exception("Failed to set leverage")
        
        # 진입 주문
        entry_order = self.create_market_order(action, amount)
        entry_price = entry_order.get('entry_price', current_price)
        
        # SL/TP 가격 계산
        sl_price, tp_price = self._calculate_sl_tp_prices(
            action, entry_price, sl_pct, tp_pct
        )
        
        # SL/TP 주문 생성
        exit_side = 'short' if action == 'long' else 'long'
        sl_order = self.create_stop_loss_order(exit_side, amount, sl_price)
        tp_order = self.create_take_profit_order(exit_side, amount, tp_price)
        
        # 결과 반환
        return {
            'action': action,
            'entry_price': entry_price,
            'amount': amount,
            'leverage': leverage,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'sl_percentage': sl_pct,
            'tp_percentage': tp_pct,
            'investment_amount': investment_amount,
            'entry_order': entry_order,
            'sl_order': sl_order,
            'tp_order': tp_order,
            'timestamp': datetime.now().isoformat()
        }
    
    def _calculate_order_amount(self, investment_amount: float, current_price: float) -> float:
        """
        주문 수량 계산
        
        Args:
            investment_amount: 투자 금액
            current_price: 현재 가격
            
        Returns:
            주문 수량 (BTC)
        """
        import math
        # BTC 수량 = 투자금액 / 현재가격, 소수점 3자리까지 반올림
        amount = math.ceil((investment_amount / current_price) * 1000) / 1000
        return amount
    
    def _calculate_sl_tp_prices(self, action: str, entry_price: float, 
                               sl_pct: float, tp_pct: float) -> tuple:
        """
        스탑로스/테이크프로핏 가격 계산
        
        Args:
            action: 'long' 또는 'short'
            entry_price: 진입 가격
            sl_pct: 스탑로스 비율
            tp_pct: 테이크프로핏 비율
            
        Returns:
            (sl_price, tp_price) 튜플
        """
        if action == 'long':
            sl_price = round(entry_price * (1 - sl_pct), 2)
            tp_price = round(entry_price * (1 + tp_pct), 2)
        else:  # short
            sl_price = round(entry_price * (1 + sl_pct), 2)
            tp_price = round(entry_price * (1 - tp_pct), 2)
        
        return sl_price, tp_price
    
    def print_position_opened(self, position_result: Dict[str, Any]) -> None:
        """
        포지션 진입 결과 출력
        
        Args:
            position_result: 포지션 진입 결과
        """
        action = position_result['action'].upper()
        entry_price = position_result['entry_price']
        sl_price = position_result['sl_price']
        tp_price = position_result['tp_price']
        leverage = position_result['leverage']
        sl_pct = position_result['sl_percentage'] * 100
        tp_pct = position_result['tp_percentage'] * 100
        
        print(f"\n=== {action} Position Opened ===")
        print(f"Entry: ${entry_price:,.2f}")
        print(f"Stop Loss: ${sl_price:,.2f} ({'-' if action == 'LONG' else '+'}{sl_pct:.2f}%)")
        print(f"Take Profit: ${tp_price:,.2f} ({'+' if action == 'LONG' else '-'}{tp_pct:.2f}%)")
        print(f"Leverage: {leverage}x")
        print("===========================")
    
    def print_position_closed(self, close_result: Dict[str, Any]) -> None:
        """
        포지션 종료 결과 출력
        
        Args:
            close_result: 포지션 종료 결과
        """
        entry_price = close_result.get('entry_price', 0)
        exit_price = close_result.get('exit_price', 0)
        profit_loss = close_result.get('profit_loss', 0)
        profit_loss_pct = close_result.get('profit_loss_percentage', 0)
        
        print(f"\n=== Position Closed ===")
        print(f"Entry: ${entry_price:,.2f}")
        print(f"Exit: ${exit_price:,.2f}")
        print(f"P/L: ${profit_loss:,.2f} ({profit_loss_pct:.2f}%)")
        print("=======================")
    
    def set_current_trade_id(self, trade_id: int) -> None:
        """
        현재 거래 ID 설정
        
        Args:
            trade_id: 거래 ID
        """
        self.current_trade_id = trade_id
    
    def get_current_trade_id(self) -> Optional[int]:
        """
        현재 거래 ID 반환
        
        Returns:
            현재 거래 ID 또는 None
        """
        return self.current_trade_id