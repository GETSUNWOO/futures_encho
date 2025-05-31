"""
시뮬레이션 거래 실행기
- 가상계좌를 통한 백테스팅 및 시뮬레이션
- BaseExecutor 상속하여 가상 거래 로직 구현
"""
from typing import Dict, Any, Optional
from datetime import datetime
from .base_executor import BaseExecutor


class TestExecutor(BaseExecutor):
    """가상계좌를 통한 시뮬레이션 실행기"""
    
    def __init__(self, initial_balance: float = 10000.0):
        """
        초기화
        
        Args:
            initial_balance: 초기 USDT 잔액
        """
        super().__init__()
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.current_position: Optional[Dict[str, Any]] = None
        self.order_id_counter = 1

        # 안전장치용 상태 변수
        self._closing_in_progress = False
        self._last_trigger_check = 0
        
        print(f"Test mode initialized with ${initial_balance:,.2f} USDT")
    
    def set_leverage(self, leverage: int) -> bool:
        """
        레버리지 설정 (시뮬레이션)
        
        Args:
            leverage: 설정할 레버리지 배수
            
        Returns:
            항상 True (시뮬레이션에서는 항상 성공)
        """
        print(f"[SIM] Leverage set to {leverage}x")
        return True
    
    def create_market_order(self, side: str, amount: float) -> Dict[str, Any]:
        """
        시장가 주문 생성 (시뮬레이션)
        
        Args:
            side: 'long' 또는 'short'
            amount: 주문 수량 (BTC)
            
        Returns:
            주문 결과 정보
        """
        try:
            # 현재가는 외부에서 주입받아야 하므로 임시로 0 설정
            # 실제로는 open_position에서 current_price가 전달됨
            entry_price = getattr(self, '_current_market_price', 50000.0)
            
            # 포지션 정보 저장
            self.current_position = {
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'timestamp': datetime.now().isoformat(),
                'unrealized_pnl': 0.0
            }
            
            order_id = f"SIM_{self.order_id_counter}"
            self.order_id_counter += 1
            
            print(f"[SIM] Market {side} order created: {amount} BTC at ${entry_price:,.2f}")
            
            return {
                'order_id': order_id,
                'entry_price': entry_price,
                'amount': amount,
                'side': side,
                'status': 'filled'
            }
            
        except Exception as e:
            print(f"[SIM] Error creating market order: {e}")
            raise
    
    def create_stop_loss_order(self, side: str, amount: float, stop_price: float) -> Dict[str, Any]:
        """
        스탑로스 주문 생성 (시뮬레이션)
        
        Args:
            side: 'long' 또는 'short' (청산 방향)
            amount: 주문 수량
            stop_price: 스탑 가격
            
        Returns:
            주문 결과 정보
        """
        order_id = f"SIM_SL_{self.order_id_counter}"
        self.order_id_counter += 1
        
        order_side = 'sell' if side == 'short' else 'buy'
        
        print(f"[SIM] Stop loss order created: {order_side} {amount} BTC at ${stop_price:,.2f}")
        
        return {
            'order_id': order_id,
            'stop_price': stop_price,
            'amount': amount,
            'side': order_side,
            'type': 'stop_loss'
        }
    
    def create_take_profit_order(self, side: str, amount: float, stop_price: float) -> Dict[str, Any]:
        """
        테이크프로핏 주문 생성 (시뮬레이션)
        
        Args:
            side: 'long' 또는 'short' (청산 방향)
            amount: 주문 수량
            stop_price: 스탑 가격
            
        Returns:
            주문 결과 정보
        """
        order_id = f"SIM_TP_{self.order_id_counter}"
        self.order_id_counter += 1
        
        order_side = 'sell' if side == 'short' else 'buy'
        
        print(f"[SIM] Take profit order created: {order_side} {amount} BTC at ${stop_price:,.2f}")
        
        return {
            'order_id': order_id,
            'stop_price': stop_price,
            'amount': amount,
            'side': order_side,
            'type': 'take_profit'
        }
    
    def check_position_status(self) -> Dict[str, Any]:
        """
        현재 포지션 상태 확인 (시뮬레이션)
        
        Returns:
            포지션 정보
        """
        if self.current_position:
            # 현재가로 미실현 손익 계산
            current_price = getattr(self, '_current_market_price', self.current_position['entry_price'])
            side = self.current_position['side']
            amount = self.current_position['amount']
            entry_price = self.current_position['entry_price']
            
            if side == 'long':
                unrealized_pnl = (current_price - entry_price) * amount
            else:
                unrealized_pnl = (entry_price - current_price) * amount
            
            return {
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'unrealized_pnl': unrealized_pnl,
                'is_open': True
            }
        
        return {
            'side': None,
            'amount': 0,
            'entry_price': 0,
            'unrealized_pnl': 0,
            'is_open': False
        }
    
    def close_position(self, reason: str = "manual") -> Dict[str, Any]:
        """현재 포지션 강제 종료 - 중복 방지 안전장치 추가"""
        
        # 1. 포지션 존재 확인
        if not self.current_position:
            return {
                'success': False,
                'message': 'No open position to close'
            }
        
        # 2. 중복 청산 방지
        if self._closing_in_progress:
            return {
                'success': False,
                'message': 'Position close already in progress'
            }
        
        self._closing_in_progress = True
        
        try:
            side = self.current_position['side']
            amount = self.current_position['amount']
            entry_price = self.current_position['entry_price']
            current_price = getattr(self, '_current_market_price', entry_price)
            
            # 손익 계산
            if side == 'long':
                profit_loss = (current_price - entry_price) * amount
                profit_loss_percentage = (current_price / entry_price - 1) * 100
            else:
                profit_loss = (entry_price - current_price) * amount
                profit_loss_percentage = (1 - current_price / entry_price) * 100
            
            # 잔액 업데이트
            self.current_balance += profit_loss
            
            print(f"[SIM] Position closed ({reason}): {side} {amount} BTC")
            print(f"[SIM] P/L: ${profit_loss:,.2f} ({profit_loss_percentage:.2f}%)")
            print(f"[SIM] New balance: ${self.current_balance:,.2f}")
            
            # 포지션 정리
            result = {
                'success': True,
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'exit_price': current_price,
                'profit_loss': profit_loss,
                'profit_loss_percentage': profit_loss_percentage,
                'reason': reason,
                'order_id': f"SIM_CLOSE_{self.order_id_counter}"
            }
            
            # 포지션 상태 초기화
            self.current_position = None
            self.order_id_counter += 1
            
            return result
            
        except Exception as e:
            print(f"[SIM] Error closing position: {e}")
            return {
                'success': False,
                'message': f'Error closing position: {e}'
            }
        finally:
            # 청산 진행 플래그 해제 (반드시 실행)
            self._closing_in_progress = False
    
    def update_market_price(self, current_price: float) -> None:
        """
        현재 시장가 업데이트 (시뮬레이션용)
        
        Args:
            current_price: 현재 BTC 가격
        """
        self._current_market_price = current_price
    
    def check_sl_tp_triggers(self, current_price: float, sl_price: float, tp_price: float) -> Optional[str]:
        """SL/TP 트리거 조건 확인 - 중복 방지 안전장치 추가"""
        
        # 1. 중복 체크 방지 (0.5초 이내)
        current_time = time.time()
        if current_time - self._last_trigger_check < 0.5:
            return None
        
        self._last_trigger_check = current_time
        
        # 2. 포지션 존재 확인
        if not self.current_position:
            return None
        
        side = self.current_position['side']
        
        if side == 'long':
            if current_price <= sl_price:
                return 'stop_loss'
            elif current_price >= tp_price:
                return 'take_profit'
        else:  # short
            if current_price >= sl_price:
                return 'stop_loss'
            elif current_price <= tp_price:
                return 'take_profit'
        
        return None
    
    def get_account_balance(self) -> float:
        """
        USDT 계좌 잔액 조회 (시뮬레이션)
        
        Returns:
            가용 USDT 잔액
        """
        return self.current_balance
    
    def get_total_return(self) -> float:
        """
        총 수익률 계산
        
        Returns:
            총 수익률 (%)
        """
        return ((self.current_balance - self.initial_balance) / self.initial_balance) * 100
    
    def reset_account(self, balance: Optional[float] = None) -> None:
        """
        계좌 초기화
        
        Args:
            balance: 새로운 초기 잔액 (None이면 기존 초기 잔액 사용)
        """
        if balance is not None:
            self.initial_balance = balance
        
        self.current_balance = self.initial_balance
        self.current_position = None
        self.order_id_counter = 1
        
        print(f"[SIM] Account reset to ${self.initial_balance:,.2f} USDT")
    
    def print_account_summary(self) -> None:
        """계좌 요약 정보 출력"""
        total_return = self.get_total_return()
        position_status = self.check_position_status()
        
        print(f"\n=== [SIM] Account Summary ===")
        print(f"Initial Balance: ${self.initial_balance:,.2f}")
        print(f"Current Balance: ${self.current_balance:,.2f}")
        print(f"Total Return: {total_return:+.2f}%")
        print(f"Open Position: {position_status['side'] or 'None'}")
        if position_status['is_open']:
            print(f"Unrealized P/L: ${position_status['unrealized_pnl']:+,.2f}")
        print("=============================\n")