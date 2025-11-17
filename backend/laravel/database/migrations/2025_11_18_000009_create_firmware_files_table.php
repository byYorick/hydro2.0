<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('firmware_files', function (Blueprint $table) {
            $table->id();
            $table->string('node_type'); // ph, ec, climate, irrig, light
            $table->string('version');
            $table->string('file_path');
            $table->string('checksum_sha256');
            $table->text('release_notes')->nullable();
            $table->timestamp('created_at')->useCurrent();

            $table->index(['node_type', 'version'], 'firmware_files_node_type_version_idx');
            $table->index('checksum_sha256', 'firmware_files_checksum_idx');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('firmware_files');
    }
};

