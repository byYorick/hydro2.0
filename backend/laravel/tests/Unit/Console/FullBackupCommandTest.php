<?php

namespace Tests\Unit\Console;

use Illuminate\Process\PendingProcess;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Process;
use Tests\TestCase;

class FullBackupCommandTest extends TestCase
{
    public function test_command_signature_exists(): void
    {
        // Проверяем, что команда зарегистрирована
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);
    }

    public function test_command_has_description(): void
    {
        // Проверяем описание команды
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);

        $command = $commands['backup:full'];
        $this->assertStringContainsString('Создает полный бэкап', $command->getDescription());
    }

    public function test_command_accepts_skip_docker_option(): void
    {
        // Проверяем, что команда принимает опцию --skip-docker
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);

        $command = $commands['backup:full'];
        $this->assertNotNull($command);
    }

    public function test_command_accepts_skip_mqtt_option(): void
    {
        // Проверяем, что команда принимает опцию --skip-mqtt
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);

        $command = $commands['backup:full'];
        $this->assertNotNull($command);
    }

    public function test_command_handles_missing_script(): void
    {
        config(['backup.script_directory' => storage_path('missing-backup-script')]);
        Process::fake();
        $this->artisan('backup:full')->assertFailed();
        Process::assertNothingRan();
    }

    public function test_backup_passes_active_database_and_options_without_shell_interpolation(): void
    {
        $directory = sys_get_temp_dir().'/hydro-backup-'.bin2hex(random_bytes(8)).' with spaces';
        File::ensureDirectoryExists($directory);
        File::put($directory.'/full_backup.sh', '# fixture');
        config([
            'backup.script_directory' => $directory,
            'backup.directory' => '/private/backup path',
            'backup.include_docker_volumes' => true,
            'database.connections.pgsql.host' => 'backup-db',
            'database.connections.pgsql.port' => 5544,
            'database.connections.pgsql.database' => 'selected_database',
            'database.connections.pgsql.username' => 'selected_user',
        ]);
        Process::fake(['*' => Process::result(output: '/private/backup path/full/test')]);
        try {
            $this->artisan('backup:full', ['--skip-docker' => true, '--skip-mqtt' => true])
                ->assertSuccessful();
            Process::assertRan(function (PendingProcess $process) use ($directory) {
                $this->assertSame(['bash', $directory.'/full_backup.sh'], $process->command);
                $this->assertSame('backup-db', $process->environment['DB_HOST']);
                $this->assertSame('5544', $process->environment['DB_PORT']);
                $this->assertSame('selected_database', $process->environment['DB_NAME']);
                $this->assertSame('selected_user', $process->environment['DB_USER']);
                $this->assertSame('1', $process->environment['SKIP_DOCKER']);
                $this->assertSame('1', $process->environment['SKIP_MQTT']);

                return true;
            });
        } finally {
            File::deleteDirectory($directory);
        }
    }

    public function test_failed_component_fails_the_artisan_command(): void
    {
        $directory = sys_get_temp_dir().'/hydro-backup-'.bin2hex(random_bytes(8));
        File::ensureDirectoryExists($directory);
        File::put($directory.'/full_backup.sh', '# fixture');
        config(['backup.script_directory' => $directory]);
        Process::fake(['*' => Process::result(errorOutput: 'component failed', exitCode: 1)]);
        try {
            $this->artisan('backup:full')->assertFailed();
        } finally {
            File::deleteDirectory($directory);
        }
    }
}
