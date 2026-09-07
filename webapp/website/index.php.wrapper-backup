<?php

declare(strict_types=1);

// PHP entrypoint for the public web portal.
// Keep the existing UI document intact during the migration so the Telegram
// bot/API/database behavior is not coupled to this frontend change.
header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');
header('Expires: 0');

require __DIR__ . '/index.html';
