<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;

class GenerateServiceToken extends Command
{
    protected $signature = 'token:generate {--name=python-service}';
    protected $description = 'Generate API token for Python services';

    public function handle()
    {
        $user = User::first();
        
        if (!$user) {
            $this->error('No users found. Please create a user first.');
            return 1;
        }

        $tokenName = $this->option('name');
        $token = $user->createToken($tokenName)->plainTextToken;
        
        $this->info('Token generated successfully:');
        $this->line($token);
        $this->newLine();
        $this->info('Set this token as LARAVEL_API_TOKEN environment variable in docker-compose.dev.yml');
        
        return 0;
    }
}

