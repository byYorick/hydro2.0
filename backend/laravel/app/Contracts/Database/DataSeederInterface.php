<?php

namespace App\Contracts\Database;

/**
 * Интерфейс для сидеров данных (телеметрия, команды, алерты и т.д.)
 * Такие сидеры могут требовать большого количества данных и времени
 */
interface DataSeederInterface extends SeederInterface
{
    /**
     * Получить примерное количество создаваемых записей
     */
    public function getEstimatedRecordCount(): int;

    /**
     * Поддерживает ли сидер частичное выполнение
     */
    public function supportsPartialExecution(): bool;

    /**
     * Выполнить частичное сидирование (например, за определенный период)
     */
    public function runPartial(\DateTime $startDate, \DateTime $endDate): void;

    /**
     * Получить текущий прогресс выполнения
     */
    public function getProgress(): array;
}
