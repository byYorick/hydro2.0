# Эталон: iarduino_I2C_pH v1.2.3

Здесь лежит **исходная** Arduino-библиотека Trema pH (I²C Flash), по которой портирован драйвер `trema_ph` в ESP-IDF.

- **Архив тега 1.2.3:** https://github.com/tremaru/iarduino_I2C_pH/archive/refs/tags/1.2.3.zip  
- **Распакованные исходники:** каталог `iarduino_I2C_pH-1.2.3/`  
- **Описание регистров и API:** https://wiki.iarduino.ru/page/ph-i2c/

Рабочая реализация для проекта — `../trema_ph.c` и `../include/trema_ph.h` (FreeRTOS, `i2c_bus`, mutex, опциональная очередь снимков).
