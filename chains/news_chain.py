"""
뉴스 체인 - 뉴스 수집 및 감성 분석
- SERP API 또는 RSS를 통한 뉴스 수집
- AI 기반 뉴스 요약 및 감성 분석
- 트레이딩 관련성 필터링
- 결과 캐싱 (2시간 주기)
"""
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from langchain.prompts import ChatPromptTemplate
from langchain.schema import HumanMessage, SystemMessage

from config import Config
from llm_factory import create_llm
from utils.db import get_chain_db, log_chain
from utils.retry_utils import retry_on_llm_error

class NewsChain:
    """뉴스 수집 및 분석 체인"""
    
    def __init__(self):
        """초기화"""
        self.db = get_chain_db()
        self.model_name = Config.get_chain_model("news")
        self.settings = Config.get_chain_settings("news")
        self.serp_api_key = Config.SERP_API_KEY
        
        # LLM 생성
        try:
            self.llm = create_llm(self.model_name, **self.settings)
            log_chain("news", "INFO", f"Initialized with model: {self.model_name}")
        except Exception as e:
            log_chain("news", "ERROR", f"Failed to initialize LLM: {e}")
            raise
        
        # 프롬프트 템플릿
        self.analysis_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a cryptocurrency news analyst specializing in Bitcoin market sentiment analysis.

Analyze the provided news articles and provide a comprehensive summary focused on trading implications.

Your analysis must include:
1. Overall market sentiment (bullish/bearish/neutral)
2. Key themes and categories (regulation, adoption, technical, macro)
3. Impact assessment on BTC price
4. Relevance score for trading decisions

Respond in JSON format:
{
  "sentiment": "bullish/bearish/neutral",
  "sentiment_score": 0.0-1.0,
  "key_themes": ["theme1", "theme2"],
  "categories": {
    "regulation": {"count": 0, "sentiment": "neutral"},
    "adoption": {"count": 0, "sentiment": "neutral"},
    "technical": {"count": 0, "sentiment": "neutral"},
    "macro": {"count": 0, "sentiment": "neutral"}
  },
  "impact_assessment": "brief description of likely price impact",
  "trading_relevance": 0.0-1.0,
  "summary": "2-3 sentence summary of key points",
  "risk_factors": ["factor1", "factor2"]
}

Use sentiment_score: 0.0-0.3 (bearish), 0.3-0.7 (neutral), 0.7-1.0 (bullish)
Use trading_relevance: 0.0-0.3 (low), 0.3-0.7 (medium), 0.7-1.0 (high)"""),
            ("human", "Analyze these Bitcoin news articles:\n\n{news_articles}")
        ])
    
    def run(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        뉴스 체인 실행
        
        Args:
            force_refresh: 캐시 무시하고 강제 갱신
            
        Returns:
            뉴스 분석 결과
        """
        start_time = time.time()
        
        try:
            # 캐시된 결과 확인 (force_refresh가 아닌 경우)
            if not force_refresh:
                cached_result = self.db.get_latest_news_summary()
                if cached_result:
                    log_chain("news", "INFO", "Using cached news summary")
                    return {
                        "success": True,
                        "source": "cache",
                        "timestamp": cached_result["timestamp"],
                        "data": cached_result["summary"],
                        "sentiment_score": cached_result["sentiment_score"],
                        "articles_count": cached_result["articles_count"]
                    }
            
            # 뉴스 수집
            log_chain("news", "INFO", "Collecting fresh news articles")
            articles = self._collect_news()
            
            if not articles:
                log_chain("news", "WARNING", "No news articles collected")
                return self._empty_result("No news articles available")
            
            # AI 분석
            log_chain("news", "INFO", f"Analyzing {len(articles)} articles")
            analysis_result = self._analyze_news(articles)
            
            # 결과 저장
            self.db.save_news_summary(
                articles_count=len(articles),
                summary_data=analysis_result,
                sentiment_score=analysis_result.get("sentiment_score", 0.5)
            )
            
            processing_time = time.time() - start_time
            log_chain("news", "INFO", f"News analysis completed in {processing_time:.2f}s")
            
            return {
                "success": True,
                "source": "fresh",
                "timestamp": datetime.now().isoformat(),
                "data": analysis_result,
                "sentiment_score": analysis_result.get("sentiment_score", 0.5),
                "articles_count": len(articles),
                "processing_time": processing_time
            }
            
        except Exception as e:
            log_chain("news", "ERROR", f"News chain failed: {e}")
            return self._error_result(str(e))
    
    def _collect_news(self) -> List[Dict[str, str]]:
        """뉴스 수집 (SERP API 우선, 실패시 RSS 백업)"""
        try:
            # SERP API 시도
            if self.serp_api_key:
                articles = self._collect_from_serp()
                if articles:
                    return articles
                log_chain("news", "WARNING", "SERP API failed, trying RSS backup")
            
            # RSS 백업
            return self._collect_from_rss()
            
        except Exception as e:
            log_chain("news", "ERROR", f"News collection failed: {e}")
            return []
    
    def _collect_from_serp(self) -> List[Dict[str, str]]:
        """SERP API를 통한 뉴스 수집"""
        try:
            url = "https://serpapi.com/search.json"
            params = {
                "engine": "google_news",
                "q": "bitcoin cryptocurrency BTC",
                "gl": "us",
                "hl": "en",
                "num": 15,
                "api_key": self.serp_api_key
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                news_results = data.get("news_results", [])
                
                articles = []
                for news in news_results:
                    article = {
                        "title": news.get("title", ""),
                        "source": news.get("source", ""),
                        "date": news.get("date", ""),
                        "snippet": news.get("snippet", "")
                    }
                    if article["title"]:  # 제목이 있는 경우만 추가
                        articles.append(article)
                
                log_chain("news", "INFO", f"Collected {len(articles)} articles from SERP")
                return articles
            else:
                log_chain("news", "ERROR", f"SERP API error: {response.status_code}")
                return []
                
        except Exception as e:
            log_chain("news", "ERROR", f"SERP collection error: {e}")
            return []
    
    def _collect_from_rss(self) -> List[Dict[str, str]]:
        """RSS를 통한 뉴스 수집 (백업)"""
        try:
            # CoinDesk RSS (신뢰할 수 있는 소스)
            rss_urls = [
                "https://www.coindesk.com/arc/outboundfeeds/rss/",
                "https://cointelegraph.com/rss",
            ]
            
            articles = []
            
            for rss_url in rss_urls:
                try:
                    response = requests.get(rss_url, timeout=10)
                    if response.status_code == 200:
                        # 간단한 RSS 파싱 (실제로는 feedparser 사용 권장)
                        content = response.text
                        
                        # 제목만 추출하는 간단한 방법
                        import re
                        titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', content)
                        if not titles:
                            titles = re.findall(r'<title>(.*?)</title>', content)
                        
                        for title in titles[:10]:  # 최대 10개
                            if any(keyword.lower() in title.lower() for keyword in ["bitcoin", "btc", "crypto"]):
                                articles.append({
                                    "title": title,
                                    "source": rss_url.split("//")[1].split("/")[0],
                                    "date": datetime.now().strftime("%Y-%m-%d"),
                                    "snippet": ""
                                })
                        
                        if len(articles) >= 10:
                            break
                            
                except Exception as e:
                    log_chain("news", "WARNING", f"RSS source failed {rss_url}: {e}")
                    continue
            
            log_chain("news", "INFO", f"Collected {len(articles)} articles from RSS")
            return articles
            
        except Exception as e:
            log_chain("news", "ERROR", f"RSS collection error: {e}")
            return []
    
    @retry_on_llm_error(max_retries=2)
    def _analyze_news(self, articles: List[Dict[str, str]]) -> Dict[str, Any]:
        """AI를 통한 뉴스 분석"""
        try:
            # 뉴스 기사들을 텍스트로 변환
            news_text = ""
            for i, article in enumerate(articles, 1):
                news_text += f"{i}. {article['title']}"
                if article['snippet']:
                    news_text += f" - {article['snippet']}"
                if article['source']:
                    news_text += f" ({article['source']})"
                news_text += "\n"
            
            # AI 분석 요청
            messages = self.analysis_prompt.format_messages(news_articles=news_text)
            response = self.llm.invoke(messages)
            
            # JSON 응답 파싱
            response_text = response.content.strip()
            
            # JSON 응답 정리
            if "```json" in response_text:
                start_idx = response_text.find("```json") + 7
                end_idx = response_text.find("```", start_idx)
                if end_idx != -1:
                    response_text = response_text[start_idx:end_idx].strip()
            elif "```" in response_text:
                parts = response_text.split("```")
                if len(parts) >= 3:
                    response_text = parts[1].strip()
            
            analysis_result = json.loads(response_text)
            
            # 결과 검증 및 기본값 설정
            analysis_result = self._validate_analysis_result(analysis_result)
            
            log_chain("news", "INFO", f"Analysis completed - Sentiment: {analysis_result['sentiment']}")
            return analysis_result
            
        except json.JSONDecodeError as e:
            log_chain("news", "ERROR", f"Failed to parse AI response: {e}")
            return self._fallback_analysis(articles)
        except Exception as e:
            log_chain("news", "ERROR", f"News analysis failed: {e}")
            return self._fallback_analysis(articles)
    
    def _validate_analysis_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """분석 결과 검증 및 기본값 설정"""
        # 필수 필드 기본값
        defaults = {
            "sentiment": "neutral",
            "sentiment_score": 0.5,
            "key_themes": [],
            "categories": {
                "regulation": {"count": 0, "sentiment": "neutral"},
                "adoption": {"count": 0, "sentiment": "neutral"},
                "technical": {"count": 0, "sentiment": "neutral"},
                "macro": {"count": 0, "sentiment": "neutral"}
            },
            "impact_assessment": "Neutral market impact expected",
            "trading_relevance": 0.5,
            "summary": "Mixed news sentiment with no clear directional bias",
            "risk_factors": []
        }
        
        # 기본값으로 채우기
        for key, default_value in defaults.items():
            if key not in result:
                result[key] = default_value
        
        # 값 범위 검증
        result["sentiment_score"] = max(0.0, min(1.0, result.get("sentiment_score", 0.5)))
        result["trading_relevance"] = max(0.0, min(1.0, result.get("trading_relevance", 0.5)))
        
        # sentiment 값 검증
        if result["sentiment"] not in ["bullish", "bearish", "neutral"]:
            result["sentiment"] = "neutral"
        
        return result
    
    def _fallback_analysis(self, articles: List[Dict[str, str]]) -> Dict[str, Any]:
        """AI 분석 실패시 폴백 분석"""
        # 간단한 키워드 기반 감성 분석
        bullish_keywords = ["adoption", "institutional", "etf", "bullish", "surge", "rise", "positive"]
        bearish_keywords = ["regulation", "ban", "crash", "bearish", "decline", "negative", "concern"]
        
        bullish_score = 0
        bearish_score = 0
        
        for article in articles:
            text = (article["title"] + " " + article.get("snippet", "")).lower()
            
            for keyword in bullish_keywords:
                if keyword in text:
                    bullish_score += 1
            
            for keyword in bearish_keywords:
                if keyword in text:
                    bearish_score += 1
        
        # 감성 결정
        if bullish_score > bearish_score:
            sentiment = "bullish"
            sentiment_score = 0.6 + min(0.3, (bullish_score - bearish_score) * 0.1)
        elif bearish_score > bullish_score:
            sentiment = "bearish"
            sentiment_score = 0.4 - min(0.3, (bearish_score - bullish_score) * 0.1)
        else:
            sentiment = "neutral"
            sentiment_score = 0.5
        
        return {
            "sentiment": sentiment,
            "sentiment_score": sentiment_score,
            "key_themes": ["fallback_analysis"],
            "categories": {
                "regulation": {"count": bearish_score, "sentiment": "bearish" if bearish_score > 0 else "neutral"},
                "adoption": {"count": bullish_score, "sentiment": "bullish" if bullish_score > 0 else "neutral"},
                "technical": {"count": 0, "sentiment": "neutral"},
                "macro": {"count": 0, "sentiment": "neutral"}
            },
            "impact_assessment": f"Simple keyword analysis: {sentiment}",
            "trading_relevance": 0.3,  # 낮은 신뢰도
            "summary": f"Fallback analysis based on keyword sentiment. {len(articles)} articles analyzed.",
            "risk_factors": ["fallback_analysis_used"]
        }
    
    def _empty_result(self, reason: str) -> Dict[str, Any]:
        """빈 결과 반환"""
        return {
            "success": False,
            "source": "empty",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "sentiment": "neutral",
                "sentiment_score": 0.5,
                "summary": "No news data available"
            },
            "sentiment_score": 0.5,
            "articles_count": 0
        }
    
    def _error_result(self, error_msg: str) -> Dict[str, Any]:
        """에러 결과 반환"""
        return {
            "success": False,
            "source": "error",
            "error": error_msg,
            "timestamp": datetime.now().isoformat(),
            "data": {
                "sentiment": "neutral",
                "sentiment_score": 0.5,
                "summary": "Error occurred during news analysis"
            },
            "sentiment_score": 0.5,
            "articles_count": 0
        }


# 편의 함수
def run_news_analysis(force_refresh: bool = False) -> Dict[str, Any]:
    """뉴스 분석 실행 편의 함수"""
    chain = NewsChain()
    return chain.run(force_refresh)


def get_latest_news_sentiment() -> float:
    """최신 뉴스 감성 점수만 반환"""
    db = get_chain_db()
    news_summary = db.get_latest_news_summary()
    if news_summary:
        return news_summary["sentiment_score"]
    return 0.5  # 중립


def print_news_summary() -> None:
    """뉴스 요약 정보 출력"""
    db = get_chain_db()
    news_summary = db.get_latest_news_summary()
    
    if news_summary:
        data = news_summary["summary"]
        print(f"\n📰 News Summary ({news_summary['articles_count']} articles)")
        print(f"Sentiment: {data['sentiment']} ({data['sentiment_score']:.2f})")
        print(f"Summary: {data['summary']}")
        print(f"Trading Relevance: {data.get('trading_relevance', 0.5):.2f}")
    else:
        print("\n📰 No recent news summary available")