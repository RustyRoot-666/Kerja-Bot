<?php

declare(strict_types=1);

require_once __DIR__ . '/../webapp/php_backend.php';
require_once __DIR__ . '/../webapp/php_area_success.php';

$limit = 0;
foreach ($argv as $arg) {
    if (str_starts_with($arg, '--limit=')) $limit = max(0, (int)substr($arg, 8));
}

function area_success_kecamatan(string $address): string {
    $s = area_success_normalize($address);
    if ($s === '') return '';

    // Surabaya customer addresses commonly contain the kecamatan as the
    // locality token after the street/area. Keep it as geocoding context only;
    // it must never become the map's success grouping key.
    $known = [
        'ASEMROWO','BENOWO','BUBUTAN','BULAK','DUKUH PAKIS','GAYUNGAN',
        'GENTENG','GUBENG','GUNUNG ANYAR','JAMBANGAN','KARANG PILANG',
        'KENJERAN','KREMBANGAN','LAKARSANTRI','MULYOREJO','PABEAN CANTIAN',
        'PAKAL','RUNGKUT','SAMBIKEREP','SAWAHAN','SEMAMPIR','SIMOKERTO',
        'SIMOKERTO','SIMOKERTO','SIMOMULYA','SUKOLILO','SUKOMANUNGGAL',
        'TAMBAKSARI','TANDES','TEGALSARI','TENGGILIS MEJOYO','WIYUNG',
        'WONOCOLO','WONOKROMO','MOJO','KEPUTIH','NGINDEN','PUMPUNGAN',
        'MANYAR','MENUR','SEMOLOWARU','KERTAJAYA','AIRLANGGA'
    ];

    // Prefer the longest names first so multi-word kecamatan are matched as
    // one unit. The extra locality aliases cover the abbreviations commonly
    // present in the operational sheet.
    usort($known, static fn($a, $b) => strlen($b) <=> strlen($a));
    foreach ($known as $name) {
        if (preg_match('/(?:^|\s)' . preg_quote($name, '/') . '(?:\s|$)/i', $s)) {
            return $name;
        }
    }

    return '';
}

$rows = fetch_sheet(false);
$areas = [];
foreach ($rows as $row) {
    $address = trim((string)($row['address'] ?? ''));
    if ($address === '') continue;
    $area = area_success_locality($address);
    if ($area === '' || $area === 'LAINNYA') continue;
    $kecamatan = area_success_kecamatan($address);
    $areas[$area] ??= ['kecamatan'=>$kecamatan, 'address'=>$address];
    // If the first address did not expose a kecamatan, retain a later address
    // from the same customer area that does.
    if ($areas[$area]['kecamatan'] === '' && $kecamatan !== '') {
        $areas[$area]['kecamatan'] = $kecamatan;
        $areas[$area]['address'] = $address;
    }
}
ksort($areas);

$pdo = db();
$pdo->exec("CREATE TABLE IF NOT EXISTS area_success_geocodes (
    area_key TEXT PRIMARY KEY,
    area_name TEXT NOT NULL,
    kecamatan TEXT,
    latitude REAL,
    longitude REAL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'failed',
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
)");
try {
    $pdo->exec("ALTER TABLE area_success_geocodes ADD COLUMN kecamatan TEXT");
} catch (Throwable $e) {
    // Column already exists.
}

function geocode_area_request(string $area, string $kecamatan = ''): ?array {
    $parts = [$area];
    if ($kecamatan !== '' && strcasecmp($kecamatan, $area) !== 0) $parts[] = $kecamatan;
    $parts[] = 'Surabaya';
    $parts[] = 'Jawa Timur';
    $parts[] = 'Indonesia';
    $query = implode(', ', $parts);

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
        'display_name'=>(string)($items[0]['display_name'] ?? $query)
    ];
}

$total = count($areas); $checked=0; $done=0; $cached=0; $failed=0;
echo "AREA SUCCESS GEOCODER\n";
echo "Unique customer areas: {$total}\n";
echo "Geocode query: CUSTOMER AREA + KECAMATAN + SURABAYA\n";
echo "Kecamatan is geocoding context only; success remains per customer area.\n";

foreach (array_keys($areas) as $area) {
    if ($limit > 0 && $checked >= $limit) break;
    $checked++;
    $key = strtolower($area);
    $kecamatan = (string)($areas[$area]['kecamatan'] ?? '');
    $st = $pdo->prepare('SELECT status,latitude,longitude FROM area_success_geocodes WHERE area_key=? LIMIT 1');
    $st->execute([$key]);
    $existing = $st->fetch();
    if ($existing && $existing['status'] === 'ok' && $existing['latitude'] !== null && $existing['longitude'] !== null) {
        $cached++;
        continue;
    }

    $geo = geocode_area_request($area, $kecamatan);
    $now = date('Y-m-d H:i:s');
    if ($geo) {
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kecamatan,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,?, 'ok',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kecamatan=excluded.kecamatan,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$area,$kecamatan,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
        $done++;
        echo "OK {$checked}/{$total} {$area} [{$kecamatan}] -> {$geo['latitude']},{$geo['longitude']}\n";
    } else {
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kecamatan,status,attempts,updated_at) VALUES(?,?,?,'failed',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kecamatan=excluded.kecamatan,status='failed',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$area,$kecamatan,$now]);
        $failed++;
        echo "FAIL {$checked}/{$total} {$area} [{$kecamatan}]\n";
    }
    usleep(1100000);
}

echo "DONE checked={$checked} geocoded={$done} cached={$cached} failed={$failed}\n";
