"""
켈리 공식 기반 포지션 사이징 유틸리티
- 확신도, SL/TP 기반 최적 포지션 계산
- 리스크 관리 및 안전장치 적용
- 레버리지 최적화
"""
import math
from typing import Dict, Any, Optional
from config import Config


class KellyCalculator:
    """켈리 공식 기반 포지션 사이징 계산기"""
    
    @staticmethod
    def calculate_position_size(
        conviction: float,
        sl_percent: float,
        tp_percent: float,
        available_balance: float,
        current_price: float,
        max_leverage: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        켈리 공식을 사용한 최적 포지션 사이징
        
        Args:
            conviction: AI 확신도 (0.0 ~ 1.0)
            sl_percent: 손절 비율 (0.0 ~ 1.0)
            tp_percent: 익절 비율 (0.0 ~ 1.0)
            available_balance: 가용 잔액 (USDT)
            current_price: 현재 BTC 가격
            max_leverage: 최대 레버리지 (None이면 config 사용)
            
        Returns:
            포지션 사이징 결과 딕셔너리
            
        Raises:
            ValueError: 잘못된 입력값
        """
        # 입력값 검증
        KellyCalculator._validate_inputs(conviction, sl_percent, tp_percent, available_balance)
        
        # 설정값 로드
        kelly_config = Config.KELLY_SETTINGS
        risk_config = Config.RISK_SETTINGS
        
        # 최소 확신도 체크
        if conviction < kelly_config["min_conviction"]:
            return KellyCalculator._no_position_result(
                f"Conviction {conviction:.2%} below minimum {kelly_config['min_conviction']:.2%}"
            )
        
        # 켈리 공식 계산
        win_loss_ratio = tp_percent / sl_percent  # b = TP/SL
        win_probability = conviction              # p
        lose_probability = 1 - conviction        # q = 1-p
        
        # 켈리 비율: f* = (p - q/b) = (p*b - q) / b
        kelly_fraction = (win_probability * win_loss_ratio - lose_probability) / win_loss_ratio
        
        # 안전 조정 (설정된 켈리 분수 적용)
        adjusted_kelly = kelly_fraction * kelly_config["kelly_fraction"]
        
        # 최대 포지션 사이즈 제한
        position_fraction = min(adjusted_kelly, kelly_config["max_position_size"])
        
        # 포지션이 너무 작거나 음수인 경우
        if position_fraction <= 0.01:  # 1% 미만
            return KellyCalculator._no_position_result(
                f"Calculated position size too small: {position_fraction:.3f}"
            )
        
        # 투자 금액 계산
        investment_amount = available_balance * position_fraction
        investment_amount = max(investment_amount, Config.MIN_INVESTMENT_AMOUNT)
        
        # 레버리지 최적화
        max_lev = max_leverage or kelly_config["max_leverage"]
        optimal_leverage = KellyCalculator._calculate_optimal_leverage(
            conviction, sl_percent, max_lev
        )
        
        # BTC 수량 계산
        btc_amount = investment_amount / current_price
        btc_amount = math.ceil(btc_amount * 1000) / 1000  # 0.001 BTC 단위로 반올림
        
        # 실제 투자 금액 재계산
        actual_investment = btc_amount * current_price
        actual_position_fraction = actual_investment / available_balance
        
        return {
            "success": True,
            "position_fraction": actual_position_fraction,
            "investment_amount": actual_investment,
            "btc_amount": btc_amount,
            "leverage": optimal_leverage,
            "kelly_details": {
                "raw_kelly": kelly_fraction,
                "adjusted_kelly": adjusted_kelly,
                "win_loss_ratio": win_loss_ratio,
                "safety_factor": kelly_config["kelly_fraction"]
            },
            "risk_metrics": {
                "max_loss_amount": actual_investment * sl_percent * optimal_leverage,
                "max_loss_percent": (actual_investment * sl_percent * optimal_leverage) / available_balance,
                "expected_gain": actual_investment * tp_percent * optimal_leverage * conviction,
                "risk_reward_ratio": tp_percent / sl_percent
            }
        }
    
    @staticmethod
    def _calculate_optimal_leverage(conviction: float, sl_percent: float, max_leverage: int) -> int:
        """
        확신도와 손절 비율에 기반한 최적 레버리지 계산
        
        Args:
            conviction: 확신도
            sl_percent: 손절 비율
            max_leverage: 최대 레버리지
            
        Returns:
            최적 레버리지
        """
        # 기본 레버리지 계산 (확신도와 역상관)
        # 높은 확신도 + 낮은 SL = 높은 레버리지
        base_leverage = min(
            math.floor(conviction * 20),  # 확신도 기반 (최대 20배)
            math.floor(0.1 / sl_percent)  # SL 기반 (10% / SL%)
        )
        
        # 안전 범위 적용
        safe_leverage = max(1, min(base_leverage, max_leverage))
        
        # 추가 안전장치: SL이 5% 이상이면 레버리지 제한
        if sl_percent >= 0.05:
            safe_leverage = min(safe_leverage, 5)
        
        return safe_leverage
    
    @staticmethod
    def _validate_inputs(conviction: float, sl_percent: float, tp_percent: float, available_balance: float) -> None:
        """입력값 검증"""
        if not (0 <= conviction <= 1):
            raise ValueError(f"Conviction must be between 0 and 1, got {conviction}")
        
        if not (0 < sl_percent < 1):
            raise ValueError(f"SL percent must be between 0 and 1, got {sl_percent}")
        
        if not (0 < tp_percent < 1):
            raise ValueError(f"TP percent must be between 0 and 1, got {tp_percent}")
        
        if available_balance <= 0:
            raise ValueError(f"Available balance must be positive, got {available_balance}")
        
        if tp_percent <= sl_percent:
            raise ValueError(f"TP ({tp_percent}) must be greater than SL ({sl_percent})")
    
    @staticmethod
    def _no_position_result(reason: str) -> Dict[str, Any]:
        """포지션 진입하지 않는 경우의 결과"""
        return {
            "success": False,
            "reason": reason,
            "position_fraction": 0.0,
            "investment_amount": 0.0,
            "btc_amount": 0.0,
            "leverage": 1
        }


class RiskManager:
    """리스크 관리 유틸리티"""
    
    @staticmethod
    def check_risk_limits(
        position_result: Dict[str, Any],
        available_balance: float,
        daily_pnl: float = 0.0
    ) -> Dict[str, Any]:
        """
        리스크 한도 체크 및 조정
        
        Args:
            position_result: 켈리 계산 결과
            available_balance: 가용 잔액
            daily_pnl: 당일 손익
            
        Returns:
            리스크 체크 결과
        """
        if not position_result["success"]:
            return position_result
        
        risk_config = Config.RISK_SETTINGS
        warnings = []
        
        # 일일 손실 한도 체크
        daily_loss_limit = available_balance * risk_config["daily_loss_limit"]
        if daily_pnl < -daily_loss_limit:
            return {
                "success": False,
                "reason": f"Daily loss limit exceeded: ${-daily_pnl:.2f} > ${daily_loss_limit:.2f}",
                "position_fraction": 0.0,
                "investment_amount": 0.0,
                "btc_amount": 0.0,
                "leverage": 1
            }
        
        # 최대 손실 금액 체크
        max_loss = position_result["risk_metrics"]["max_loss_amount"]
        remaining_daily_limit = daily_loss_limit + daily_pnl  # 남은 일일 한도
        
        if max_loss > remaining_daily_limit:
            # 포지션 사이즈 조정
            safe_investment = remaining_daily_limit / (
                position_result["risk_metrics"]["max_loss_percent"] / 
                position_result["position_fraction"]
            )
            
            adjustment_factor = safe_investment / position_result["investment_amount"]
            
            if adjustment_factor < 0.5:  # 50% 이상 줄여야 하면 포지션 포기
                return {
                    "success": False,
                    "reason": f"Required position reduction too large: {adjustment_factor:.2%}",
                    "position_fraction": 0.0,
                    "investment_amount": 0.0,
                    "btc_amount": 0.0,
                    "leverage": 1
                }
            
            # 포지션 사이즈 조정
            position_result["investment_amount"] *= adjustment_factor
            position_result["btc_amount"] *= adjustment_factor
            position_result["position_fraction"] *= adjustment_factor
            warnings.append(f"Position reduced by {(1-adjustment_factor)*100:.1f}% due to daily risk limit")
        
        # 최대 드로다운 경고
        max_drawdown = risk_config["max_drawdown_limit"]
        current_drawdown = max(0, -daily_pnl / available_balance)
        
        if current_drawdown > max_drawdown * 0.8:  # 80% 도달시 경고
            warnings.append(f"Approaching max drawdown: {current_drawdown:.2%}")
        
        position_result["warnings"] = warnings
        return position_result
    
    @staticmethod
    def calculate_sl_tp_prices(
        entry_price: float,
        direction: str,
        sl_percent: float,
        tp_percent: float
    ) -> Dict[str, float]:
        """
        진입가 기준 SL/TP 가격 계산
        
        Args:
            entry_price: 진입 가격
            direction: 'LONG' 또는 'SHORT'
            sl_percent: 손절 비율
            tp_percent: 익절 비율
            
        Returns:
            SL/TP 가격 딕셔너리
        """
        if direction.upper() == "LONG":
            sl_price = entry_price * (1 - sl_percent)
            tp_price = entry_price * (1 + tp_percent)
        else:  # SHORT
            sl_price = entry_price * (1 + sl_percent)
            tp_price = entry_price * (1 - tp_percent)
        
        return {
            "sl_price": round(sl_price, 2),
            "tp_price": round(tp_price, 2),
            "sl_distance": abs(entry_price - sl_price),
            "tp_distance": abs(tp_price - entry_price),
            "risk_reward_ratio": tp_percent / sl_percent
        }


# 편의 함수들
def calculate_kelly_position(
    conviction: float,
    sl_percent: float,
    tp_percent: float,
    available_balance: float,
    current_price: float,
    daily_pnl: float = 0.0,
    max_leverage: Optional[int] = None
) -> Dict[str, Any]:
    """
    켈리 공식 포지션 계산 원스톱 함수
    
    Args:
        conviction: AI 확신도 (0.0 ~ 1.0)
        sl_percent: 손절 비율
        tp_percent: 익절 비율
        available_balance: 가용 잔액
        current_price: 현재 가격
        daily_pnl: 당일 손익
        max_leverage: 최대 레버리지
        
    Returns:
        최종 포지션 사이징 결과
    """
    if not Config.USE_KELLY_CRITERION:
        # 켈리 공식 미사용시 고정 비율 사용
        fixed_fraction = 0.1  # 10% 고정
        investment = min(
            available_balance * fixed_fraction,
            available_balance * Config.KELLY_SETTINGS["max_position_size"]
        )
        
        return {
            "success": True,
            "position_fraction": investment / available_balance,
            "investment_amount": investment,
            "btc_amount": investment / current_price,
            "leverage": 3,  # 고정 레버리지
            "kelly_details": {"method": "fixed_fraction"},
            "risk_metrics": {
                "max_loss_amount": investment * sl_percent * 3,
                "risk_reward_ratio": tp_percent / sl_percent
            }
        }
    
    # 켈리 계산
    position_result = KellyCalculator.calculate_position_size(
        conviction, sl_percent, tp_percent, available_balance, current_price, max_leverage
    )
    
    # 리스크 체크 및 조정
    return RiskManager.check_risk_limits(position_result, available_balance, daily_pnl)


def get_sl_tp_prices(entry_price: float, direction: str, sl_percent: float, tp_percent: float) -> Dict[str, float]:
    """SL/TP 가격 계산 편의 함수"""
    return RiskManager.calculate_sl_tp_prices(entry_price, direction, sl_percent, tp_percent)