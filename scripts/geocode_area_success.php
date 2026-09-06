<?php

declare(strict_types=1);

require_once __DIR__ . '/../webapp/php_backend.php';
require_once __DIR__ . '/../webapp/php_area_success.php';
require_once __DIR__ . '/../webapp/php_customer_zones.php';

function area_success_geocode_query(string $address): string {
    $text = strtoupper(trim($address));
    $text = preg_replace('/\s+/u', ' ', $text) ?: '';
    if ($text === '') return '';

    // Apartments/complexes: remove unit/house identifiers so the geocoder
    // resolves the building/complex itself. Example:
    // APARTEMEN BALE HINGGIL B1527 -> APARTEMEN BALE HINGGIL
    if (preg_match('/^APARTEMEN(?:T)?\s+(.+)$/u', $text, $m)) {
        $name = trim($m[1]);
        $name = preg_replace('/\s+(?:UNIT|NO|NOMOR)\s*[-A-Z0-9\/]+.*$/u', '', $name) ?: $name;
        $name = preg_replace('/\s+[A-Z]?\d+(?:[-\/]\d+)?$/u', '', $name) ?: $name;
        $name = preg_replace('/\s+[A-Z]\d+(?:[-\/]\d+)?$/u', '', $name) ?: $name;
        return 'APARTEMEN ' . trim($name) . ', Surabaya, Jawa Timur, Indonesia';
    }

    return $text . ', Surabaya, Jawa Timur, Indonesia';
}

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
    if ($key === '') continue;

    if (!isset($streets[$key])) {
        $streets[$key] = ['street' => $street, 'query' => area_success_geocode_query($address)];
    }
}
ksort($streets);

$pdo = db();
$done = 0; $skipped = 0; $failed = 0; $checked = 0;
$total = count($streets);

echo "AREA SUCCESS GEOCODER\n";
echo "Unique customer streets: {$total}\n";
echo "Cached results are reused; uncached requests are single-threaded at ~1 req/sec.\n";

foreach ($streets as $key => $item) {
    if ($limit > 0 && $checked >= $limit) break;
    $checked++;

    $street = $item['street'];
    $query = $item['query'];

    $st = $pdo->prepare('SELECT status FROM customer_geocodes WHERE address_key=? LIMIT 1');
    $st->execute([$key]);
    $status = (string)($st->fetchColumn() ?: '');
    if ($status === 'ok') {
        $skipped++;
        continue;
    }

    $geo = customer_zone_geocode($query);
    if (!$geo && $street !== $query) {
        usleep(1100000);
        $geo = customer_zone_geocode($street . ', Surabaya, Jawa Timur, Indonesia');
    }

    $now = date('Y-m-d H:i:s');
    if ($geo) {
        $pdo->prepare("INSERT INTO customer_geocodes(address_key,address,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,'ok',1,?) ON CONFLICT(address_key) DO UPDATE SET address=excluded.address,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$street,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
        $done++;
        echo "OK {$checked}/{$total} {$street} <- {$query}\n";
    } else {
        $pdo->prepare("INSERT INTO customer_geocodes(address_key,address,status,attempts,updated_at) VALUES(?,?, 'failed',1,?) ON CONFLICT(address_key) DO UPDATE SET address=excluded.address,status='failed',attempts=customer_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$street,$now]);
        $failed++;
        echo "FAIL {$checked}/{$total} {$street} <- {$query}\n";
    }
    usleep(1100000);
}

echo "DONE checked={$checked} geocoded={$done} cached={$skipped} failed={$failed}\n";
