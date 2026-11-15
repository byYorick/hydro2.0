<?php

use App\Support\Database\RuntimeRoleGrants;
use Illuminate\Database\Migrations\Migration;

return new class extends Migration
{
    public function up(): void
    {
        RuntimeRoleGrants::apply();
    }

    public function down(): void
    {
        RuntimeRoleGrants::revoke();
    }
};
