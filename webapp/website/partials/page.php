<?php

declare(strict_types=1);

/**
 * KERJA-BOT FIELD COMMAND
 *
 * PHP presentation orchestrator. The existing index.html remains the
 * presentation source of truth during this migration stage, while PHP
 * renders it through isolated sections.
 *
 * API routes, Telegram handlers and database logic stay outside this layer.
 */

require_once __DIR__ . '/view_loader.php';

require __DIR__ . '/head.php';
echo "\n";
require __DIR__ . '/auth.php';
echo "\n";
require __DIR__ . '/dashboard.php';
echo "\n";
require __DIR__ . '/footer.php';
