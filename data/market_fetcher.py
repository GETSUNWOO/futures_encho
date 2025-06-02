"""
시장 데이터 수집 모듈
- 멀티 타임프레임 가격 데이터 수집
- 비트코인 뉴스 데이터 수집
- 선물거래 가격 정확도 개선
"""
import ccxt
import pandas as pd
import requests
from typing import Dict, List, Optional


class MarketFetcher:
    """시장 데이터 수집을 담당하는 클래스"""
    
    def __init__(self, exchange: ccxt.Exchange, serp_api_key: Optional[str] = None):
        """
        초기화
        
        Args:
            exchange: ccxt 거래소 객체
        """
        self.exchange = exchange
        
        # 거래소 타입에 따라 심볼 설정 (RealExecutor와 동일하게)
        if hasattr(exchange, 'options') and exchange.options.get('defaultType') == 'future':
            self.symbol = "BTC/USDT:USDT"  # 선물 심볼
            self.is_futures = True
            print("📊 MarketFetcher initialized for FUTURES")
        else:
            self.symbol = "BTC/USDT"       # 현물 심볼
            self.is_futures = False
            print("📊 MarketFetcher initialized for SPOT")
    
    def fetch_current_price(self) -> float:
        """
        현재 BTC 가격 조회 - 선물/현물에 따라 적절한 가격 반환
        
        Returns:
            현재 BTC/USDT 가격
        """
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            
            # 선물거래면 마크 프라이스 우선 사용 (더 정확함)
            if self.symbol == "BTC/USDT:USDT":
                price = ticker.get('mark', ticker['last'])
                print(f"📊 Futures price fetched: ${price:,.2f} (mark: {ticker.get('mark', 'N/A')}, last: {ticker['last']})")
            else:
                price = ticker['last']
                print(f"📊 Spot price fetched: ${price:,.2f}")
            
            return price
            
        except Exception as e:
            print(f"Error fetching current price: {e}")
            return 0.0
    
    def fetch_detailed_price_info(self) -> Dict[str, float]:
        """
        상세 가격 정보 조회 (디버깅 및 모니터링용)
        
        Returns:
            다양한 가격 정보
        """
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            
            price_info = {
                'last': float(ticker.get('last', 0)),
                'bid': float(ticker.get('bid', 0)),
                'ask': float(ticker.get('ask', 0)),
                'high': float(ticker.get('high', 0)),
                'low': float(ticker.get('low', 0)),
                'close': float(ticker.get('close', 0))
            }
            
            if self.is_futures:
                # 선물 전용 정보
                price_info.update({
                    'mark': float(ticker.get('mark', 0)),
                    'index': float(ticker.get('index', 0)),
                    'mid': (price_info['bid'] + price_info['ask']) / 2 if price_info['bid'] and price_info['ask'] else 0
                })
            
            return price_info
            
        except Exception as e:
            print(f"Error fetching detailed price info: {e}")
            return {}
    
    def debug_price_sources(self) -> None:
        """
        가격 소스별 비교 (디버깅용)
        """
        try:
            print("\n" + "="*40)
            print("🔍 PRICE SOURCE DEBUG")
            print("="*40)
            
            # 현재 사용 중인 가격
            current_price = self.fetch_current_price()
            print(f"📊 Bot Price: ${current_price:,.2f}")
            
            # 상세 가격 정보
            detailed = self.fetch_detailed_price_info()
            if detailed:
                print(f"💹 Last Trade: ${detailed.get('last', 0):,.2f}")
                print(f"📈 Bid: ${detailed.get('bid', 0):,.2f}")
                print(f"📉 Ask: ${detailed.get('ask', 0):,.2f}")
                
                if self.is_futures:
                    print(f"🎯 Mark Price: ${detailed.get('mark', 0):,.2f}")
                    print(f"📋 Index Price: ${detailed.get('index', 0):,.2f}")
                    print(f"⚖️  Mid Price: ${detailed.get('mid', 0):,.2f}")
            
            # 현물과 선물 비교
            if self.is_futures:
                try:
                    # 현물 가격도 가져와서 비교
                    spot_exchange = ccxt.binance({'options': {'defaultType': 'spot'}})
                    spot_ticker = spot_exchange.fetch_ticker('BTC/USDT')
                    spot_price = float(spot_ticker['last'])
                    
                    futures_price = detailed.get('mark', detailed.get('last', 0))
                    premium = futures_price - spot_price
                    premium_pct = (premium / spot_price) * 100
                    
                    print(f"\n📊 SPOT vs FUTURES:")
                    print(f"   Spot Price: ${spot_price:,.2f}")
                    print(f"   Futures Price: ${futures_price:,.2f}")
                    print(f"   Premium: ${premium:+,.2f} ({premium_pct:+.3f}%)")
                    
                except Exception as e:
                    print(f"   Error comparing with spot: {e}")
            
            print("="*40 + "\n")
            
        except Exception as e:
            print(f"Debug error: {e}")
    
    def get_current_positions(self) -> Dict[str, any]:
        """
        현재 포지션 정보를 조회
        
        Returns:
            현재 포지션 정보 (side, amount)
        """
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            
            for position in positions:
                symbol_to_check = 'BTC/USDT:USDT' if self.is_futures else 'BTC/USDT'
                if position['symbol'] == symbol_to_check:
                    amt = float(position['info']['positionAmt'])
                    if amt > 0:
                        return {'side': 'long', 'amount': amt}
                    elif amt < 0:
                        return {'side': 'short', 'amount': abs(amt)}
            
            return {'side': None, 'amount': 0}
            
        except Exception as e:
            print(f"Error fetching positions: {e}")
            return {'side': None, 'amount': 0}
    
    def get_account_balance(self) -> float:
        """
        USDT 잔액 조회
        
        Returns:
            가용 USDT 잔액
        """
        try:
            balance = self.exchange.fetch_balance()
            return balance['USDT']['free']
        except Exception as e:
            print(f"Error fetching balance: {e}")
            return 0.0
    
    def cancel_all_orders(self) -> bool:
        """
        모든 미체결 주문 취소
        
        Returns:
            성공 여부
        """
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            if open_orders:
                for order in open_orders:
                    self.exchange.cancel_order(order['id'], self.symbol)
                print(f"Cancelled {len(open_orders)} open orders")
                return True
            else:
                print("No open orders to cancel")
                return True
        except Exception as e:
            print(f"Error cancelling orders: {e}")
            return False