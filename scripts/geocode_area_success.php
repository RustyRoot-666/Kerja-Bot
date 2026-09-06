<?php

declare(strict_types=1);

require_once __DIR__ . '/../webapp/php_backend.php';
require_once __DIR__ . '/../webapp/php_area_success.php';

$limit = 0;
foreach ($argv as $arg) {
    if (str_starts_with($arg, '--limit=')) $limit = max(0, (int)substr($arg, 8));
}

$rows = fetch_sheet(false);
$areas = [];
foreach ($rows as $row) {
    $address = trim((string)($row['address'] ?? ''));
    if ($address === '') continue;
    $area = area_success_locality($address);
    if ($area === '' || $area === 'LAINNYA') continue;
    $areas[$area] = true;
}
ksort($areas);

$pdo = db();
$pdo->exec("CREATE TABLE IF NOT EXISTS area_success_geocodes (
    area_key TEXT PRIMARY KEY,
    area_name TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'failed',
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
)");

function geocode_area_request(string $area): ?array {
    $query = $area . ', Surabaya, Jawa Timur, Indonesia';
    $url = 'https://nominatim.openstreetmap.org/search?' . http_build_query([
        'q'=>$query,'format'=>'jsonv2','limit'=>1,'countrycodes'=>'id'
    ]);
    $ctx = stream_context_create(['http'=>[
        'timeout'=>15,
        'header'=>"User-Agent: Kerja-Bot/1.0 (area-success-map)\r\nAccept: application/json\r\n"
    ]]);
    $raw = @file_get_contents($url, false, $ctx);
    if ($raw === false) return null;
    $items = json_decode($raw, true);
    if (!is_array($items) || empty($items[0]['lat']) || empty($items[0]['lon'])) return null;
    return [
        'latitude'=>(float)$items[0]['lat'],
        'longitude'=>(float)$items[0]['lon'],
        'display_name'=>(string)($items[0]['display_name'] ?? $area)
    ];
}

$total = count($areas); $checked=0; $done=0; $cached=0; $failed=0;
echo "AREA SUCCESS GEOCODER\n";
echo "Unique customer areas: {$total}\n";
echo "One Nominatim request per area; no customer-street geocoding.\n";

foreach (array_keys($areas) as $area) {
    if ($limit > 0 && $checked >= $limit) break;
    $checked++;
    $key = strtolower($area);
    $st = $pdo->prepare('SELECT status,latitude,longitude FROM area_success_geocodes WHERE area_key=? LIMIT 1');
    $st->execute([$key]);
    $existing = $st->fetch();
    if ($existing && $existing['status'] === 'ok' && $existing['latitude'] !== null && $existing['longitude'] !== null) {
        $cached++;
        continue;
    }

    $geo = geocode_area_request($area);
    $now = date('Y-m-d H:i:s');
    if ($geo) {
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,'ok',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$area,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
        $done++;
        echo "OK {$checked}/{$total} {$area} -> {$geo['latitude']},{$geo['longitude']}\n";
    } else {
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,status,attempts,updated_at) VALUES(?,?, 'failed',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,status='failed',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$area,$now]);
        $failed++;
        echo "FAIL {$checked}/{$total} {$area}\n";
    }
    usleep(1100000);
}

echo "DONE checked={$checked} geocoded={$done} cached={$cached} failed={$failed}\n";
