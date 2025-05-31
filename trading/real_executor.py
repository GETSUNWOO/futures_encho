"""
실거래 실행기 - 완전한 구현
- Binance API를 통한 실제 거래 실행
- BaseExecutor 상속하여 모든 추상 메서드 구현
- 안전장치 포함
"""
import ccxt
import time
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
        
        # 안전장치용 상태 변수
        self._last_order_time = 0
        self._order_in_progress = False
        
        # 거래소 타입에 따라 심볼 설정
        if exchange.options.get('defaultType') == 'future':
            self.symbol = "BTC/USDT:USDT"
            print("🔴 Real executor initialized for FUTURES trading")
        else:
            self.symbol = "BTC/USDT"
            print("🔴 Real executor initialized for SPOT trading")
    
    def set_leverage(self, leverage: int) -> bool:
        """
        레버리지 설정
        
        Args:
            leverage: 설정할 레버리지 배수
            
        Returns:
            성공 여부
        """
        try:
            # 선물거래에서만 레버리지 설정 가능
            if self.exchange.options.get('defaultType') == 'future':
                self.exchange.set_leverage(leverage, self.symbol)
                print(f"Leverage set to {leverage}x")
                return True
            else:
                print(f"Leverage not applicable for spot trading")
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
        # 중복 주문 방지 (2초 이내)
        current_time = time.time()
        if current_time - self._last_order_time < 2.0:
            raise Exception("Order too frequent - please wait")
        
        # 주문 진행 중 체크
        if self._order_in_progress:
            raise Exception("Another order is in progress")
        
        self._order_in_progress = True
        self._last_order_time = current_time
        
        try:
            if side == 'long':
                order = self.exchange.create_market_buy_order(self.symbol, amount)
            else:  # short
                order = self.exchange.create_market_sell_order(self.symbol, amount)
            
            # 체결 가격 조회
            ticker = self.exchange.fetch_ticker(self.symbol)
            
            if self.exchange.options.get('defaultType') == 'future':
                entry_price = ticker.get('mark', ticker['last'])
            else:
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
        finally:
            # 주문 진행 플래그 해제
            self._order_in_progress = False
    
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
            
            # 선물거래용 스탑 주문
            if self.exchange.options.get('defaultType') == 'future':
                order = self.exchange.create_order(
                    self.symbol, 
                    'STOP_MARKET', 
                    order_side, 
                    amount, 
                    None, 
                    {'stopPrice': stop_price}
                )
            else:
                # 현물거래용 스탑 주문
                order = self.exchange.create_order(
                    self.symbol,
                    'stop_loss_limit',
                    order_side,
                    amount,
                    stop_price,
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
            
            # 선물거래용 테이크프로핏 주문
            if self.exchange.options.get('defaultType') == 'future':
                order = self.exchange.create_order(
                    self.symbol,
                    'TAKE_PROFIT_MARKET',
                    order_side,
                    amount,
                    None,
                    {'stopPrice': stop_price}
                )
            else:
                # 현물거래용 테이크프로핏 주문
                order = self.exchange.create_order(
                    self.symbol,
                    'take_profit_limit',
                    order_side,
                    amount,
                    stop_price,
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
            
            # 심볼 체크 (선물/현물에 따라 다름)
            symbol_to_check = self.symbol
            if self.exchange.options.get('defaultType') == 'future':
                symbol_to_check = 'BTC/USDT:USDT'
            
            for position in positions:
                if position['symbol'] == symbol_to_check:
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
        # 중복 청산 방지
        if self._order_in_progress:
            return {
                'success': False,
                'message': 'Another operation is in progress'
            }
        
        self._order_in_progress = True
        
        try:
            # 현재 포지션 확인
            position_status = self.check_position_status()
            if not position_status['is_open']:
                return {
                    'success': False,
                    'message': 'No open position to close'
                }
            
            side = position_status['side']
            amount = position_status['amount']
            entry_price = position_status['entry_price']
            
            # 모든 미체결 주문 취소 (SL/TP 주문들)
            try:
                open_orders = self.exchange.fetch_open_orders(self.symbol)
                for order in open_orders:
                    self.exchange.cancel_order(order['id'], self.symbol)
                print(f"Cancelled {len(open_orders)} open orders")
            except Exception as e:
                print(f"Error cancelling orders: {e}")
            
            # 반대 방향으로 청산
            if side == 'long':
                order = self.exchange.create_market_sell_order(self.symbol, amount)
            else:
                order = self.exchange.create_market_buy_order(self.symbol, amount)
            
            # 청산 가격
            ticker = self.exchange.fetch_ticker(self.symbol)
            exit_price = ticker['last']
            
            # 손익 계산
            if side == 'long':
                profit_loss = (exit_price - entry_price) * amount
                profit_loss_percentage = (exit_price / entry_price - 1) * 100
            else:
                profit_loss = (entry_price - exit_price) * amount
                profit_loss_percentage = (1 - exit_price / entry_price) * 100
            
            print(f"Position closed ({reason}): {side} {amount} BTC")
            print(f"Entry: ${entry_price:,.2f}, Exit: ${exit_price:,.2f}")
            print(f"P/L: ${profit_loss:,.2f} ({profit_loss_percentage:.2f}%)")
            
            return {
                'success': True,
                'side': side,
                'amount': amount,
                'entry_price': entry_price,
                'exit_price': exit_price,
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
        finally:
            # 주문 진행 플래그 해제
            self._order_in_progress = False
    
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