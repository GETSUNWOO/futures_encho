"""
실거래 실행기
- Binance API를 통한 실제 거래 실행
- BaseExecutor 상속하여 구체적인 거래 로직 구현
- 선물거래 심볼 정확도 개선
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
        
        # 거래소 타입에 따라 심볼 설정
        if exchange.options.get('defaultType') == 'future':
            self.symbol = "BTC/USDT:USDT"  # 선물 심볼
            print("🔴 Real executor initialized for FUTURES trading")
        else:
            self.symbol = "BTC/USDT"       # 현물 심볼
            print("🔴 Real executor initialized for SPOT trading")
    
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
            
            # 선물거래면 마크 프라이스 우선 사용
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
    
    # ... (나머지 메서드들은 기존과 동일하되 self.symbol 사용)
    
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