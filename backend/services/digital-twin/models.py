"""
Модели для симуляции параметров зоны.
"""
from typing import Tuple


class PHModel:
    """
    Модель pH: учитывает буферную ёмкость, влияние дозировок, естественный дрифт.
    """
    
    def __init__(self):
        # Параметры модели (можно калибровать по историческим данным)
        self.buffer_capacity = 0.1  # буферная ёмкость раствора
        self.natural_drift = 0.01  # естественное смещение pH в час
        self.correction_rate = 0.05  # скорость коррекции при дозировке
        
    def step(self, current_ph: float, target_ph: float, elapsed_hours: float) -> float:
        """
        Один шаг симуляции pH.
        
        Args:
            current_ph: текущее значение pH
            target_ph: целевое значение pH
            elapsed_hours: время в часах с начала фазы
        """
        # Естественный дрифт
        drift = self.natural_drift * elapsed_hours
        
        # Коррекция к target (упрощенная модель)
        diff = target_ph - current_ph
        if abs(diff) > 0.1:  # если отклонение значительное
            correction = diff * self.correction_rate * elapsed_hours
            # Ограничиваем скорость изменения
            correction = max(-0.2, min(0.2, correction))
        else:
            correction = 0
        
        new_ph = current_ph + drift + correction
        
        # Ограничиваем диапазон pH
        return max(4.0, min(9.0, new_ph))


class ECModel:
    """
    Модель EC: учитывает концентрацию солей, дозировку, испарение/долив.
    """
    
    def __init__(self):
        self.evaporation_rate = 0.02  # испарение в час (%)
        self.dilution_rate = 0.01  # разбавление при доливе чистой воды
        self.nutrient_addition_rate = 0.03  # скорость добавления питательных веществ
        
    def step(self, current_ec: float, target_ec: float, elapsed_hours: float) -> float:
        """
        Один шаг симуляции EC.
        
        Args:
            current_ec: текущее значение EC
            target_ec: целевое значение EC
            elapsed_hours: время в часах с начала фазы
        """
        # Испарение увеличивает EC (концентрация растет)
        evaporation_effect = current_ec * self.evaporation_rate * elapsed_hours
        
        # Коррекция к target
        diff = target_ec - current_ec
        if abs(diff) > 0.1:
            if diff > 0:
                # Добавление питательных веществ
                correction = diff * self.nutrient_addition_rate * elapsed_hours
            else:
                # Разбавление
                correction = diff * self.dilution_rate * elapsed_hours
            correction = max(-0.3, min(0.3, correction))
        else:
            correction = 0
        
        new_ec = current_ec + evaporation_effect + correction
        
        # Ограничиваем диапазон EC
        return max(0.1, min(5.0, new_ec))


class ClimateModel:
    """
    Модель климата: баланс тепла и влаги, влияние вентиляции.
    """
    
    def __init__(self):
        self.heat_loss_rate = 0.5  # потери тепла в час (°C)
        self.humidity_decay_rate = 0.02  # снижение влажности в час (%)
        self.ventilation_cooling = 1.0  # охлаждение при вентиляции (°C/час)
        
    def step(
        self,
        current_temp: float,
        current_humidity: float,
        target_temp: float,
        target_humidity: float,
        elapsed_hours: float
    ) -> Tuple[float, float]:
        """
        Один шаг симуляции климата.
        
        Args:
            current_temp: текущая температура воздуха
            current_humidity: текущая влажность воздуха
            target_temp: целевая температура
            target_humidity: целевая влажность
            elapsed_hours: время в часах с начала фазы
        """
        # Температура
        temp_diff = target_temp - current_temp
        if abs(temp_diff) > 1.0:
            # Нагрев или охлаждение
            temp_change = temp_diff * 0.1 * elapsed_hours
            # Потери тепла
            heat_loss = self.heat_loss_rate * elapsed_hours
            new_temp = current_temp + temp_change - heat_loss
        else:
            # Только потери тепла
            new_temp = current_temp - self.heat_loss_rate * elapsed_hours
        
        # Влажность
        humidity_diff = target_humidity - current_humidity
        if abs(humidity_diff) > 5.0:
            humidity_change = humidity_diff * 0.05 * elapsed_hours
        else:
            humidity_change = 0
        
        # Естественное снижение влажности
        humidity_decay = current_humidity * self.humidity_decay_rate * elapsed_hours
        
        new_humidity = current_humidity + humidity_change - humidity_decay
        
        # Ограничиваем диапазоны
        new_temp = max(10.0, min(35.0, new_temp))
        new_humidity = max(20.0, min(95.0, new_humidity))
        
        return new_temp, new_humidity

