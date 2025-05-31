"""
데이터베이스 기록 및 관리 모듈
- 거래 기록 저장 및 조회
- AI 분석 결과 저장
- 성과 분석 및 통계
"""
import sqlite3
from datetime import datetime
from typing import Dict, Any, List, Optional


class DatabaseRecorder:
    """거래 기록 및 AI 분석 데이터 관리"""
    
    def __init__(self, db_file: str = "bitcoin_trading.db"):
        """
        초기화
        
        Args:
            db_file: 데이터베이스 파일 경로
        """
        self.db_file = db_file
        self.setup_database()
    
    def setup_database(self) -> None:
        """데이터베이스 및 필요한 테이블 생성"""
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # 거래 기록 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            action TEXT NOT NULL,
            entry_price REAL NOT NULL,
            amount REAL NOT NULL,
            leverage INTEGER NOT NULL,
            sl_price REAL NOT NULL,
            tp_price REAL NOT NULL,
            sl_percentage REAL NOT NULL,
            tp_percentage REAL NOT NULL,
            position_size_percentage REAL NOT NULL,
            investment_amount REAL NOT NULL,
            status TEXT DEFAULT 'OPEN',
            exit_price REAL,
            exit_timestamp TEXT,
            profit_loss REAL,
            profit_loss_percentage REAL
        )
        ''')
        
        # AI 분석 결과 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            current_price REAL NOT NULL,
            direction TEXT NOT NULL,
            recommended_position_size REAL NOT NULL,
            recommended_leverage INTEGER NOT NULL,
            stop_loss_percentage REAL NOT NULL,
            take_profit_percentage REAL NOT NULL,
            reasoning TEXT NOT NULL,
            trade_id INTEGER,
            FOREIGN KEY (trade_id) REFERENCES trades (id)
        )
        ''')
        
        conn.commit()
        conn.close()
        print("Database setup completed")
    
    def save_trade(self, trade_data: Dict[str, Any]) -> int:
        """
        거래 정보를 데이터베이스에 저장
        
        Args:
            trade_data: 거래 정보 데이터
            
        Returns:
            생성된 거래 기록의 ID
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO trades (
            timestamp, action, entry_price, amount, leverage, sl_price, tp_price,
            sl_percentage, tp_percentage, position_size_percentage, investment_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            trade_data.get('action', ''),
            trade_data.get('entry_price', 0),
            trade_data.get('amount', 0),
            trade_data.get('leverage', 0),
            trade_data.get('sl_price', 0),
            trade_data.get('tp_price', 0),
            trade_data.get('sl_percentage', 0),
            trade_data.get('tp_percentage', 0),
            trade_data.get('position_size_percentage', 0),
            trade_data.get('investment_amount', 0)
        ))
        
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return trade_id
    
    def save_ai_analysis(self, analysis_data: Dict[str, Any], trade_id: Optional[int] = None) -> int:
        """
        AI 분석 결과를 데이터베이스에 저장
        
        Args:
            analysis_data: AI 분석 결과 데이터
            trade_id: 연결된 거래 ID
            
        Returns:
            생성된 분석 기록의 ID
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO ai_analysis (
            timestamp, current_price, direction, recommended_position_size,
            recommended_leverage, stop_loss_percentage, take_profit_percentage,
            reasoning, trade_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            analysis_data.get('current_price', 0),
            analysis_data.get('direction', 'NO_POSITION'),
            analysis_data.get('recommended_position_size', 0),
            analysis_data.get('recommended_leverage', 0),
            analysis_data.get('stop_loss_percentage', 0),
            analysis_data.get('take_profit_percentage', 0),
            analysis_data.get('reasoning', ''),
            trade_id
        ))
        
        analysis_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return analysis_id
    
    def update_trade_status(self, trade_id: int, status: str, exit_price: Optional[float] = None,
                           exit_timestamp: Optional[str] = None, profit_loss: Optional[float] = None,
                           profit_loss_percentage: Optional[float] = None) -> None:
        """
        거래 상태 업데이트
        
        Args:
            trade_id: 거래 ID
            status: 새 상태
            exit_price: 청산 가격
            exit_timestamp: 청산 시간
            profit_loss: 손익 금액
            profit_loss_percentage: 손익 비율
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # 동적 SQL 구성
        update_fields = ["status = ?"]
        update_values = [status]
        
        if exit_price is not None:
            update_fields.append("exit_price = ?")
            update_values.append(exit_price)
        
        if exit_timestamp is not None:
            update_fields.append("exit_timestamp = ?")
            update_values.append(exit_timestamp)
        
        if profit_loss is not None:
            update_fields.append("profit_loss = ?")
            update_values.append(profit_loss)
        
        if profit_loss_percentage is not None:
            update_fields.append("profit_loss_percentage = ?")
            update_values.append(profit_loss_percentage)
        
        update_sql = f"UPDATE trades SET {', '.join(update_fields)} WHERE id = ?"
        update_values.append(trade_id)
        
        cursor.execute(update_sql, update_values)
        conn.commit()
        conn.close()
    
    def link_analysis_to_trade(self, analysis_id: int, trade_id: int) -> None:
        """
        AI 분석과 거래를 연결
        
        Args:
            analysis_id: 분석 ID
            trade_id: 거래 ID
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute("UPDATE ai_analysis SET trade_id = ? WHERE id = ?", (trade_id, analysis_id))
        
        conn.commit()
        conn.close()
    
    def get_latest_open_trade(self) -> Optional[Dict[str, Any]]:
        """
        가장 최근의 열린 거래 정보 조회
        
        Returns:
            거래 정보 또는 None
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT id, action, entry_price, amount, leverage, sl_price, tp_price
        FROM trades
        WHERE status = 'OPEN'
        ORDER BY timestamp DESC
        LIMIT 1
        ''')
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'id': result[0],
                'action': result[1],
                'entry_price': result[2],
                'amount': result[3],
                'leverage': result[4],
                'sl_price': result[5],
                'tp_price': result[6]
            }
        return None
    
    def get_trade_summary(self, days: int = 7) -> Optional[Dict[str, Any]]:
        """
        지정된 일수 동안의 거래 요약
        
        Args:
            days: 요약할 기간(일)
            
        Returns:
            거래 요약 정보
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades,
            SUM(profit_loss) as total_profit_loss,
            AVG(profit_loss_percentage) as avg_profit_loss_percentage
        FROM trades
        WHERE exit_timestamp IS NOT NULL
        AND timestamp >= datetime('now', ?)
        ''', (f'-{days} days',))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'total_trades': result[0] or 0,
                'winning_trades': result[1] or 0,
                'losing_trades': result[2] or 0,
                'total_profit_loss': result[3] or 0,
                'avg_profit_loss_percentage': result[4] or 0
            }
        return None
    
    def get_historical_trading_data(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        과거 거래 내역과 관련 AI 분석 결과 조회
        
        Args:
            limit: 가져올 최대 거래 기록 수
            
        Returns:
            거래 및 분석 데이터 리스트
        """
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT 
            t.id as trade_id, t.timestamp as trade_timestamp, t.action,
            t.entry_price, t.exit_price, t.amount, t.leverage, t.sl_price, t.tp_price,
            t.sl_percentage, t.tp_percentage, t.position_size_percentage, t.status,
            t.profit_loss, t.profit_loss_percentage,
            a.id as analysis_id, a.reasoning, a.direction, a.recommended_leverage,
            a.recommended_position_size, a.stop_loss_percentage, a.take_profit_percentage
        FROM trades t
        LEFT JOIN ai_analysis a ON t.id = a.trade_id
        WHERE t.status = 'CLOSED'
        ORDER BY t.timestamp DESC
        LIMIT ?
        ''', (limit,))
        
        results = cursor.fetchall()
        historical_data = [dict(row) for row in results]
        
        conn.close()
        return historical_data
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        거래 성과 메트릭스 계산
        
        Returns:
            성과 메트릭스 데이터
        """
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        
        # 전체 거래 성과
        cursor.execute('''
        SELECT 
            COUNT(*) as total_trades,
            SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades,
            SUM(profit_loss) as total_profit_loss,
            AVG(profit_loss_percentage) as avg_profit_loss_percentage,
            MAX(profit_loss_percentage) as max_profit_percentage,
            MIN(profit_loss_percentage) as max_loss_percentage,
            AVG(CASE WHEN profit_loss > 0 THEN profit_loss_percentage ELSE NULL END) as avg_win_percentage,
            AVG(CASE WHEN profit_loss < 0 THEN profit_loss_percentage ELSE NULL END) as avg_loss_percentage
        FROM trades
        WHERE status = 'CLOSED'
        ''')
        
        overall_metrics = cursor.fetchone()
        
        # 방향별 성과
        cursor.execute('''
        SELECT 
            action,
            COUNT(*) as total_trades,
            SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades,
            SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades,
            SUM(profit_loss) as total_profit_loss,
            AVG(profit_loss_percentage) as avg_profit_loss_percentage
        FROM trades
        WHERE status = 'CLOSED'
        GROUP BY action
        ''')
        
        directional_metrics = cursor.fetchall()
        conn.close()
        
        # 결과 구성
        metrics = {
            "overall": {
                "total_trades": overall_metrics[0] or 0,
                "winning_trades": overall_metrics[1] or 0,
                "losing_trades": overall_metrics[2] or 0,
                "total_profit_loss": overall_metrics[3] or 0,
                "avg_profit_loss_percentage": overall_metrics[4] or 0,
                "max_profit_percentage": overall_metrics[5] or 0,
                "max_loss_percentage": overall_metrics[6] or 0,
                "avg_win_percentage": overall_metrics[7] or 0,
                "avg_loss_percentage": overall_metrics[8] or 0
            },
            "directional": {}
        }
        
        # 승률 계산
        total_trades = metrics["overall"]["total_trades"]
        if total_trades > 0:
            metrics["overall"]["win_rate"] = (metrics["overall"]["winning_trades"] / total_trades) * 100
        else:
            metrics["overall"]["win_rate"] = 0
        
        # 방향별 메트릭스
        for row in directional_metrics:
            action = row[0]
            total = row[1] or 0
            winning = row[2] or 0
            
            metrics["directional"][action] = {
                "total_trades": total,
                "winning_trades": winning,
                "losing_trades": row[3] or 0,
                "total_profit_loss": row[4] or 0,
                "avg_profit_loss_percentage": row[5] or 0,
                "win_rate": (winning / total * 100) if total > 0 else 0
            }
        
        return metrics
    
    def print_trade_summary(self, days: int = 7) -> None:
        """
        거래 요약 출력
        
        Args:
            days: 요약할 기간(일)
        """
        summary = self.get_trade_summary(days)
        if summary:
            win_rate = (summary['winning_trades'] / summary['total_trades'] * 100) if summary['total_trades'] > 0 else 0
            
            print(f"\n=== {days}-Day Trading Summary ===")
            print(f"Total Trades: {summary['total_trades']}")
            print(f"Win/Loss: {summary['winning_trades']}/{summary['losing_trades']}")
            print(f"Win Rate: {win_rate:.2f}%")
            print(f"Total P/L: ${summary['total_profit_loss']:,.2f}")
            print(f"Avg P/L %: {summary['avg_profit_loss_percentage']:.2f}%")
            print("=============================")
        else:
            print(f"No trading data found for the last {days} days")