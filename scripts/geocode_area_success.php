<?php

declare(strict_types=1);

require_once __DIR__ . '/../webapp/php_backend.php';
require_once __DIR__ . '/../webapp/php_area_success.php';

$limit = 0;
foreach ($argv as $arg) if (str_starts_with($arg, '--limit=')) $limit = max(0, (int)substr($arg, 8));

/*
 * IMPORTANT:
 * The map point must NOT be obtained by geocoding the customer-area name.
 * Kecamatan is the geographic scope. We first determine the kecamatan for
 * the customer area, then geocode the FULL customer addresses belonging to
 * that kecamatan/area. The area coordinate is the centroid of those customer
 * address coordinates.
 */
function area_success_location_context(string $address): array {
    $s = area_success_normalize($address);
    if ($s === '') return ['kelurahan'=>'', 'kecamatan'=>''];
    $map = [
        'KEJAWAN PUTIH TAMBAK'=>'MULYOREJO', 'KEJAWAN PUTIH MUTIARA'=>'MULYOREJO',
        'MEDOKAN SEMAMPIR'=>'SUKOLILO', 'KALISARI'=>'MULYOREJO',
        'NGINDEN JANGKUNGAN'=>'SUKOLILO', 'MENUR PUMPUNGAN'=>'SUKOLILO',
        'KEPUTIH'=>'SUKOLILO', 'NGINDEN'=>'SUKOLILO', 'PUMPUNGAN'=>'SUKOLILO',
        'SEMOLOWARU'=>'SUKOLILO', 'KERTAJAYA'=>'GUBENG', 'MOJO'=>'GUBENG',
        'AIRLANGGA'=>'GUBENG', 'GUBENG'=>'GUBENG', 'MULYOREJO'=>'MULYOREJO',
        'TENGGILIS MEJOYO'=>'TENGGILIS MEJOYO', 'GUNUNG ANYAR'=>'GUNUNG ANYAR',
        'RUNGKUT'=>'RUNGKUT', 'TAMBAKSARI'=>'TAMBAKSARI', 'WONOCOLO'=>'WONOCOLO',
        'WONOKROMO'=>'WONOKROMO', 'WIYUNG'=>'WIYUNG', 'DUKUH PAKIS'=>'DUKUH PAKIS',
        'LAKARSANTRI'=>'LAKARSANTRI', 'SAMBIKEREP'=>'SAMBIKEREP', 'SUKOLILO'=>'SUKOLILO',
        'SUKOMANUNGGAL'=>'SUKOMANUNGGAL', 'TANDES'=>'TANDES', 'ASEMROWO'=>'ASEMROWO',
        'BENOWO'=>'BENOWO', 'BUBUTAN'=>'BUBUTAN', 'BULAK'=>'BULAK',
        'GAYUNGAN'=>'GAYUNGAN', 'GENTENG'=>'GENTENG', 'JAMBANGAN'=>'JAMBANGAN',
        'KARANG PILANG'=>'KARANG PILANG', 'KENJERAN'=>'KENJERAN', 'KREMBANGAN'=>'KREMBANGAN',
        'PABEAN CANTIAN'=>'PABEAN CANTIAN', 'PAKAL'=>'PAKAL', 'SAWAHAN'=>'SAWAHAN',
        'SEMAMPIR'=>'SEMAMPIR', 'SIMOKERTO'=>'SIMOKERTO', 'TEGALSARI'=>'TEGALSARI'
    ];
    uksort($map, static fn($a,$b)=>strlen($b)<=>strlen($a));
    foreach ($map as $kel=>$kec) {
        if (preg_match('/(?:^|\s)'.preg_quote($kel,'/').'(?=\s|$)/i', $s)) {
            return ['kelurahan'=>$kel, 'kecamatan'=>$kec];
        }
    }
    return ['kelurahan'=>'', 'kecamatan'=>''];
}

function area_success_area_context(string $area): array {
    $known = [
        'APARTEMEN BALE HINGGIL'=>['MEDOKAN SEMAMPIR','SUKOLILO'],
        'APARTEMEN EDUCITY'=>['KEJAWAN PUTIH TAMBAK','MULYOREJO'],
        'APARTEMEN ONE GALAXY'=>['MULYOREJO','MULYOREJO'],
        'APARTEMEN PUNCAK KERTAJAYA'=>['KERTAJAYA','GUBENG'],
        'APARTEMEN DIAN REGENCY'=>['KEPUTIH','SUKOLILO'],
        'BASKARA'=>['KALISARI','MULYOREJO'],
        'BASKARA SARI'=>['KALISARI','MULYOREJO'],
        'BASKARA SAWAH'=>['KALISARI','MULYOREJO'],
        'BASKARA SELATAN'=>['KALISARI','MULYOREJO'],
        'BASKARA TENGAH'=>['KALISARI','MULYOREJO'],
        'BASKARA UTARA'=>['KALISARI','MULYOREJO']
    ];
    $v = $known[strtoupper(trim($area))] ?? ['', ''];
    return ['kelurahan'=>$v[0], 'kecamatan'=>$v[1]];
}

$rows = fetch_sheet(false);
$areas = [];

foreach ($rows as $row) {
    $address = trim((string)($row['address'] ?? ''));
    if ($address === '') continue;

    $area = area_success_locality($address);
    if ($area === '' || $area === 'LAINNYA') continue;

    // Kecamatan is determined from the customer/address context first.
    $ctx = area_success_location_context($address);
    $known = area_success_area_context($area);
    if ($known['kecamatan'] !== '') $ctx = $known;

    if (!isset($areas[$area])) {
        $areas[$area] = [
            'kelurahan' => $ctx['kelurahan'],
            'kecamatan' => $ctx['kecamatan'],
            'addresses' => []
        ];
    }

    if ($ctx['kelurahan'] !== '') {
        $areas[$area]['kelurahan'] = $ctx['kelurahan'];
        $areas[$area]['kecamatan'] = $ctx['kecamatan'];
    }

    if (!in_array($address, $areas[$area]['addresses'], true)) {
        $areas[$area]['addresses'][] = $address;
    }
}
ksort($areas);

$pdo = db();
$pdo->exec("CREATE TABLE IF NOT EXISTS area_success_geocodes (
    area_key TEXT PRIMARY KEY,
    area_name TEXT NOT NULL,
    kelurahan TEXT,
    kecamatan TEXT,
    latitude REAL,
    longitude REAL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'failed',
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
)");
foreach (['kelurahan','kecamatan'] as $column) {
    try { $pdo->exec("ALTER TABLE area_success_geocodes ADD COLUMN {$column} TEXT"); } catch (Throwable $e) {}
}

// One cache row per FULL customer address. This prevents repeated Nominatim calls.
$pdo->exec("CREATE TABLE IF NOT EXISTS area_success_address_geocodes (
    address_key TEXT PRIMARY KEY,
    address TEXT NOT NULL,
    kecamatan TEXT,
    latitude REAL,
    longitude REAL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'failed',
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
)");

function geocode_http(string $query): ?array {
    $url = 'https://nominatim.openstreetmap.org/search?' . http_build_query([
        'q' => $query,
        'format' => 'jsonv2',
        'limit' => 1,
        'countrycodes' => 'id'
    ]);
    $ctx = stream_context_create(['http' => [
        'timeout' => 15,
        'header' => "User-Agent: Kerja-Bot/1.0 (area-success-map)\r\nAccept: application/json\r\n"
    ]]);
    $raw = @file_get_contents($url, false, $ctx);
    if ($raw === false) return null;
    $items = json_decode($raw, true);
    if (!is_array($items) || empty($items[0]['lat']) || empty($items[0]['lon'])) return null;
    return [
        'latitude' => (float)$items[0]['lat'],
        'longitude' => (float)$items[0]['lon'],
        'display_name' => (string)($items[0]['display_name'] ?? $query)
    ];
}

function geocode_customer_address(string $address, string $kecamatan): ?array {
    // FULL ADDRESS is the primary geocode target. Kecamatan is context only.
    $queries = [];
    if ($kecamatan !== '') {
        $queries[] = implode(', ', array_filter([
            trim($address), 'Kecamatan ' . $kecamatan, 'Kota Surabaya', 'Jawa Timur', 'Indonesia'
        ]));
        $queries[] = implode(', ', array_filter([
            trim($address), $kecamatan, 'Surabaya', 'Jawa Timur', 'Indonesia'
        ]));
    }
    $queries[] = implode(', ', array_filter([
        trim($address), 'Surabaya', 'Jawa Timur', 'Indonesia'
    ]));

    foreach (array_values(array_unique($queries)) as $i => $query) {
        $geo = geocode_http($query);
        if ($geo) return $geo;
        if ($i < count($queries) - 1) usleep(1100000);
    }
    return null;
}

function address_key(string $address): string {
    return strtolower(trim(preg_replace('/\s+/', ' ', $address)));
}

$total = count($areas);
$checked = 0;
$done = 0;
$cached = 0;
$failed = 0;
$address_geocoded = 0;
$address_cached = 0;
$address_failed = 0;

echo "AREA SUCCESS GEOCODER\n";
echo "Unique customer areas: {$total}\n";
echo "Geocode strategy: KECAMATAN -> FULL CUSTOMER ADDRESSES -> AREA CENTROID\n";
echo "No area-name/POI geocoding. Kecamatan is scope; customer addresses provide coordinates.\n";

foreach ($areas as $area => $info) {
    if ($limit > 0 && $checked >= $limit) break;
    $checked++;

    $key = strtolower($area);
    $kel = (string)($info['kelurahan'] ?? '');
    $kec = (string)($info['kecamatan'] ?? '');
    $addresses = array_values(array_unique((array)($info['addresses'] ?? [])));

    if ($kec === '') {
        $failed++;
        echo "FAIL {$checked}/{$total} {$area} [{$kel} | KECAMATAN UNKNOWN] addresses=" . count($addresses) . "\n";
        continue;
    }

    $points = [];
    $names = [];

    foreach ($addresses as $address) {
        $akey = address_key($address);
        $st = $pdo->prepare('SELECT status,latitude,longitude,display_name FROM area_success_address_geocodes WHERE address_key=? LIMIT 1');
        $st->execute([$akey]);
        $existing = $st->fetch();

        if ($existing && $existing['status'] === 'ok' && $existing['latitude'] !== null && $existing['longitude'] !== null) {
            $geo = [
                'latitude' => (float)$existing['latitude'],
                'longitude' => (float)$existing['longitude'],
                'display_name' => (string)($existing['display_name'] ?? $address)
            ];
            $address_cached++;
        } else {
            $geo = geocode_customer_address($address, $kec);
            $now = date('Y-m-d H:i:s');
            if ($geo) {
                $pdo->prepare("INSERT INTO area_success_address_geocodes(address_key,address,kecamatan,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,?, 'ok',1,?) ON CONFLICT(address_key) DO UPDATE SET address=excluded.address,kecamatan=excluded.kecamatan,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=area_success_address_geocodes.attempts+1,updated_at=excluded.updated_at")
                    ->execute([$akey,$address,$kec,$geo['latitude'],$geo['longitude'],$geo['display_name'],$now]);
                $address_geocoded++;
            } else {
                $pdo->prepare("INSERT INTO area_success_address_geocodes(address_key,address,kecamatan,status,attempts,updated_at) VALUES(?,?,?,'failed',1,?) ON CONFLICT(address_key) DO UPDATE SET address=excluded.address,kecamatan=excluded.kecamatan,status='failed',attempts=area_success_address_geocodes.attempts+1,updated_at=excluded.updated_at")
                    ->execute([$akey,$address,$kec,$now]);
                $address_failed++;
                continue;
            }
            usleep(1100000);
        }

        $points[] = [$geo['latitude'], $geo['longitude']];
        $names[] = $geo['display_name'];
    }

    if (!$points) {
        $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kelurahan,kecamatan,status,attempts,updated_at) VALUES(?,?,?,?, 'failed',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kelurahan=excluded.kelurahan,kecamatan=excluded.kecamatan,status='failed',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")
            ->execute([$key,$area,$kel,$kec,date('Y-m-d H:i:s')]);
        $failed++;
        echo "FAIL {$checked}/{$total} {$area} [{$kel} | {$kec}] customers=" . count($addresses) . " geocoded=0\n";
        continue;
    }

    $lat = array_sum(array_column($points, 0)) / count($points);
    $lon = array_sum(array_column($points, 1)) / count($points);
    $now = date('Y-m-d H:i:s');

    $pdo->prepare("INSERT INTO area_success_geocodes(area_key,area_name,kelurahan,kecamatan,latitude,longitude,display_name,status,attempts,updated_at) VALUES(?,?,?,?,?,?,?,'ok',1,?) ON CONFLICT(area_key) DO UPDATE SET area_name=excluded.area_name,kelurahan=excluded.kelurahan,kecamatan=excluded.kecamatan,latitude=excluded.latitude,longitude=excluded.longitude,display_name=excluded.display_name,status='ok',attempts=area_success_geocodes.attempts+1,updated_at=excluded.updated_at")
        ->execute([$key,$area,$kel,$kec,$lat,$lon,$names[0],$now]);

    $done++;
    echo "OK {$checked}/{$total} {$area} [{$kel} | {$kec}] customers=" . count($addresses) . " geocoded=" . count($points) . " -> {$lat},{$lon}\n";
}

echo "DONE checked={$checked} areas_geocoded={$done} areas_failed={$failed} address_geocoded={$address_geocoded} address_cached={$address_cached} address_failed={$address_failed}\n";
