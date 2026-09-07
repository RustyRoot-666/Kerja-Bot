<?php

declare(strict_types=1);

/**
 * KERJA-BOT FIELD COMMAND
 * Public website PHP entrypoint.
 *
 * The presentation layer is kept separate from the router/API layer.
 * This entrypoint owns HTTP headers only; the actual public view lives in
 * website/partials/page.php. Bot, Telegram handlers, database and API logic
 * remain untouched.
 */

header('Content-Type: text/html; charset=utf-8');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');
header('Expires: 0');

require __DIR__ . '/partials/page.php';
