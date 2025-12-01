<?php

namespace App\Helpers;

use App\Models\User;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\Greenhouse;

/**
 * Helper для проверки доступа пользователя к зонам, теплицам и нодам.
 * 
 * Текущая модель доступа:
 * - Админы имеют доступ ко всем зонам/теплицам/нодам
 * - Остальные роли (viewer, operator, agronomist, engineer) имеют доступ ко всем зонам
 *   (пока нет явной модели привязки пользователей к зонам через user_zones/user_greenhouses)
 * 
 * В будущем можно расширить для мульти-тенантности:
 * - Добавить таблицы user_zones и user_greenhouses
 * - Реализовать проверку через $user->zones()->where('zones.id', $zoneId)->exists()
 */
class ZoneAccessHelper
{
    /**
     * Проверяет, имеет ли пользователь доступ к зоне.
     * 
     * @param User $user
     * @param int|Zone $zone Zone ID или Zone модель
     * @return bool
     */
    public static function canAccessZone(User $user, int|Zone $zone): bool
    {
        // Админы имеют доступ ко всем зонам
        if ($user->isAdmin()) {
            return true;
        }
        
        // Получаем Zone модель, если передан ID
        $zoneModel = $zone instanceof Zone ? $zone : Zone::find($zone);
        if (!$zoneModel) {
            return false;
        }
        
        // TODO: В будущем добавить проверку через user_zones или user_greenhouses
        // Пока что для остальных ролей разрешаем доступ ко всем зонам
        // Это нужно изменить, если требуется изоляция между хозяйствами
        // 
        // Пример будущей реализации:
        // return $user->zones()->where('zones.id', $zoneModel->id)->exists()
        //     || $user->greenhouses()->where('greenhouses.id', $zoneModel->greenhouse_id)->exists();
        
        return true;
    }
    
    /**
     * Проверяет, имеет ли пользователь доступ к ноде.
     * 
     * @param User $user
     * @param int|DeviceNode $node Node ID или DeviceNode модель
     * @return bool
     */
    public static function canAccessNode(User $user, int|DeviceNode $node): bool
    {
        // Админы имеют доступ ко всем нодам
        if ($user->isAdmin()) {
            return true;
        }
        
        // Получаем DeviceNode модель, если передан ID
        $nodeModel = $node instanceof DeviceNode ? $node : DeviceNode::find($node);
        if (!$nodeModel) {
            return false;
        }
        
        // Если нода привязана к зоне, проверяем доступ через зону
        if ($nodeModel->zone_id) {
            return self::canAccessZone($user, $nodeModel->zone_id);
        }
        
        // Нода без зоны - пока разрешаем доступ всем авторизованным
        // В будущем можно добавить отдельную проверку
        return true;
    }
    
    /**
     * Проверяет, имеет ли пользователь доступ к теплице.
     * 
     * @param User $user
     * @param int|Greenhouse $greenhouse Greenhouse ID или Greenhouse модель
     * @return bool
     */
    public static function canAccessGreenhouse(User $user, int|Greenhouse $greenhouse): bool
    {
        // Админы имеют доступ ко всем теплицам
        if ($user->isAdmin()) {
            return true;
        }
        
        // Получаем Greenhouse модель, если передан ID
        $greenhouseModel = $greenhouse instanceof Greenhouse ? $greenhouse : Greenhouse::find($greenhouse);
        if (!$greenhouseModel) {
            return false;
        }
        
        // TODO: В будущем добавить проверку через user_greenhouses
        // Пока что для остальных ролей разрешаем доступ ко всем теплицам
        // 
        // Пример будущей реализации:
        // return $user->greenhouses()->where('greenhouses.id', $greenhouseModel->id)->exists();
        
        return true;
    }
    
    /**
     * Получает список ID зон, к которым пользователь имеет доступ.
     * 
     * @param User $user
     * @return array<int> Массив ID зон
     */
    public static function getAccessibleZoneIds(User $user): array
    {
        // Админы имеют доступ ко всем зонам
        if ($user->isAdmin()) {
            return Zone::pluck('id')->toArray();
        }
        
        // TODO: В будущем фильтровать по user_zones или user_greenhouses
        // Пока что возвращаем все зоны
        // 
        // Пример будущей реализации:
        // return $user->zones()->pluck('zones.id')->toArray();
        
        return Zone::pluck('id')->toArray();
    }
    
    /**
     * Получает список ID нод, к которым пользователь имеет доступ.
     * 
     * @param User $user
     * @return array<int> Массив ID нод
     */
    public static function getAccessibleNodeIds(User $user): array
    {
        // Админы имеют доступ ко всем нодам
        if ($user->isAdmin()) {
            return DeviceNode::pluck('id')->toArray();
        }
        
        // Получаем доступные зоны
        $zoneIds = self::getAccessibleZoneIds($user);
        
        // Возвращаем ноды из доступных зон
        return DeviceNode::whereIn('zone_id', $zoneIds)
            ->orWhereNull('zone_id') // Ноды без зоны пока доступны всем
            ->pluck('id')
            ->toArray();
    }
}

