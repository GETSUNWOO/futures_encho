"""
시장 데이터 수집 모듈
- 멀티 타임프레임 가격 데이터 수집
- 비트코인 뉴스 데이터 수집
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
            serp_api_key: SERP API 키 (뉴스 수집용)
        """
        self.exchange = exchange
        self.serp_api_key = serp_api_key
        self.symbol = "BTC/USDT"
        
        # 타임프레임별 데이터 수집 설정
        self.timeframes = {
            "15m": {"timeframe": "15m", "limit": 96},  # 24시간
            "1h": {"timeframe": "1h", "limit": 48},    # 48시간  
            "4h": {"timeframe": "4h", "limit": 30}     # 5일
        }
    
    def fetch_multi_timeframe_data(self) -> Dict[str, pd.DataFrame]:
        """
        여러 타임프레임의 가격 데이터를 수집
        
        Returns:
            타임프레임별 DataFrame 데이터
        """
        multi_tf_data = {}
        
        for tf_name, tf_params in self.timeframes.items():
            try:
                # OHLCV 데이터 가져오기
                ohlcv = self.exchange.fetch_ohlcv(
                    self.symbol, 
                    timeframe=tf_params["timeframe"], 
                    limit=tf_params["limit"]
                )
                
                # 데이터프레임으로 변환
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                multi_tf_data[tf_name] = df
                print(f"Collected {tf_name} data: {len(df)} candles")
                
            except Exception as e:
                print(f"Error fetching {tf_name} data: {e}")
                multi_tf_data[tf_name] = pd.DataFrame()  # 빈 DataFrame 반환
        
        return multi_tf_data
    
    def fetch_current_price(self) -> float:
        """
        현재 BTC 가격 조회
        
        Returns:
            현재 BTC/USDT 가격
        """
        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            return ticker['last']
        except Exception as e:
            print(f"Error fetching current price: {e}")
            return 0.0
    
    def fetch_bitcoin_news(self, limit: int = 10) -> List[Dict[str, str]]:
        """
        비트코인 관련 최신 뉴스를 가져옴
        
        Args:
            limit: 가져올 뉴스 개수
            
        Returns:
            뉴스 기사 정보 리스트 (제목과 날짜만 포함)
        """
        if not self.serp_api_key:
            print("SERP API key not provided. Skipping news fetch.")
            return []
            
        try:
            url = "https://serpapi.com/search.json"
            params = {
                "engine": "google_news",
                "q": "bitcoin",
                "gl": "us",
                "hl": "en", 
                "api_key": self.serp_api_key
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                news_results = data.get("news_results", [])
                
                # 최신 뉴스만 추출하고 제목과 날짜만 포함
                recent_news = []
                for news in news_results[:limit]:
                    news_item = {
                        "title": news.get("title", ""),
                        "date": news.get("date", "")
                    }
                    recent_news.append(news_item)
                
                print(f"Collected {len(recent_news)} recent news articles")
                return recent_news
            else:
                print(f"Error fetching news: Status code {response.status_code}")
                return []
                
        except Exception as e:
            print(f"Error fetching news: {e}")
            return []
    
    def get_current_positions(self) -> Dict[str, any]:
        """
        현재 포지션 정보를 조회
        
        Returns:
            현재 포지션 정보 (side, amount)
        """
        try:
            positions = self.exchange.fetch_positions([self.symbol])
            
            for position in positions:
                if position['symbol'] == 'BTC/USDT:USDT':
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