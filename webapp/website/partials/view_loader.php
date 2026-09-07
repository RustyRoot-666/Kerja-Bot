<?php

declare(strict_types=1);

/**
 * Shared legacy-view loader used during the PHP website migration.
 *
 * index.html remains the presentation source of truth for this migration
 * stage. These helpers let PHP render the existing document as independent
 * presentation sections without changing its HTML/JS contract.
 */
function website_view_html(): string
{
    static $html = null;

    if ($html !== null) {
        return $html;
    }

    $view = __DIR__ . '/../index.html';
    if (!is_file($view)) {
        throw new RuntimeException('KERJA-BOT: public view unavailable.');
    }

    $html = file_get_contents($view);
    if ($html === false) {
        throw new RuntimeException('KERJA-BOT: public view could not be read.');
    }

    return $html;
}

function website_view_fragment(string $startMarker, string $endMarker): string
{
    $html = website_view_html();
    $start = strpos($html, $startMarker);

    if ($start === false) {
        throw new RuntimeException('KERJA-BOT: view fragment start marker not found.');
    }

    $end = strpos($html, $endMarker, $start);
    if ($end === false) {
        throw new RuntimeException('KERJA-BOT: view fragment end marker not found.');
    }

    return substr($html, $start, $end - $start);
}

function website_view_element_by_id(string $id): string
{
    $html = website_view_html();
    $pattern = '/<([a-z][a-z0-9]*)\\b[^>]*\\bid=["\\\']' . preg_quote($id, '/') . '["\\\'][^>]*>/i';

    if (!preg_match($pattern, $html, $match, PREG_OFFSET_CAPTURE)) {
        throw new RuntimeException('KERJA-BOT: element #' . $id . ' not found.');
    }

    $tag = strtolower($match[1][0]);
    $start = $match[0][1];
    $cursor = $start + strlen($match[0][0]);
    $depth = 1;
    $tokenPattern = '/<\\/?' . preg_quote($tag, '/') . '\\b[^>]*>/i';

    while (preg_match($tokenPattern, $html, $token, PREG_OFFSET_CAPTURE, $cursor)) {
        $raw = $token[0][0];
        $pos = $token[0][1];
        $cursor = $pos + strlen($raw);

        if (preg_match('/^<\\//', $raw)) {
            $depth--;
        } elseif (!preg_match('/\\/\\s*>$/', $raw)) {
            $depth++;
        }

        if ($depth === 0) {
            return substr($html, $start, $cursor - $start);
        }
    }

    throw new RuntimeException('KERJA-BOT: element #' . $id . ' is not balanced.');
}

function website_render_fragment(callable $renderer): void
{
    try {
        echo $renderer();
    } catch (Throwable $e) {
        http_response_code(500);
        echo 'KERJA-BOT: presentation fragment unavailable.';
    }
}
