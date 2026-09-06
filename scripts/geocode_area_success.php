<?php

declare(strict_types=1);

// Load the backend first because the area/customer helpers depend on db().
require_once __DIR__ . '/../webapp/php_backend.php';
require_once __DIR__ . '/../webapp/php_area_success.php';
require_once __DIR__ . '/../webapp/php_customer_zones.php';

$limit = 0;
foreach ($argv as $arg) {
    if (str_starts_with($arg, '--limit=')) $limit = max(0, (int)substr($arg, 8));
}

customer_zone_ensure_schema();
$rows = fetch_sheet(false);
$streets = [];
foreach ($rows as $row) {
    $address = trim((string)($row['address'] ?? ''));
    if ($address === '') continue;
    $street = customer_zone_normalize_street($address);
    if ($street === '') continue;
    $key = customer_zone_key($street);
    if ($key !== '') $streets[$key] = $street;
}
ksort($streets);

$pdo = db();
$done = 0; $skipped = 0; $failed = 0; $checked = 0;
$total = count($streets);

echo "AREA SUCCESS GEOCODER\n";
echo "Unique customer streets: {$total}\n";
echo "Cached results are reused; uncached requests are single-threaded at ~1 req/sec.\n";

foreach ($streets as $key => $street) {
    if ($limit > 0 && $checked >= $limit) break;
    $checked++;

    $st = $pdo->prepare('SELECT status FROM customer_geocodes WHERE address_key=? LIMIT 1');
    $st->execute([$key]);
    $status = (string)($st->fetchColumn() ?: '');
    if ($status === 'ok') {
        $skipped++;
        continue;
    }

    $geo = customer_zone_geocode($street);
    $now = date('Y-m-d H:i:s');
    if ($geo) {
        $pdo->prepare("INSERT INTO customer_geocodes(address_key,address,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,'ok',1,?) ON CONFLICT(address_key) DO UPDATE SET address=excluded.address,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$street,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
        $done++;
        echo "OK {$checked}/{$total} {$street}\n";
    } else {
        $pdo->prepare("INSERT INTO customer_geocodes(address_key,address,status,attempts,updated_at) VALUES(?,?, 'failed',1,?) ON CONFLICT(address_key) DO UPDATE SET address=excluded.address,status='failed',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$street,$now]);
        $failed++;
        echo "FAIL {$checked}/{$total} {$street}\n";
    }
    usleep(1100000);
}

echo "DONE checked={$checked} geocoded={$done} cached={$skipped} failed={$failed}\n";
