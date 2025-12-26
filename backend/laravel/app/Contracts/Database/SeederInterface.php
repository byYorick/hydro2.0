<?php

namespace App\Contracts\Database;

/**
 * Интерфейс для всех сидеров системы
 */
interface SeederInterface
{
    /**
     * Выполнить сидирование данных
     */
    public function run(): void;

    /**
     * Проверить, что все зависимости выполнены
     */
    public function validateDependencies(): bool;

    /**
     * Получить список зависимостей сидера
     */
    public function getDependencies(): array;

    /**
     * Очистить данные, созданные этим сидером
     */
    public function cleanup(): void;

    /**
     * Получить имя сидера для логов
     */
    public function getSeederName(): string;
}
