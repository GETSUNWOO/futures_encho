"""
데이터베이스 헬퍼 유틸리티
- 체인 결과 저장/조회
- 캐시 관리
- 성과 데이터 집계
- 기존 database/recorder.py 확장
"""
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from contextlib import contextmanager
from config import Config


class ChainDB:
    """체인 시스템용 데이터베이스 헬퍼"""
    
    def __init__(self, db_file: Optional[str] = None):
        """
        초기화
        
        Args:
            db_file: 데이터베이스 파일 경로 (None이면 config에서 가져옴)
        """
        self.db_file = db_file or Config.get_db_file()
        self._setup_tables()
    
    @contextmanager
    def get_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row  # dict-like 접근 가능
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _setup_tables(self) -> None:
        """체인 시스템용 테이블 생성"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 체인 결과 저장 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS chain_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                result_data TEXT NOT NULL,
                expiry_time TEXT,
                model_used TEXT,
                processing_time REAL
            )
            ''')
            
            # 체인 결과 테이블 인덱스
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_chain_results_name_time 
            ON chain_results(chain_name, timestamp)
            ''')
            
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_chain_results_expiry 
            ON chain_results(expiry_time)
            ''')
            
            # 뉴스 요약 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS news_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                articles_count INTEGER NOT NULL,
                summary_data TEXT NOT NULL,
                sentiment_score REAL,
                expiry_time TEXT NOT NULL
            )
            ''')
            
            # 뉴스 요약 테이블 인덱스
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_news_summary_timestamp 
            ON news_summary(timestamp)
            ''')
            
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_news_summary_expiry 
            ON news_summary(expiry_time)
            ''')
            
            # 시장 추세 요약 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trend_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timeframe TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                trend_data TEXT NOT NULL,
                confidence REAL,
                expiry_time TEXT NOT NULL
            )
            ''')
            
            # 시장 추세 테이블 인덱스
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trend_summary_timeframe_time 
            ON trend_summary(timeframe, timestamp)
            ''')
            
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_trend_summary_expiry 
            ON trend_summary(expiry_time)
            ''')
            
            # 성과 요약 테이블
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS performance_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                summary_data TEXT NOT NULL,
                total_trades INTEGER,
                win_rate REAL,
                avg_return REAL,
                expiry_time TEXT NOT NULL
            )
            ''')
            
            # 성과 요약 테이블 인덱스
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_performance_summary_timestamp 
            ON performance_summary(timestamp)
            ''')
            
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_performance_summary_expiry 
            ON performance_summary(expiry_time)
            ''')
            
            # 실행 로그 테이블 (디버깅용)
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS chain_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chain_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                log_level TEXT NOT NULL,
                message TEXT NOT NULL
            )
            ''')
            
            # 로그 테이블 인덱스
            cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_chain_logs_name_time 
            ON chain_logs(chain_name, timestamp)
            ''')
            
            conn.commit()
    
    # =========================================================================
    # 체인 결과 저장/조회
    # =========================================================================
    
    def save_chain_result(
        self, 
        chain_name: str, 
        result_data: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
        model_used: Optional[str] = None,
        processing_time: Optional[float] = None
    ) -> int:
        """
        체인 실행 결과 저장
        
        Args:
            chain_name: 체인 이름
            result_data: 결과 데이터
            ttl_seconds: 캐시 유효 시간 (초)
            model_used: 사용된 모델
            processing_time: 처리 시간
            
        Returns:
            저장된 레코드 ID
        """
        timestamp = datetime.now().isoformat()
        expiry_time = None
        
        if ttl_seconds:
            expiry_time = (datetime.now() + timedelta(seconds=ttl_seconds)).isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO chain_results 
            (chain_name, timestamp, result_data, expiry_time, model_used, processing_time)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                chain_name,
                timestamp,
                json.dumps(result_data, default=str),
                expiry_time,
                model_used,
                processing_time
            ))
            conn.commit()
            return cursor.lastrowid
    
    def get_latest_chain_result(self, chain_name: str, max_age_seconds: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        최신 체인 결과 조회
        
        Args:
            chain_name: 체인 이름
            max_age_seconds: 최대 나이 (초)
            
        Returns:
            체인 결과 또는 None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
            SELECT result_data, timestamp, model_used, processing_time
            FROM chain_results
            WHERE chain_name = ?
            '''
            params = [chain_name]
            
            # 만료되지 않은 결과만 조회
            query += ' AND (expiry_time IS NULL OR expiry_time > ?)'
            params.append(datetime.now().isoformat())
            
            # 최대 나이 제한
            if max_age_seconds:
                cutoff_time = (datetime.now() - timedelta(seconds=max_age_seconds)).isoformat()
                query += ' AND timestamp > ?'
                params.append(cutoff_time)
            
            query += ' ORDER BY timestamp DESC LIMIT 1'
            
            cursor.execute(query, params)
            row = cursor.fetchone()
            
            if row:
                return {
                    'data': json.loads(row['result_data']),
                    'timestamp': row['timestamp'],
                    'model_used': row['model_used'],
                    'processing_time': row['processing_time']
                }
            return None
    
    # =========================================================================
    # 특화 테이블 메서드들
    # =========================================================================
    
    def save_news_summary(self, articles_count: int, summary_data: Dict[str, Any], sentiment_score: float) -> int:
        """뉴스 요약 저장"""
        timestamp = datetime.now().isoformat()
        expiry_time = (datetime.now() + timedelta(hours=4)).isoformat()  # 4시간 후 만료
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO news_summary (timestamp, articles_count, summary_data, sentiment_score, expiry_time)
            VALUES (?, ?, ?, ?, ?)
            ''', (timestamp, articles_count, json.dumps(summary_data, default=str), sentiment_score, expiry_time))
            conn.commit()
            return cursor.lastrowid
    
    def get_latest_news_summary(self) -> Optional[Dict[str, Any]]:
        """최신 뉴스 요약 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT summary_data, sentiment_score, timestamp, articles_count
            FROM news_summary
            WHERE expiry_time > ?
            ORDER BY timestamp DESC LIMIT 1
            ''', (datetime.now().isoformat(),))
            
            row = cursor.fetchone()
            if row:
                return {
                    'summary': json.loads(row['summary_data']),
                    'sentiment_score': row['sentiment_score'],
                    'timestamp': row['timestamp'],
                    'articles_count': row['articles_count']
                }
            return None
    
    def save_trend_summary(self, timeframe: str, trend_data: Dict[str, Any], confidence: float) -> int:
        """시장 추세 요약 저장"""
        timestamp = datetime.now().isoformat()
        # 타임프레임에 따른 만료 시간 설정
        ttl_hours = {"1h": 1.5, "4h": 6}.get(timeframe, 2)
        expiry_time = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO trend_summary (timeframe, timestamp, trend_data, confidence, expiry_time)
            VALUES (?, ?, ?, ?, ?)
            ''', (timeframe, timestamp, json.dumps(trend_data, default=str), confidence, expiry_time))
            conn.commit()
            return cursor.lastrowid
    
    def get_latest_trend_summary(self, timeframe: str) -> Optional[Dict[str, Any]]:
        """최신 추세 요약 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT trend_data, confidence, timestamp
            FROM trend_summary
            WHERE timeframe = ? AND expiry_time > ?
            ORDER BY timestamp DESC LIMIT 1
            ''', (timeframe, datetime.now().isoformat()))
            
            row = cursor.fetchone()
            if row:
                return {
                    'trend': json.loads(row['trend_data']),
                    'confidence': row['confidence'],
                    'timestamp': row['timestamp']
                }
            return None
    
    def save_performance_summary(self, summary_data: Dict[str, Any]) -> int:
        """성과 요약 저장"""
        timestamp = datetime.now().isoformat()
        expiry_time = (datetime.now() + timedelta(hours=2)).isoformat()  # 2시간 후 만료
        
        total_trades = summary_data.get('total_trades', 0)
        win_rate = summary_data.get('win_rate', 0.0)
        avg_return = summary_data.get('avg_return', 0.0)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            INSERT INTO performance_summary 
            (timestamp, summary_data, total_trades, win_rate, avg_return, expiry_time)
            VALUES (?, ?, ?, ?, ?, ?)
            ''', (timestamp, json.dumps(summary_data, default=str), total_trades, win_rate, avg_return, expiry_time))
            conn.commit()
            return cursor.lastrowid
    
    def get_latest_performance_summary(self) -> Optional[Dict[str, Any]]:
        """최신 성과 요약 조회"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
            SELECT summary_data, total_trades, win_rate, avg_return, timestamp
            FROM performance_summary
            WHERE expiry_time > ?
            ORDER BY timestamp DESC LIMIT 1
            ''', (datetime.now().isoformat(),))
            
            row = cursor.fetchone()
            if row:
                return {
                    'summary': json.loads(row['summary_data']),
                    'total_trades': row['total_trades'],
                    'win_rate': row['win_rate'],
                    'avg_return': row['avg_return'],
                    'timestamp': row['timestamp']
                }
            return None
    
    # =========================================================================
    # 캐시 관리
    # =========================================================================
    
    def cleanup_expired_cache(self) -> int:
        """만료된 캐시 데이터 정리"""
        current_time = datetime.now().isoformat()
        deleted_count = 0
        
        tables_with_expiry = [
            'chain_results', 'news_summary', 'trend_summary', 'performance_summary'
        ]
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for table in tables_with_expiry:
                cursor.execute(f'DELETE FROM {table} WHERE expiry_time <= ?', (current_time,))
                deleted_count += cursor.rowcount
            conn.commit()
        
        return deleted_count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """캐시 통계 조회"""
        current_time = datetime.now().isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            stats = {}
            tables = ['chain_results', 'news_summary', 'trend_summary', 'performance_summary']
            
            for table in tables:
                cursor.execute(f'SELECT COUNT(*) as total FROM {table}')
                total = cursor.fetchone()['total']
                
                cursor.execute(f'SELECT COUNT(*) as valid FROM {table} WHERE expiry_time > ? OR expiry_time IS NULL', (current_time,))
                valid = cursor.fetchone()['valid']
                
                stats[table] = {
                    'total_records': total,
                    'valid_records': valid,
                    'expired_records': total - valid
                }
        
        return stats
    
    # =========================================================================
    # 로깅
    # =========================================================================
    
    def log_chain_event(self, chain_name: str, level: str, message: str) -> None:
        """체인 이벤트 로깅"""
        timestamp = datetime.now().isoformat()
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO chain_logs (chain_name, timestamp, log_level, message)
                VALUES (?, ?, ?, ?)
                ''', (chain_name, timestamp, level, message))
                conn.commit()
        except Exception as e:
            print(f"Failed to log chain event: {e}")
    
    def get_recent_logs(self, chain_name: Optional[str] = None, hours: int = 24) -> List[Dict[str, Any]]:
        """최근 로그 조회"""
        cutoff_time = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if chain_name:
                cursor.execute('''
                SELECT chain_name, timestamp, log_level, message
                FROM chain_logs
                WHERE chain_name = ? AND timestamp > ?
                ORDER BY timestamp DESC LIMIT 100
                ''', (chain_name, cutoff_time))
            else:
                cursor.execute('''
                SELECT chain_name, timestamp, log_level, message
                FROM chain_logs
                WHERE timestamp > ?
                ORDER BY timestamp DESC LIMIT 100
                ''', (cutoff_time,))
            
            return [dict(row) for row in cursor.fetchall()]


# 전역 인스턴스 (싱글톤 패턴)
_chain_db_instance = None

def get_chain_db() -> ChainDB:
    """ChainDB 싱글톤 인스턴스 반환"""
    global _chain_db_instance
    if _chain_db_instance is None:
        _chain_db_instance = ChainDB()
    return _chain_db_instance


# 편의 함수들
def save_chain_result(chain_name: str, result_data: Dict[str, Any], **kwargs) -> int:
    """체인 결과 저장 편의 함수"""
    return get_chain_db().save_chain_result(chain_name, result_data, **kwargs)


def get_latest_result(chain_name: str, **kwargs) -> Optional[Dict[str, Any]]:
    """최신 체인 결과 조회 편의 함수"""
    return get_chain_db().get_latest_chain_result(chain_name, **kwargs)


def cleanup_cache() -> int:
    """캐시 정리 편의 함수"""
    return get_chain_db().cleanup_expired_cache()


def log_chain(chain_name: str, level: str, message: str) -> None:
    """체인 로깅 편의 함수"""
    get_chain_db().log_chain_event(chain_name, level, message)