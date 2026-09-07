<?php

declare(strict_types=1);

require_once __DIR__ . '/view_loader.php';

website_render_fragment(static function (): string {
    return website_view_element_by_id('dashboard');
});
