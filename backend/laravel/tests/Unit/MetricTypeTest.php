<?php

namespace Tests\Unit;

use App\Enums\MetricType;
use Tests\TestCase;

class MetricTypeTest extends TestCase
{
    public function test_metric_type_values(): void
    {
        $values = MetricType::values();
        
        $this->assertContains('ph', $values);
        $this->assertContains('ec', $values);
        $this->assertContains('temp_air', $values);
        $this->assertContains('temp_water', $values);
        $this->assertContains('humidity', $values);
        $this->assertContains('co2', $values);
        $this->assertContains('lux', $values);
        $this->assertContains('water_level', $values);
        $this->assertContains('flow_rate', $values);
        $this->assertContains('pump_current', $values);
    }

    public function test_metric_type_is_valid(): void
    {
        $this->assertTrue(MetricType::isValid('ph'));
        $this->assertTrue(MetricType::isValid('PH'));
        $this->assertTrue(MetricType::isValid('  PH  '));
        $this->assertTrue(MetricType::isValid('temp_air'));
        $this->assertTrue(MetricType::isValid('TEMP_AIR'));
        
        $this->assertFalse(MetricType::isValid('unknown'));
        $this->assertFalse(MetricType::isValid(''));
        $this->assertFalse(MetricType::isValid('ph_invalid'));
    }

    public function test_metric_type_normalize(): void
    {
        $this->assertEquals('ph', MetricType::normalize('ph'));
        $this->assertEquals('ph', MetricType::normalize('PH'));
        $this->assertEquals('ph', MetricType::normalize('  PH  '));
        $this->assertEquals('temp_air', MetricType::normalize('TEMP_AIR'));
        $this->assertEquals('temp_air', MetricType::normalize('  temp_air  '));
        
        $this->assertNull(MetricType::normalize('unknown'));
        $this->assertNull(MetricType::normalize(''));
    }

    public function test_metric_type_cases(): void
    {
        $this->assertEquals('ph', MetricType::PH->value);
        $this->assertEquals('ec', MetricType::EC->value);
        $this->assertEquals('temp_air', MetricType::TEMP_AIR->value);
        $this->assertEquals('temp_water', MetricType::TEMP_WATER->value);
        $this->assertEquals('humidity', MetricType::HUMIDITY->value);
        $this->assertEquals('co2', MetricType::CO2->value);
        $this->assertEquals('lux', MetricType::LUX->value);
        $this->assertEquals('water_level', MetricType::WATER_LEVEL->value);
        $this->assertEquals('flow_rate', MetricType::FLOW_RATE->value);
        $this->assertEquals('pump_current', MetricType::PUMP_CURRENT->value);
    }
}

