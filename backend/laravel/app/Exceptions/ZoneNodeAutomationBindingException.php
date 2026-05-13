<?php

namespace App\Exceptions;

/**
 * Конфликт при UI-привязке узла к зоне (дубли pH/EC или ролей полива/коррекции).
 */
class ZoneNodeAutomationBindingException extends \DomainException {}
