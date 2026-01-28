<?php

namespace Tests\Unit;

use App\Enums\MetricType;
use Tests\TestCase;

class MetricTypeTest extends TestCase
{
    public function test_metric_type_values(): void
    {
        $values = MetricType::values();

        $this->assertContains('PH', $values);
        $this->assertContains('EC', $values);
        $this->assertContains('TEMPERATURE', $values);
        $this->assertContains('HUMIDITY', $values);
        $this->assertContains('CO2', $values);
        $this->assertContains('LIGHT_INTENSITY', $values);
        $this->assertContains('WATER_LEVEL', $values);
        $this->assertContains('FLOW_RATE', $values);
        $this->assertContains('PUMP_CURRENT', $values);
    }

    public function test_metric_type_is_valid(): void
    {
        $this->assertTrue(MetricType::isValid('ph'));
        $this->assertTrue(MetricType::isValid('PH'));
        $this->assertTrue(MetricType::isValid('  PH  '));
        $this->assertTrue(MetricType::isValid('temperature'));
        $this->assertTrue(MetricType::isValid('TEMPERATURE'));

        $this->assertFalse(MetricType::isValid('unknown'));
        $this->assertFalse(MetricType::isValid(''));
        $this->assertFalse(MetricType::isValid('ph_invalid'));
    }

    public function test_metric_type_normalize(): void
    {
        $this->assertEquals('PH', MetricType::normalize('ph'));
        $this->assertEquals('PH', MetricType::normalize('PH'));
        $this->assertEquals('PH', MetricType::normalize('  PH  '));
        $this->assertEquals('TEMPERATURE', MetricType::normalize('TEMPERATURE'));
        $this->assertEquals('TEMPERATURE', MetricType::normalize('  temperature  '));

        $this->assertNull(MetricType::normalize('unknown'));
        $this->assertNull(MetricType::normalize(''));
    }

    public function test_metric_type_cases(): void
    {
        $this->assertEquals('PH', MetricType::PH->value);
        $this->assertEquals('EC', MetricType::EC->value);
        $this->assertEquals('TEMPERATURE', MetricType::TEMPERATURE->value);
        $this->assertEquals('HUMIDITY', MetricType::HUMIDITY->value);
        $this->assertEquals('CO2', MetricType::CO2->value);
        $this->assertEquals('LIGHT_INTENSITY', MetricType::LIGHT_INTENSITY->value);
        $this->assertEquals('WATER_LEVEL', MetricType::WATER_LEVEL->value);
        $this->assertEquals('FLOW_RATE', MetricType::FLOW_RATE->value);
        $this->assertEquals('PUMP_CURRENT', MetricType::PUMP_CURRENT->value);
    }
}
