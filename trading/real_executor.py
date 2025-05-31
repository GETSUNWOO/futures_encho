"""
실거래 실행기
- Binance API를 통한 실제 거래 실행
- BaseExecutor 상속하여 구체적인 거래 로직 구현
"""
import ccxt
from typing import Dict, Any
from .base_executor import BaseExecutor


class RealExecutor(BaseExecutor):
    """Binance를 통한 실거래 실행기"""
    
    def __init__(self, exchange: ccxt.Exchange):
        """
        초기화
        
        Args:
            exchange: ccxt Binance 거래소 객체
        """
        super().__init__()
        self.exchange = exchange
    
    def set_leverage(self, leverage: int) -> bool:
        """
        레버리지 설정
        
        Args:
            leverage: 설정할 레버리지 배수
            
        Returns:
            성공 여부
        """
        try:
            self.exchange.set_leverage(leverage, self.symbol)
            print(f"Leverage set to {leverage}x")
            return True
        except Exception as e:
            print(f"Error setting leverage: {e}")
            return False
    
    def create_market_order(self, side: str, amount: float) -> Dict[str, Any]:
        """
        시장가 주문 생성
        
        Args:
            side: 'long' 또는 'short'
            amount: 주문 수량 (BTC)
            
        Returns:
            주문 결과 정보
        """
        try:
            if side == 'long':
                order = self.exchange.create_market_buy_order(self.symbol, amount)
            else:  # short
                order = self.exchange.create_market_sell_order(self.symbol, amount)
            
            # 체결 가격 조회 (ticker에서 현재가 사용)
            ticker = self.exchange.fetch_ticker(self.symbol)
            entry_price = ticker['last']
            
            print(f"Market {side} order created: {amount} BTC at ${entry_price:,.2f}")
            
            return {
                'order_id': order['id'],
                'entry_price': entry_price,
                'amount': amount,
                'side': side,
                'status': 'filled'
            }
            
        except Exception as e:
            print(f"Error creating market order: {e}")
            raise
    
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
        try:
            order_side = 'sell' if side == 'short' else 'buy'
            
            order = self.exchange.create_order(
                self.symbol, 
                'STOP_MARKET', 
                order_side, 
                amount, 
                None, 
                {'stopPrice': stop_price}
            )
            
            print(f"Stop loss order created: {order_side} {amount} BTC at ${stop_price:,.2f}")
            
            return {
                'order_id': order['id'],
                'stop_price': stop_price,
                'amount': amount,
                'side': order_side,
                'type': 'stop_loss'
            }
            
        except Exception as e:
            print(f"Error creating stop loss order: {e}")
            raise
    
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
        try:
            order_side = 'sell' if side == 'short' else 'buy'
            
            order = self.exchange.create_order(
                self.symbol, 
                'TAKE_PROFIT_MARKET', 
                order_side, 
                amount, 
                None, 
                {'stopPrice': stop_price}
            )
            
            print(f"Take profit order created: {order_side} {amount} BTC at ${stop_price:,.2f}")
            
            return {
                'order_id': order['id'],
                'stop_price': stop_price,
                'amount': amount,
                'side': order_side,
                'type': 'take_profit'
            }
            
        except Exception as e:
            print(f"Error creating take profit order: {e}")
            raise
    
    def check_position_status(self) -> Dict[str, Any]:
        """
        현재 포지션 상태 확인
        
        Returns:
            포지션 정보 (side, amount, entry_price 등)
        """
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            
            for position in positions:
                if position['symbol'] == 'BTC/USDT:USDT':
                    amt = float(position['info']['positionAmt'])
                    entry_price = float(position['info']['entryPrice']) if position['info']['entryPrice'] else 0
                    unrealized_pnl = float(position['info']['unRealizedProfit']) if position['info']['unRealizedProfit'] else 0
                    
                    if amt > 0:
                        return {
                            'side': 'long',
                            'amount': amt,
                            'entry_price': entry_price,
                            'unrealized_pnl': unrealized_pnl,
                            'is_open': True
                        }
                    elif amt < 0:
                        return {
                            'side': 'short',
                            'amount': abs(amt),
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
            
        except Exception as e:
            print(f"Error checking position status: {e}")
            return {
                'side': None,
                'amount': 0,
                'entry_price': 0,
                'unrealized_pnl': 0,
                'is_open': False
            }
    
    def close_position(self, reason: str = "manual") -> Dict[str, Any]:
        """
        현재 포지션 강제 종료
        
        Args:
            reason: 종료 사유
            
        Returns:
            종료 결과 정보
        """
        try:
            # 현재 포지션 확인
            position_status = self.check_position_status()
            
            if not position_status['is_open']:
                return {
                    'success': False,
                    'message': 'No open position to close'
                }
            
            # 미체결 주문 모두 취소
            self._cancel_all_orders()
            
            # 현재가 조회
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = ticker['last']
            
            # 포지션 방향에 따라 반대 주문 실행
            side = position_status['side']
            amount = position_status['amount']
            entry_price = position_status['entry_price']
            
            if side == 'long':
                # 롱 포지션 -> 매도로 청산
                order = self.exchange.create_market_sell_order(self.symbol, amount)
            else:
                # 숏 포지션 -> 매수로 청산
                order = self.exchange.create_market_buy_order(self.symbol, amount)
            
            # 손익 계산
            if side == 'long':
                profit_loss = (current_price - entry_price) * amount
                profit_loss_percentage = (current_price / entry_price - 1) * 100
            else:
                profit_loss = (entry_price - current_price) * amount
                profit_loss_percentage = (1 - current_price / entry_price) * 100
            
            print(f"Position closed ({reason}): {side} {amount} BTC")
            
            return {
                'success': True,
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'exit_price': current_price,
                'profit_loss': profit_loss,
                'profit_loss_percentage': profit_loss_percentage,
                'reason': reason,
                'order_id': order['id']
            }
            
        except Exception as e:
            print(f"Error closing position: {e}")
            return {
                'success': False,
                'message': f'Error closing position: {e}'
            }
    
    def _cancel_all_orders(self) -> None:
        """모든 미체결 주문 취소"""
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            if open_orders:
                for order in open_orders:
                    self.exchange.cancel_order(order['id'], self.symbol)
                print(f"Cancelled {len(open_orders)} open orders")
        except Exception as e:
            print(f"Error cancelling orders: {e}")
    
    def get_account_balance(self) -> float:
        """
        USDT 계좌 잔액 조회
        
        Returns:
            가용 USDT 잔액
        """
        try:
            balance = self.exchange.fetch_balance()
            return balance['USDT']['free']
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return 0.0