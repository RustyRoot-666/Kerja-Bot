<?php

declare(strict_types=1);

require_once __DIR__ . '/view_loader.php';

website_render_fragment(static function (): string {
    $html = website_view_html();
    $bodyPos = stripos($html, '<body');

    if ($bodyPos === false) {
        throw new RuntimeException('KERJA-BOT: <body> marker not found.');
    }

    $bodyEnd = strpos($html, '>', $bodyPos);
    if ($bodyEnd === false) {
        throw new RuntimeException('KERJA-BOT: <body> tag is incomplete.');
    }

    return substr($html, 0, $bodyEnd + 1);
});
