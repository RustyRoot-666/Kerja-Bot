<?php

declare(strict_types=1);

/**
 * KERJA-BOT FIELD COMMAND
 *
 * Presentation layer for the public portal.
 * The existing HTML document is intentionally rendered through this PHP
 * partial so the PHP migration does not alter the UI or JavaScript contract.
 *
 * Keep API routes, Telegram handlers, and database logic outside this layer.
 */

$view = __DIR__ . '/../index.html';

if (!is_file($view)) {
    http_response_code(500);
    echo 'KERJA-BOT: public view unavailable.';
    return;
}

readfile($view);
