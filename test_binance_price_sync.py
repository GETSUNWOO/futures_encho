#!/usr/bin/env python3
"""
바이낸스 BTC 선물시장 가격 싱크 테스트
- 실제 바이낸스 선물 차트와 우리 봇이 가져오는 가격 비교
- 실시간 가격 모니터링
- 지연시간 측정
"""

import ccxt
import time
import requests
from datetime import datetime
from config import Config

class BinancePriceSyncTest:
    """바이낸스 가격 싱크 테스트 클래스"""
    
    def __init__(self):
        """초기화"""
        print("🔍 Binance Price Sync Test Starting...")
        print("="*60)
        
        # 거래소 설정 (API 키 없이 공개 데이터만 사용)
        self.exchange_public = ccxt.binance()
        
        # API 키가 있는 경우 설정
        if Config.BINANCE_API_KEY and Config.BINANCE_SECRET_KEY:
            self.exchange_private = ccxt.binance({
                'apiKey': Config.BINANCE_API_KEY,
                'secret': Config.BINANCE_SECRET_KEY,
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True
                }
            })
            print("✅ Private API available")
        else:
            self.exchange_private = None
            print("⚠️  No API keys - using public data only")
        
        self.symbol = "BTC/USDT"
        self.future_symbol = "BTC/USDT:USDT"
        
    def get_binance_web_price(self):
        """바이낸스 웹사이트에서 직접 가격 가져오기"""
        try:
            # 바이낸스 공개 API
            url = "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT"
            response = requests.get(url, timeout=5)
            data = response.json()
            return float(data['price'])
        except Exception as e:
            print(f"❌ Web API Error: {e}")
            return None
    
    def get_ccxt_spot_price(self):
        """CCXT로 현물 가격 가져오기"""
        try:
            ticker = self.exchange_public.fetch_ticker(self.symbol)
            return {
                'last': ticker['last'],
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'timestamp': ticker['timestamp']
            }
        except Exception as e:
            print(f"❌ CCXT Spot Error: {e}")
            return None
    
    def get_ccxt_futures_price(self):
        """CCXT로 선물 가격 가져오기"""
        try:
            # 선물거래 모드로 설정
            exchange_future = ccxt.binance()
            exchange_future.options['defaultType'] = 'future'
            
            ticker = exchange_future.fetch_ticker(self.future_symbol)
            return {
                'last': ticker['last'],
                'mark': ticker.get('mark', ticker['last']),
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'timestamp': ticker['timestamp']
            }
        except Exception as e:
            print(f"❌ CCXT Futures Error: {e}")
            return None
    
    def get_private_api_price(self):
        """개인 API로 가격 가져오기 (API 키 필요)"""
        if not self.exchange_private:
            return None
        
        try:
            ticker = self.exchange_private.fetch_ticker(self.future_symbol)
            return {
                'last': ticker['last'],
                'mark': ticker.get('mark', ticker['last']),
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'timestamp': ticker['timestamp']
            }
        except Exception as e:
            print(f"❌ Private API Error: {e}")
            return None
    
    def test_single_price_comparison(self):
        """한 번의 가격 비교 테스트"""
        print(f"\n🕐 {datetime.now().strftime('%H:%M:%S')} - Price Comparison Test")
        print("-" * 60)
        
        start_time = time.time()
        
        # 1. 바이낸스 웹 API (선물)
        web_price = self.get_binance_web_price()
        web_time = time.time() - start_time
        
        # 2. CCXT 현물
        spot_data = self.get_ccxt_spot_price()
        spot_time = time.time() - start_time
        
        # 3. CCXT 선물
        futures_data = self.get_ccxt_futures_price()
        futures_time = time.time() - start_time
        
        # 4. 개인 API
        private_data = self.get_private_api_price()
        private_time = time.time() - start_time
        
        # 결과 출력
        print(f"🌐 Binance Web API (Futures): ${web_price:,.2f} ({web_time:.3f}s)")
        
        if spot_data:
            print(f"📊 CCXT Spot Price: ${spot_data['last']:,.2f} ({spot_time:.3f}s)")
            
            bid = spot_data['bid'] if spot_data['bid'] is not None else 0
            ask = spot_data['ask'] if spot_data['ask'] is not None else 0
            print(f"   Bid/Ask: ${bid:,.2f} / ${ask:,.2f}")
        
        if futures_data:
            print(f"🚀 CCXT Futures Price: ${futures_data['last']:,.2f} ({futures_time:.3f}s)")
            print(f"   Mark Price: ${futures_data['mark']:,.2f}")
            
            bid = futures_data['bid'] if futures_data['bid'] is not None else 0
            ask = futures_data['ask'] if futures_data['ask'] is not None else 0
            print(f"   Bid/Ask: ${bid:,.2f} / ${ask:,.2f}")
        
        if private_data:
            print(f"🔑 Private API (Futures): ${private_data['last']:,.2f} ({private_time:.3f}s)")
            print(f"   Mark Price: ${private_data['mark']:,.2f}")
        
        # 가격 차이 분석
        if web_price and futures_data:
            diff = abs(web_price - futures_data['last'])
            diff_pct = (diff / web_price) * 100
            print(f"\n📈 Price Difference:")
            print(f"   Web vs CCXT Futures: ${diff:.2f} ({diff_pct:.4f}%)")
            
            if diff_pct > 0.01:  # 0.01% 이상 차이
                print(f"   ⚠️  WARNING: Price difference > 0.01%")
            else:
                print(f"   ✅ Price sync looks good")
        
        return {
            'web_price': web_price,
            'spot_price': spot_data['last'] if spot_data else None,
            'futures_price': futures_data['last'] if futures_data else None,
            'private_price': private_data['last'] if private_data else None,
            'timestamp': datetime.now()
        }
    
    def test_continuous_monitoring(self, duration_minutes=5, interval_seconds=10):
        """지속적인 가격 모니터링"""
        print(f"\n🔄 Starting continuous monitoring for {duration_minutes} minutes")
        print(f"📊 Update interval: {interval_seconds} seconds")
        print("=" * 60)
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        price_history = []
        
        try:
            while time.time() < end_time:
                result = self.test_single_price_comparison()
                price_history.append(result)
                
                remaining = int(end_time - time.time())
                print(f"⏰ Remaining: {remaining//60}m {remaining%60}s")
                
                time.sleep(interval_seconds)
                
        except KeyboardInterrupt:
            print("\n🛑 Monitoring stopped by user")
        
        # 요약 통계
        self.print_monitoring_summary(price_history)
    
    def print_monitoring_summary(self, price_history):
        """모니터링 결과 요약"""
        if not price_history:
            return
        
        print("\n" + "="*60)
        print("📊 MONITORING SUMMARY")
        print("="*60)
        
        # 가격 차이 통계
        differences = []
        for record in price_history:
            if record['web_price'] and record['futures_price']:
                diff_pct = abs(record['web_price'] - record['futures_price']) / record['web_price'] * 100
                differences.append(diff_pct)
        
        if differences:
            print(f"🎯 Price Difference Statistics:")
            print(f"   Average: {sum(differences)/len(differences):.4f}%")
            print(f"   Maximum: {max(differences):.4f}%")
            print(f"   Minimum: {min(differences):.4f}%")
            
            if max(differences) > 0.05:
                print(f"   ⚠️  WARNING: Some price differences > 0.05%")
            else:
                print(f"   ✅ All price differences within acceptable range")
        
        print(f"\n📈 Total samples: {len(price_history)}")
        print(f"🕐 Duration: {(price_history[-1]['timestamp'] - price_history[0]['timestamp']).total_seconds():.0f} seconds")
    
    def test_our_bot_price_fetching(self):
        """우리 봇이 실제로 사용하는 방식으로 가격 가져오기 테스트"""
        print(f"\n🤖 Testing our bot's price fetching method")
        print("-" * 60)
        
        try:
            # MarketFetcher 모방 - 선물 모드로 설정
            from data.market_fetcher import MarketFetcher
            
            # 선물 거래소 설정 (봇과 동일하게)
            test_exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'future',  # 선물 모드로 설정
                    'adjustForTimeDifference': True
                }
            })
            
            market_fetcher = MarketFetcher(test_exchange)
            
            start_time = time.time()
            bot_price = market_fetcher.fetch_current_price()
            fetch_time = time.time() - start_time
            
            print(f"🤖 Bot's fetch_current_price(): ${bot_price:,.2f} ({fetch_time:.3f}s)")
            
            # 비교를 위해 선물 웹 API와 비교
            web_price = self.get_binance_web_price()
            
            if web_price and bot_price:
                diff = abs(web_price - bot_price)
                diff_pct = (diff / web_price) * 100
                print(f"📊 Comparison with Futures Web API:")
                print(f"   Web (Futures): ${web_price:,.2f}")
                print(f"   Bot (Futures): ${bot_price:,.2f}")
                print(f"   Difference: ${diff:.2f} ({diff_pct:.4f}%)")
                
                if diff_pct < 0.01:
                    print(f"   ✅ Bot price fetching is accurate!")
                else:
                    print(f"   ⚠️  Bot price might have sync issues")
            
        except Exception as e:
            print(f"❌ Bot price test error: {e}")
            import traceback
            traceback.print_exc()
    
    def run_full_test(self):
        """전체 테스트 실행"""
        print("🚀 Starting Full Binance Price Sync Test")
        print("="*60)
        
        # 1. 단일 가격 비교
        print("\n1️⃣ Single Price Comparison Test")
        self.test_single_price_comparison()
        
        # 2. 우리 봇 방식 테스트
        print("\n2️⃣ Our Bot's Price Fetching Test")
        self.test_our_bot_price_fetching()
        
        # 3. 사용자 선택 - 지속 모니터링
        print("\n3️⃣ Continuous Monitoring (Optional)")
        response = input("Do you want to run continuous monitoring? (y/N): ").lower()
        
        if response == 'y':
            duration = input("Duration in minutes (default 5): ").strip()
            duration = int(duration) if duration.isdigit() else 5
            
            interval = input("Interval in seconds (default 10): ").strip()
            interval = int(interval) if interval.isdigit() else 10
            
            self.test_continuous_monitoring(duration, interval)
        
        print("\n✅ Price sync test completed!")


def main():
    """메인 함수"""
    print("🔍 Binance BTC Futures Price Sync Test")
    print("This tool helps verify price synchronization with Binance")
    print()
    
    try:
        tester = BinancePriceSyncTest()
        tester.run_full_test()
        
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n💥 Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()