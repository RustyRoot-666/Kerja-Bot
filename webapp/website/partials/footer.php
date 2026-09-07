<?php

declare(strict_types=1);

require_once __DIR__ . '/view_loader.php';

website_render_fragment(static function (): string {
    $html = website_view_html();
    $marker = '</section></main>';
    $pos = strrpos($html, $marker);

    if ($pos === false) {
        throw new RuntimeException('KERJA-BOT: website footer marker not found.');
    }

    return substr($html, $pos + strlen($marker));
});
