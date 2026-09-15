<?php
declare(strict_types=1);

function whatsapp_normalize_phone(mixed $phone): string {
    $value = preg_replace('/[^0-9]/', '', (string)$phone) ?: '';
    if (str_starts_with($value, '0')) $value = '62' . substr($value, 1);
    return $value;
}

function whatsapp_check_phone(string $phone, bool $cachedOnly = false): array {
    $phone = whatsapp_normalize_phone($phone);
    if ($phone === '' || $phone === '62' || strlen($phone) < 8) {
        return ['ok'=>false,'error'=>'invalid_phone','phone_number'=>$phone];
    }

    db()->exec("CREATE TABLE IF NOT EXISTS whatsapp_checks (
        phone_number TEXT PRIMARY KEY,
        exists_whatsapp INTEGER NOT NULL CHECK(exists_whatsapp IN (0,1)),
        checked_at TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'green-api'
    )");

    $st = db()->prepare('SELECT phone_number,exists_whatsapp,checked_at,source FROM whatsapp_checks WHERE phone_number=?');
    $st->execute([$phone]);
    $cached = $st->fetch();
    if ($cached) {
        return [
            'ok'=>true,
            'phone_number'=>$phone,
            'exists_whatsapp'=>(bool)$cached['exists_whatsapp'],
            'checked_at'=>$cached['checked_at'],
            'cached'=>true
        ];
    }

    if ($cachedOnly) {
        return [
            'ok'=>true,
            'phone_number'=>$phone,
            'exists_whatsapp'=>null,
            'checked_at'=>null,
            'cached'=>false,
            'not_checked'=>true
        ];
    }

    $base = rtrim((string)(getenv('GREEN_API_URL') ?: ''), '/');
    $instance = trim((string)(getenv('GREEN_API_INSTANCE') ?: ''));
    $token = trim((string)(getenv('GREEN_API_TOKEN') ?: ''));
    if ($base === '' || $instance === '' || $token === '') {
        return ['ok'=>false,'error'=>'green_api_not_configured'];
    }

    $url = $base . '/waInstance' . rawurlencode($instance) . '/checkWhatsapp/' . rawurlencode($token);
    $payload = json_encode(['phoneNumber'=>(int)$phone], JSON_UNESCAPED_SLASHES);
    $ctx = stream_context_create(['http'=>[
        'method'=>'POST',
        'header'=>"Content-Type: application/json\r\nUser-Agent: Kerja-Bot-MiniApp/1.0\r\n",
        'content'=>$payload,
        'timeout'=>20,
        'ignore_errors'=>true
    ]]);
    $raw = @file_get_contents($url, false, $ctx);
    $status = 0;
    foreach (($http_response_header ?? []) as $header) {
        if (preg_match('/^HTTP\/\S+\s+(\d+)/', $header, $m)) { $status=(int)$m[1]; break; }
    }

    if ($raw === false || $status < 200 || $status >= 300) {
        return ['ok'=>false,'error'=>'green_api_request_failed','message'=>$status ? ('HTTP ' . $status) : 'HTTP request failed'];
    }

    $payload = json_decode((string)$raw, true);
    if (!is_array($payload) || !array_key_exists('existsWhatsapp', $payload)) {
        return ['ok'=>false,'error'=>'green_api_invalid_response'];
    }

    $exists = (bool)$payload['existsWhatsapp'];
    $checkedAt = gmdate('Y-m-d\TH:i:s\Z');
    $st = db()->prepare('INSERT OR IGNORE INTO whatsapp_checks(phone_number,exists_whatsapp,checked_at,source) VALUES(?,?,?,?)');
    $st->execute([$phone,(int)$exists,$checkedAt,'green-api']);

    return [
        'ok'=>true,
        'phone_number'=>$phone,
        'exists_whatsapp'=>$exists,
        'checked_at'=>$checkedAt,
        'cached'=>false
    ];
}
